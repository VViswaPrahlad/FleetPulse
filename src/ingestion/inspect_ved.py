"""Inspection-only numeric views and quality statistics; never modifies Bronze."""
import json
import time
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from pyspark.sql import functions as F, Window
from src.ingestion.ingest_ved import ROOT, RAW, HEADERS, read_bronze, spark_session, budget, footprint

NUMERIC = {"daynum": "DayNum", "vehicle_id": "VehId", "trip_id": "Trip",
           "timestamp_ms": "Timestamp(ms)", "latitude": "Latitude[deg]",
           "longitude": "Longitude[deg]", "speed_kmh": "Vehicle Speed[km/h]",
           "fuel_lph": "Fuel Rate[L/hr]", "rpm": "Engine RPM[RPM]",
           "battery_current_a": "HV Battery Current[A]", "battery_soc_pct": "HV Battery SOC[%]",
           "battery_voltage_v": "HV Battery Voltage[V]", "maf_gps": "MAF[g/sec]",
           "absolute_load_pct": "Absolute Load[%]", "oat_degc": "OAT[DegC]",
           "aircon_kw": "Air Conditioning Power[kW]", "aircon_w": "Air Conditioning Power[Watts]",
           "heater_w": "Heater Power[Watts]", "short_trim_b1": "Short Term Fuel Trim Bank 1[%]",
           "short_trim_b2": "Short Term Fuel Trim Bank 2[%]", "long_trim_b1": "Long Term Fuel Trim Bank 1[%]",
           "long_trim_b2": "Long Term Fuel Trim Bank 2[%]"}


def numeric_view(frame):
    columns = []
    for alias, original in NUMERIC.items():
        value = F.col(original).try_cast("double")
        columns.append(F.when(value.isNotNull() & ~F.isnan(value) & (F.abs(value) != float("inf")),
                              value).alias(alias))
    return frame.select(*columns)


def invalid_timestamp(frame):
    return (F.col("timestamp_ms").isNull() | (F.col("timestamp_ms") < 0) |
            (F.col("timestamp_ms") != F.floor("timestamp_ms")))


def duplicate_counts(frame, columns):
    grouped = frame.groupBy(*columns).count().where(F.col("count") > 1)
    row = grouped.agg(F.count("*").alias("groups"),
                      F.coalesce(F.sum(F.col("count") - 1), F.lit(0)).alias("excess_rows")).first()
    return row.asDict()


