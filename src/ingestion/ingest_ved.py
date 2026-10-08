"""Source-faithful local PySpark VED ingestion with bounded Arrow Parquet IO.

Raw CSV tokens remain strings (including literal NaN), and raw_line retains
each observation without its line terminator. Numeric views are inspection
only. Spark parses/orders records; approved PyArrow writes Parquet to avoid
Hadoop's unavailable Windows native writer. No records are deduplicated.
"""
import argparse
import csv
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import py7zr
from pyspark.sql import SparkSession, functions as F, types as T

ROOT = Path(__file__).resolve().parents[2]
CAP = 5_000_000_000
RAW = ROOT / "data/raw/ved"
OUTPUT = ROOT / "data/bronze/ved"
HEADERS = [
    "DayNum", "VehId", "Trip", "Timestamp(ms)", "Latitude[deg]",
    "Longitude[deg]", "Vehicle Speed[km/h]", "MAF[g/sec]", "Engine RPM[RPM]",
    "Absolute Load[%]", "OAT[DegC]", "Fuel Rate[L/hr]",
    "Air Conditioning Power[kW]", "Air Conditioning Power[Watts]",
    "Heater Power[Watts]", "HV Battery Current[A]", "HV Battery SOC[%]",
    "HV Battery Voltage[V]", "Short Term Fuel Trim Bank 1[%]",
    "Short Term Fuel Trim Bank 2[%]", "Long Term Fuel Trim Bank 1[%]",
    "Long Term Fuel Trim Bank 2[%]",
]
SOURCE_SCHEMA = T.StructType([T.StructField(n, T.StringType(), True) for n in HEADERS])
PARSE_SCHEMA = T.StructType(SOURCE_SCHEMA.fields + [T.StructField("_corrupt_record", T.StringType(), True)])
ARROW_SCHEMA = pa.schema([(n, pa.string()) for n in HEADERS] + [
    ("raw_line", pa.string()), ("source_file", pa.string()),
    ("source_week", pa.string()), ("is_malformed", pa.bool_()),
    ("malformed_reason", pa.string()),
])
LOG = logging.getLogger("fleetpulse.ved")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def footprint():
    return sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())


def budget(additional=0):
    used = footprint()
    if used + additional >= CAP:
        raise RuntimeError(f"5 GB storage gate: used={used}, reserved/additional={additional}")
    if shutil.disk_usage(ROOT).free < additional + 100_000_000:
        raise RuntimeError("Insufficient free disk before staging/writing")
    return used


def spark_session():
    return (SparkSession.builder.master("local[2]").appName("FleetPulse-VED-Bronze")
            .config("spark.driver.memory", "2g")
            .config("spark.sql.shuffle.partitions", "2")
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.sql.execution.arrow.pyspark.enabled", "true")
            .config("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
            .config("spark.pyspark.python", sys.executable)
            .config("spark.pyspark.driver.python", sys.executable)
            .getOrCreate())


def inspect_source(path):
    """Check actual header, count physical observation lines and hash the file."""
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        first = stream.readline().rstrip("\r\n")
        header = next(csv.reader([first]))
    if header != HEADERS:
        raise ValueError(f"Source header mismatch: {path.name}: {header}")
    count = 0
    last = b""
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            count += block.count(b"\n")
            last = block[-1:]
    if last and last != b"\n":
        count += 1
    return {"header": first, "rows": count - 1, "sha256": sha256(path),
            "bytes": path.stat().st_size}


def parse_source(spark, path, header):
    # Explicit files avoid Hadoop's Windows native directory listing.
    lines = spark.read.text(str(Path(path).resolve())).withColumnRenamed("value", "raw_line")
    lines = lines.where(F.col("raw_line") != F.lit(header))
    ddl = ", ".join(f"`{field.name}` STRING" for field in PARSE_SCHEMA)
    parsed = F.from_csv(F.col("raw_line"), ddl, {
        "mode": "PERMISSIVE", "columnNameOfCorruptRecord": "_corrupt_record",
        "ignoreLeadingWhiteSpace": "false", "ignoreTrailingWhiteSpace": "false",
        "escape": '"',
        "nullValue": "__FLEETPULSE_RESERVED_NULL__", "emptyValue": "",
    })
    week = "20" + Path(path).name[4:6] + "-" + Path(path).name[6:8] + "-" + Path(path).name[8:10]
    return (lines.withColumn("parsed", parsed)
            .select(*[F.col("parsed").getField(n).alias(n) for n in HEADERS], "raw_line",
                    F.lit(Path(path).name).alias("source_file"), F.lit(week).alias("source_week"),
                    (F.col("parsed._corrupt_record").isNotNull() | (F.col("raw_line") == "")).alias("is_malformed"),
                    F.when(F.col("parsed._corrupt_record").isNotNull() | (F.col("raw_line") == ""),
                           F.lit("CSV field count/structure mismatch")).alias("malformed_reason")))


def write_bronze(spark, source, destination):
    started = time.perf_counter()
    source, destination = Path(source), Path(destination)
    observed = inspect_source(source)
    frame = parse_source(spark, source, observed["header"]).orderBy("raw_line")
    # One weekly CSV is <= 97 MB; never collect the complete dataset.
    pandas = frame.toPandas()
    if len(pandas) != observed["rows"]:
        raise RuntimeError(f"No-drop reconciliation failed: {source}: {len(pandas)} != {observed['rows']}")
    table = pa.Table.from_pandas(pandas, schema=ARROW_SCHEMA, preserve_index=False)
    malformed = int(pandas["is_malformed"].sum())
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".parquet.pending")
    budget(observed["bytes"] + 100_000_000)
    pq.write_table(table, temporary, compression="zstd", compression_level=3,
                   row_group_size=65536, write_statistics=True)
    if pq.ParquetFile(temporary).metadata.num_rows != observed["rows"]:
        raise RuntimeError("Parquet row-count mismatch")
    if pq.read_schema(temporary) != ARROW_SCHEMA:
        # Pandas metadata is not part of the logical field schema comparison.
        if not pq.read_schema(temporary).equals(ARROW_SCHEMA, check_metadata=False):
            raise RuntimeError("Parquet schema mismatch")
    os.replace(temporary, destination)
    result = {"source_file": source.name, "source_sha256": observed["sha256"],
              "source_bytes": observed["bytes"], "source_rows": observed["rows"],
              "bronze_rows": table.num_rows, "malformed_rows": malformed,
              "output_bytes": destination.stat().st_size, "output_sha256": sha256(destination),
              "seconds": time.perf_counter() - started}
    LOG.info("Reconciled %s", json.dumps(result))
    return result


