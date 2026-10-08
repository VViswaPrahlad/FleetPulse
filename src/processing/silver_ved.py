"""Deterministic, auditable Silver from immutable Day 2 Bronze.

PySpark performs normalization and row/field quality rules. PyArrow performs
bounded weekly Windows-compatible IO. Every source row reaches Silver or
quarantine, traced by (bronze_file, bronze_row_index). No sensor imputation.
"""
import argparse
import hashlib
import json
import logging
import os
import shutil
import time
import threading
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pyspark import StorageLevel
from pyspark.sql import functions as F, Window, types as T

from src.ingestion.ingest_ved import ROOT, OUTPUT as BRONZE, SOURCE_SCHEMA, ARROW_SCHEMA, sha256, footprint, spark_session
from src.quality.fuel_feasibility import static_types

SILVER = ROOT / "data/silver/ved"
QUARANTINE = ROOT / "data/quarantine/ved"
RESULTS = ROOT / "results/day3"
RULE_VERSION = "ved-silver-1"
HARD_CAP = 10_000_000_000
SOC_TOLERANCE = 0.001
FIELDS = {
    "DayNum": "day_number", "VehId": "vehicle_id", "Trip": "trip_id", "Timestamp(ms)": "elapsed_ms",
    "Latitude[deg]": "latitude_deg", "Longitude[deg]": "longitude_deg",
    "Vehicle Speed[km/h]": "speed_kmh", "MAF[g/sec]": "maf_g_s",
    "Engine RPM[RPM]": "engine_rpm", "Absolute Load[%]": "absolute_load_pct",
    "OAT[DegC]": "outside_air_temp_c", "Fuel Rate[L/hr]": "fuel_rate_lph",
    "Air Conditioning Power[kW]": "aircon_power_kw", "Air Conditioning Power[Watts]": "aircon_power_w",
    "Heater Power[Watts]": "heater_power_w", "HV Battery Current[A]": "hv_battery_current_a",
    "HV Battery SOC[%]": "battery_soc_pct", "HV Battery Voltage[V]": "hv_battery_voltage_v",
    "Short Term Fuel Trim Bank 1[%]": "short_fuel_trim_b1_pct", "Short Term Fuel Trim Bank 2[%]": "short_fuel_trim_b2_pct",
    "Long Term Fuel Trim Bank 1[%]": "long_fuel_trim_b1_pct", "Long Term Fuel Trim Bank 2[%]": "long_fuel_trim_b2_pct",
}
INTEGER_FIELDS = {"vehicle_id", "trip_id", "elapsed_ms"}
NONNEGATIVE_FIELDS = {"speed_kmh", "maf_g_s", "engine_rpm", "absolute_load_pct", "fuel_rate_lph",
                      "aircon_power_kw", "aircon_power_w", "heater_power_w", "hv_battery_voltage_v"}
INPUT_COLUMNS = list(FIELDS) + ["source_file", "source_week", "is_malformed", "malformed_reason"]
INPUT_SCHEMA = T.StructType(SOURCE_SCHEMA.fields + [T.StructField("source_file", T.StringType()),
    T.StructField("source_week", T.StringType()), T.StructField("is_malformed", T.BooleanType()),
    T.StructField("malformed_reason", T.StringType()), T.StructField("bronze_row_index", T.LongType())])
SILVER_SCHEMA = pa.schema([(name, pa.int64() if name in INTEGER_FIELDS else pa.float64()) for name in FIELDS.values()] + [
    ("battery_soc_source_pct", pa.float64()), ("engine_type", pa.string()),
    ("source_file", pa.string()), ("source_week", pa.date32()), ("bronze_file", pa.string()),
    ("bronze_row_index", pa.int64()), ("quality_flags", pa.list_(pa.string())),
    ("exclusion_reasons", pa.list_(pa.string())), ("sampling_gap_ms", pa.int64()),
    ("gap_gt_2000ms", pa.bool_()),
])
LOG = logging.getLogger("fleetpulse.silver")


def flags(expressions):
    # ArrayFilter uses interpreted CodegenFallback in installed Spark 4.0.3.
    # Conditional singleton/empty arrays preserve the same ordered flag list
    # while allowing Spark to share generated scalar parsing expressions.
    empty = F.array().cast("array<string>")
    return F.concat(*[F.when(expression.isNotNull(), F.array(expression)).otherwise(empty)
                      for expression in expressions])