def xlsx_rows(path):
    """Read the author's small static XLSX with stdlib (no openpyxl dependency)."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(si.itertext()) for si in root.findall("s:si", ns)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        result = []
        for row in sheet.findall(".//s:sheetData/s:row", ns):
            values = {}
            for cell in row.findall("s:c", ns):
                key = "".join(c for c in cell.attrib["r"] if c.isalpha())
                value = cell.find("s:v", ns)
                text = value.text if value is not None else ""
                if cell.attrib.get("t") == "s":
                    text = shared[int(text)]
                elif cell.attrib.get("t") == "inlineStr":
                    text = "".join(cell.find("s:is", ns).itertext())
                values[key] = text
            result.append(values)
    return result


def main():
    started = time.perf_counter()
    spark = spark_session()
    spark.sparkContext.setLogLevel("ERROR")
    spark.conf.set("spark.sql.shuffle.partitions", "16")
    monitor_stop = threading.Event()
    monitor = {"peak": footprint(), "cancelled": False}

    def watch_storage():
        while not monitor_stop.wait(1):
            try:
                used = footprint()
            except FileNotFoundError:
                continue  # Spark may remove a temporary file while measuring.
            monitor["peak"] = max(monitor["peak"], used)
            if used >= 4_500_000_000:
                monitor["cancelled"] = True
                spark.sparkContext.cancelAllJobs()
                return

    watcher = threading.Thread(target=watch_storage, daemon=True)
    watcher.start()
    try:
        raw = read_bronze(spark)
        numeric = numeric_view(raw)
        expressions = [F.count("*").alias("rows"), F.countDistinct("vehicle_id").alias("vehicles"),
                       F.countDistinct("vehicle_id", "trip_id").alias("trips"),
                       F.sum(invalid_timestamp(numeric).cast("long")).alias("invalid_timestamps"),
                       F.sum((F.col("daynum").isNull() | (F.col("daynum") < 1)).cast("long")).alias("invalid_daynum"),
                       F.sum((F.col("latitude").isNotNull() & F.col("longitude").isNotNull()).cast("long")).alias("gps_rows"),
                       F.sum(((F.abs("latitude") > 90) | (F.abs("longitude") > 180)).cast("long")).alias("invalid_gps"),
                       F.percentile_approx("speed_kmh", [0.01, 0.5, 0.95, 0.99], 10000).alias("speed_quantiles")]
        for column in NUMERIC:
            expressions.extend([F.count(column).alias(column + "_available"),
                                F.min(column).alias(column + "_min"),
                                F.max(column).alias(column + "_max"),
                                F.avg(column).alias(column + "_mean"),
                                F.sum((F.col(column) < 0).cast("long")).alias(column + "_negative")])
        report = numeric.agg(*expressions).first().asDict()
        report["spark"] = spark.version
        report["java"] = spark._jvm.java.lang.System.getProperty("java.version")
        report["fuel_missing_rows"] = report["rows"] - report["fuel_lph_available"]
        report["fuel_missing_pct"] = 100 * report["fuel_missing_rows"] / report["rows"]
        report["source_missing_tokens"] = {c: raw.where(F.col(c) == "NaN").count()
                                            for c in ["Fuel Rate[L/hr]", "Vehicle Speed[km/h]"]}
        report["non_numeric_tokens"] = raw.agg(*[
            F.sum((F.col(c).isNotNull() & ~F.col(c).isin("NaN", "") &
                   (F.col(c).try_cast("double").isNull() |
                    F.isnan(F.col(c).try_cast("double")) |
                    (F.abs(F.col(c).try_cast("double")) == float("inf")))).cast("long")).alias(c)
            for c in HEADERS]).first().asDict()
        report["range_flags"] = numeric.agg(
            F.sum(((F.col("battery_soc_pct") < 0) | (F.col("battery_soc_pct") > 100)).cast("long")).alias("battery_soc_outside_0_100"),
            F.sum((F.col("oat_degc") < -273.15).cast("long")).alias("temperature_below_absolute_zero"),
            F.sum(((F.col("vehicle_id") < 0) | (F.col("trip_id") < 0) |
                   (F.col("vehicle_id") != F.floor("vehicle_id")) |
                   (F.col("trip_id") != F.floor("trip_id")) |
                   F.col("vehicle_id").isNull() | F.col("trip_id").isNull()).cast("long")).alias("invalid_vehicle_trip_keys")
        ).first().asDict()
        report["observation_key_duplicates"] = duplicate_counts(numeric, ["vehicle_id", "trip_id", "timestamp_ms"])
        report["exact_record_duplicates"] = duplicate_counts(raw, ["raw_line"])
        window = Window.partitionBy("vehicle_id", "trip_id").orderBy("timestamp_ms")
        intervals = (numeric.select("vehicle_id", "trip_id", "timestamp_ms")
                     .withColumn("interval_ms", F.col("timestamp_ms") - F.lag("timestamp_ms").over(window)))
        report["intervals"] = intervals.agg(F.count("interval_ms").alias("count"),
            F.min("interval_ms").alias("min_ms"), F.max("interval_ms").alias("max_ms"),
            F.avg("interval_ms").alias("mean_ms"),
            F.sum((F.col("interval_ms") == 0).cast("long")).alias("zero_intervals"),
            F.percentile_approx("interval_ms", [0.01, 0.5, 0.95, 0.99], 10000).alias("quantiles_ms")).first().asDict()
        report["interval_modes"] = [r.asDict() for r in intervals.groupBy("interval_ms").count()
                                    .where(F.col("interval_ms").isNotNull()).orderBy(F.desc("count")).limit(10).collect()]
        report["trip_daynum_variability"] = (numeric.groupBy("vehicle_id", "trip_id")
            .agg(F.countDistinct("daynum").alias("n")).agg(F.max("n").alias("max_distinct_daynum_per_trip")).first().asDict())
        specs = []
        report["static_headers"] = {}
        for path in sorted(RAW.glob("*.xlsx")):
            rows = xlsx_rows(path)
            if rows[0].get("A") != "VehId" or rows[0].get("B") not in {"Vehicle Type", "EngineType"}:
                raise ValueError(f"Unexpected static workbook schema: {path}")
            report["static_headers"][path.name] = rows[:2]
            # Actual header positions are verified before invoking this report.
            for row in rows[1:]:
                try:
                    vehicle = float(row.get("A", ""))
                except ValueError:
                    continue
                specs.append((vehicle, row.get("B", "")))
        if specs:
            if len({v for v, _ in specs}) != len(specs):
                raise ValueError("Duplicate vehicle IDs in static workbooks would inflate the join")
            report["static_vehicle_counts"] = {kind: sum(k == kind for _, k in specs)
                                                for kind in sorted({k for _, k in specs})}
            mapping = spark.createDataFrame(specs, "vehicle_id double, engine_type string")
            report["powertrain"] = [r.asDict() for r in numeric.join(mapping, "vehicle_id", "left")
                .groupBy("engine_type").agg(F.count("*").alias("rows"), F.countDistinct("vehicle_id").alias("vehicles"),
                    F.count("fuel_lph").alias("fuel_rows"), F.count("rpm").alias("rpm_rows"),
                    F.count("battery_current_a").alias("battery_current_rows"),
                    F.count("battery_soc_pct").alias("battery_soc_rows"),
                    F.avg("speed_kmh").alias("mean_speed_kmh")).orderBy("engine_type").collect()]
        report["malformed_rows"] = raw.where("is_malformed").count()
        report["inspection_seconds"] = time.perf_counter() - started
        report["project_bytes_after_inspection"] = budget()
        report["peak_project_bytes_observed"] = monitor["peak"]
        if monitor["cancelled"]:
            raise RuntimeError("Inspection cancelled before reaching the 5 GB storage cap")
        (ROOT / "results/day2_statistics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        monitor_stop.set()
        watcher.join(timeout=2)
        spark.stop()


if __name__ == "__main__":
    main()