def read_bronze(spark, root=OUTPUT):
    files = sorted(Path(root).rglob("*.parquet"))
    if not files:
        raise ValueError("No Bronze Parquet files")
    return spark.read.option("recursiveFileLookup", "true").parquet(*[str(f.resolve()) for f in files])


def remove_staged(path):
    """Delete only a CSV generated in this pipeline's own staging directory."""
    path = Path(path).resolve()
    staging = (ROOT / "data/tmp/ved").resolve()
    if not path.is_relative_to(staging) or path.suffix != ".csv":
        raise ValueError(f"Refusing staging cleanup: {path}")
    path.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Recompute weekly outputs; never append")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started = time.perf_counter()
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "results/day2_ingestion.json"
    prior = json.loads(report_path.read_text()) if report_path.exists() else {}
    if prior.get("source_commit") != manifest["commit"]:
        prior = {}
    prior_files = {f["source_file"]: f for f in prior.get("files", [])}
    results = []
    peak = budget()
    spark = spark_session()
    try:
        for part, entry in enumerate(manifest["sources"], start=1):
            if not entry["filename"].endswith(".7z"):
                continue
            archive_path = RAW / entry["filename"]
            if entry.get("integrity") != "all member CRCs passed" or sha256(archive_path) != entry["sha256"]:
                raise RuntimeError("Archive integrity checkpoint absent or hash changed")
            stage = ROOT / f"data/tmp/ved/part{part}"
            stage.mkdir(parents=True, exist_ok=True)
            required = []
            for member in entry["members"]:
                filename = member["name"]
                if Path(filename).name != filename or not filename.endswith(".csv"):
                    raise ValueError("Unexpected/unsafe archive member")
                month = "20" + filename[4:6] + "-" + filename[6:8]
                target = OUTPUT / f"source_month={month}" / Path(filename).with_suffix(".parquet").name
                cached = prior_files.get(filename)
                if not args.force and cached and target.exists() and sha256(target) == cached["output_sha256"]:
                    results.append({**cached, "cached": True})
                    continue
                required.append((filename, target))
            if not required:
                continue
            missing = [filename for filename, _ in required if not (stage / filename).exists()]
            if missing:
                budget(entry["expanded_bytes"] + 1_000_000_000 + 250_000_000)
                LOG.info("Staging %s (free=%s)", archive_path.name, shutil.disk_usage(ROOT).free)
                with py7zr.SevenZipFile(archive_path) as archive:
                    archive.extract(path=stage, targets=missing)
            peak = max(peak, budget())
            for filename, target in required:
                result = write_bronze(spark, stage / filename, target)
                result["cached"] = False
                results.append(result)
                peak = max(peak, budget())
                remove_staged(stage / filename)
                report = {"schema_version": 1, "source_commit": manifest["commit"], "spark": spark.version,
                          "files": results, "peak_project_bytes_observed": peak,
                          "elapsed_seconds": time.perf_counter() - started, "complete": False}
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        expected = sum(len(e["members"]) for e in manifest["sources"] if "members" in e)
        if len(results) != expected:
            raise RuntimeError("Source file reconciliation failed")
        expected_files = {r["source_file"].replace(".csv", ".parquet") for r in results}
        if {p.name for p in OUTPUT.rglob("*.parquet")} != expected_files:
            raise RuntimeError("Unexpected or missing Bronze files")
        output_count = read_bronze(spark).count()
        source_count = sum(r["source_rows"] for r in results)
        if output_count != source_count:
            raise RuntimeError("Full Bronze row-count reconciliation failed")
        report = {"schema_version": 1, "source_commit": manifest["commit"], "spark": spark.version,
                  "source_rows": source_count, "bronze_rows": output_count,
                  "malformed_rows": sum(r["malformed_rows"] for r in results),
                  "files": results, "peak_project_bytes_observed": peak,
                  "elapsed_seconds": time.perf_counter() - started, "complete": True,
                  "project_bytes": budget(), "output_bytes": sum(r["output_bytes"] for r in results)}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        LOG.info("Complete: %s", json.dumps({k:v for k,v in report.items() if k != "files"}))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