def clean_frame(frame, bronze_file, engine_types):
    """Apply explicit source, cell and exclusion rules without discarding rows."""
    numeric = {}
    quality = []
    for original, alias in FIELDS.items():
        token = F.col(original)
        missing = token.isNull() | F.lower(F.trim(token)).isin("", "nan")
        cast = token.try_cast("double")
        finite = cast.isNotNull() & ~F.isnan(cast) & (F.abs(cast) != float("inf"))
        value = F.when(finite, cast)
        numeric[alias] = value
        quality.append(F.when(~missing & ~finite, F.lit("invalid_numeric_" + alias)))
    reasons = [F.when(F.coalesce(F.col("is_malformed"), F.lit(True)), F.lit("malformed_bronze"))]
    for name in ["vehicle_id", "trip_id"]:
        value = numeric[name]
        reasons.append(F.when(value.isNull() | (value < 0) | (value != F.floor(value)), F.lit("invalid_"+name)))
    elapsed = numeric["elapsed_ms"]
    reasons.extend([F.when(elapsed.isNull() | (elapsed != F.floor(elapsed)), F.lit("invalid_elapsed_ms")),
                    F.when(elapsed < 0, F.lit("negative_elapsed_ms")),
                    F.when(numeric["day_number"].isNull() | (numeric["day_number"] < 1), F.lit("invalid_day_number")),
                    F.when(F.col("source_week").try_cast("date").isNull(), F.lit("invalid_source_week"))])
    projected = []
    for name, value in numeric.items():
        if name in INTEGER_FIELDS:
            value = F.when(value == F.floor(value), value.cast("long"))
        elif name in NONNEGATIVE_FIELDS:
            quality.append(F.when(value < 0, F.lit("negative_"+name)))
            value = F.when(value >= 0, value)
        elif name == "latitude_deg":
            quality.append(F.when(F.abs(value) > 90, F.lit("invalid_latitude")))
            value = F.when(F.abs(value) <= 90, value)
        elif name == "longitude_deg":
            quality.append(F.when(F.abs(value) > 180, F.lit("invalid_longitude")))
            value = F.when(F.abs(value) <= 180, value)
        elif name == "outside_air_temp_c":
            quality.append(F.when(value < -273.15, F.lit("below_absolute_zero")))
            value = F.when(value >= -273.15, value)
        elif name == "battery_soc_pct":
            tiny = (value > 100) & (value <= 100 + SOC_TOLERANCE)
            bad = (value < 0) | (value > 100 + SOC_TOLERANCE)
            quality.extend([F.when(tiny, F.lit("soc_precision_clipped")), F.when(bad, F.lit("soc_out_of_range"))])
            value = F.when(tiny, F.lit(100.0)).when(~bad, value)
        projected.append(value.alias(name))
    quality.extend([F.when(numeric["speed_kmh"].isNull(), F.lit("missing_speed_kmh")),
                    F.when(numeric["fuel_rate_lph"].isNull(), F.lit("missing_fuel_rate_lph")),
                    F.when(numeric["absolute_load_pct"] > 100, F.lit("load_above_100_advisory"))])
    mapping = F.create_map(*[item for vehicle, kind in sorted(engine_types.items()) for item in (F.lit(vehicle).cast("long"), F.lit(kind))])
    engine = F.element_at(mapping, F.when(numeric["vehicle_id"] == F.floor(numeric["vehicle_id"]), numeric["vehicle_id"].cast("long")))
    quality.append(F.when(engine.isNull(), F.lit("unknown_engine_type")))
    output = frame.select(*projected, numeric["battery_soc_pct"].alias("battery_soc_source_pct"), engine.alias("engine_type"),
                          "source_file", F.col("source_week").try_cast("date").alias("source_week"),
                          F.lit(bronze_file).alias("bronze_file"), "bronze_row_index",
                          flags(quality).alias("quality_flags"), flags(reasons).alias("exclusion_reasons"))
    duplicate = Window.partitionBy("vehicle_id", "trip_id", "elapsed_ms")
    return output.withColumn("quality_flags", F.when(F.count("*").over(duplicate) > 1,
        F.concat("quality_flags", F.array(F.lit("duplicate_observation_key")))).otherwise(F.col("quality_flags")))


def retained_frame(cleaned):
    retained = cleaned.where(F.size("exclusion_reasons") == 0)
    window = Window.partitionBy("vehicle_id", "trip_id").orderBy("elapsed_ms", "bronze_row_index")
    retained = retained.withColumn("sampling_gap_ms", F.col("elapsed_ms") - F.lag("elapsed_ms").over(window))
    return (retained.withColumn("gap_gt_2000ms", F.coalesce(F.col("sampling_gap_ms") > 2000, F.lit(False)))
            .withColumn("quality_flags", F.when(F.col("gap_gt_2000ms"),
                F.concat("quality_flags", F.array(F.lit("irregular_gap_gt_2s")))).otherwise(F.col("quality_flags")))
            .orderBy("vehicle_id", "trip_id", "elapsed_ms", "bronze_row_index"))


def rejected_frame(cleaned):
    return (cleaned.where(F.size("exclusion_reasons") > 0)
            .withColumn("sampling_gap_ms", F.lit(None).cast("long"))
            .withColumn("gap_gt_2000ms", F.lit(False)).orderBy("bronze_row_index"))


def write_table(table, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.pending")
    if footprint() + table.nbytes + 100_000_000 >= HARD_CAP:
        raise RuntimeError("10 GB project storage gate")
    if shutil.disk_usage(ROOT).free < table.nbytes + 100_000_000:
        raise RuntimeError("Insufficient free disk")
    pq.write_table(table, temporary, compression="zstd", compression_level=3, row_group_size=65536)
    if pq.ParquetFile(temporary).metadata.num_rows != table.num_rows:
        raise RuntimeError("Output count reconciliation failed")
    if not pq.read_schema(temporary).equals(SILVER_SCHEMA, check_metadata=False):
        raise RuntimeError("Output schema mismatch")
    os.replace(temporary, path)


def flag_counts(table, column):
    values = pc.value_counts(pc.list_flatten(table.column(column))).to_pylist()
    return {r["values"]: r["counts"] for r in values}


def process_file(spark, path, silver_path, rejected_path, engine_types):
    started = time.perf_counter()
    path = Path(path)
    if not pq.read_schema(path).equals(ARROW_SCHEMA, check_metadata=False):
        raise ValueError(f"Bronze schema mismatch: {path}")
    source = pq.read_table(path, columns=INPUT_COLUMNS).to_pandas()
    source["bronze_row_index"] = np.arange(len(source), dtype=np.int64)
    relative = path.relative_to(BRONZE).as_posix() if path.is_relative_to(BRONZE) else path.name
    # Arrow supplies batches of 10,000 rows. Coalesce those input partitions
    # before normalization so a weekly file uses two tasks rather than 50+.
    frame = spark.createDataFrame(source, INPUT_SCHEMA).coalesce(2)
    cleaned = clean_frame(frame, relative, engine_types).persist(StorageLevel.MEMORY_AND_DISK)
    try:
        retained_pd = retained_frame(cleaned).toPandas()
        rejected_pd = rejected_frame(cleaned).toPandas()
    finally:
        cleaned.unpersist(blocking=True)
    if len(source) != len(retained_pd) + len(rejected_pd):
        raise RuntimeError("Input = retained + excluded reconciliation failed")
    indexes = np.concatenate([retained_pd.bronze_row_index.to_numpy(), rejected_pd.bronze_row_index.to_numpy()])
    if not np.array_equal(np.sort(indexes), np.arange(len(source))):
        raise RuntimeError("Source row identities were lost or duplicated")
    retained = pa.Table.from_pandas(retained_pd, schema=SILVER_SCHEMA, preserve_index=False)
    rejected = pa.Table.from_pandas(rejected_pd, schema=SILVER_SCHEMA, preserve_index=False)
    write_table(retained, silver_path)
    write_table(rejected, rejected_path)
    summary = {"bronze_file": relative, "bronze_sha256": sha256(path), "input_rows": len(source),
               "retained_rows": retained.num_rows, "excluded_rows": rejected.num_rows,
               "quality_flags": flag_counts(retained, "quality_flags"),
               "exclusion_reasons": flag_counts(rejected, "exclusion_reasons"),
               "retained_null_counts": {name: retained.column(name).null_count for name in FIELDS.values()},
               "retained_ranges": {name: pc.min_max(retained.column(name)).as_py() for name in FIELDS.values()},
               "retained_vehicle_ids": sorted(map(int, retained_pd.vehicle_id.unique())),
               "retained_trip_keys": retained_pd[["vehicle_id", "trip_id"]].drop_duplicates().astype(int).values.tolist(),
               "silver_bytes": Path(silver_path).stat().st_size, "quarantine_bytes": Path(rejected_path).stat().st_size,
               "silver_sha256": sha256(silver_path), "quarantine_sha256": sha256(rejected_path),
               "elapsed_seconds": time.perf_counter()-started}
    LOG.info("Reconciled %s: input=%s retained=%s excluded=%s seconds=%.2f", path.name, len(source), retained.num_rows,
             rejected.num_rows, summary["elapsed_seconds"])
    return summary


def read_silver(spark, root=SILVER):
    paths = sorted(Path(root).rglob("*.parquet"))
    return spark.read.option("recursiveFileLookup", "true").parquet(*[str(p.resolve()) for p in paths])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started = time.perf_counter()
    feasibility = json.loads((RESULTS / "fuel_feasibility.json").read_text())
    if not feasibility["complete"] or feasibility["trips_across_bronze_files"] != 0:
        raise RuntimeError("Verified weekly trip-local continuity contract required before Silver")
    paths = sorted(BRONZE.rglob("*.parquet"))
    current_hashes = {p.relative_to(BRONZE).as_posix(): sha256(p) for p in paths}
    if current_hashes != feasibility["bronze_sha256"]:
        raise RuntimeError("Bronze changed since fuel feasibility analysis")
    engine_types = static_types()
    config_hash = hashlib.sha256(json.dumps({"rule_version": RULE_VERSION, "soc_tolerance": SOC_TOLERANCE,
                                           "engine_types": engine_types}, sort_keys=True).encode()).hexdigest()
    checkpoint = RESULTS / "silver_quality.json"
    previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    previous_files = {f["bronze_file"]: f for f in previous.get("files", [])} if previous.get("config_sha256") == config_hash else {}
    summaries, peak = [], footprint()
    spark = spark_session()
    spark.sparkContext.setLogLevel("ERROR")
    spark.conf.set("spark.sql.codegen.maxFields", "200")
    stop_monitor = threading.Event()
    monitor = {"peak": footprint(), "cancelled": False}

    def watch_storage():
        while not stop_monitor.wait(1):
            try:
                used = footprint()
            except FileNotFoundError:
                continue
            monitor["peak"] = max(monitor["peak"], used)
            if used >= 9_000_000_000:
                monitor["cancelled"] = True
                spark.sparkContext.cancelAllJobs()
                return

    watcher = threading.Thread(target=watch_storage, daemon=True)
    watcher.start()
    try:
        for path in paths:
            relative = path.relative_to(BRONZE)
            silver_path, rejected_path = SILVER / relative, QUARANTINE / relative
            old = previous_files.get(relative.as_posix())
            if (not args.force and old and old["bronze_sha256"] == current_hashes[relative.as_posix()]
                and silver_path.exists() and rejected_path.exists()
                and sha256(silver_path) == old["silver_sha256"] and sha256(rejected_path) == old["quarantine_sha256"]):
                summaries.append({**old, "cached": True})
            else:
                summaries.append({**process_file(spark,path,silver_path,rejected_path,engine_types), "cached": False})
            peak = max(peak, footprint(), monitor["peak"])
            if monitor["cancelled"]:
                raise RuntimeError("Processing cancelled before reaching the 10 GB cap")
            checkpoint.write_text(json.dumps({"complete": False, "rule_version": RULE_VERSION,
                "config_sha256": config_hash, "files": summaries, "peak_project_bytes_observed": peak,
                "elapsed_seconds": time.perf_counter()-started}, indent=2),encoding="utf-8")
        if {p.relative_to(SILVER).as_posix() for p in SILVER.rglob("*.parquet")} != set(current_hashes):
            raise RuntimeError("Unexpected/missing Silver output files")
        if {p.relative_to(QUARANTINE).as_posix() for p in QUARANTINE.rglob("*.parquet")} != set(current_hashes):
            raise RuntimeError("Unexpected/missing quarantine files")
        retained_rows = sum(r["retained_rows"] for r in summaries)
        excluded_rows = sum(r["excluded_rows"] for r in summaries)
        assert retained_rows + excluded_rows == feasibility["rows"]
        assert read_silver(spark).count() == retained_rows
        assert read_silver(spark, QUARANTINE).count() == excluded_rows
        after = {p.relative_to(BRONZE).as_posix(): sha256(p) for p in paths}
        if after != current_hashes:
            raise RuntimeError("Bronze preservation audit failed")
        quality, exclusions, nulls = Counter(), Counter(), Counter()
        for record in summaries:
            quality.update(record["quality_flags"])
            exclusions.update(record["exclusion_reasons"])
            nulls.update(record["retained_null_counts"])
        report = {"complete": True, "rule_version": RULE_VERSION, "config_sha256": config_hash,
                  "input_rows": feasibility["rows"], "retained_rows": retained_rows, "excluded_rows": excluded_rows,
                  "retained_vehicles": len({v for r in summaries for v in r["retained_vehicle_ids"]}),
                  "retained_trips": len({tuple(k) for r in summaries for k in r["retained_trip_keys"]}),
                  "quality_flags": dict(quality), "exclusion_reasons": dict(exclusions), "retained_null_counts": dict(nulls),
                  "silver_bytes": sum(r["silver_bytes"] for r in summaries), "quarantine_bytes": sum(r["quarantine_bytes"] for r in summaries),
                  "files": summaries, "bronze_unchanged": True, "spark": spark.version,
                  "java": spark._jvm.java.lang.System.getProperty("java.version"),
                  "elapsed_seconds": time.perf_counter()-started,
                  "peak_project_bytes_observed": peak, "project_bytes": footprint()}
        checkpoint.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k != "files"},indent=2),flush=True)
    finally:
        stop_monitor.set()
        watcher.join(timeout=2)
        spark.stop()


if __name__ == "__main__":
    main()
