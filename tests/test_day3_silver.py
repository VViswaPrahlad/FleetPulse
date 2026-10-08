from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.ingestion.ingest_ved import ARROW_SCHEMA, spark_session, sha256
from src.processing.silver_ved import (FIELDS, INPUT_COLUMNS, INPUT_SCHEMA, SILVER_SCHEMA, clean_frame,
    retained_frame, rejected_frame, process_file, read_silver)


@pytest.fixture(scope="session")
def spark():
    value = spark_session()
    value.sparkContext.setLogLevel("ERROR")
    yield value
    value.stop()


def row(**changes):
    result = {source: "NaN" for source in FIELDS}
    result.update({"DayNum":"1.5", "VehId":"8", "Trip":"706", "Timestamp(ms)":"0",
                   "Latitude[deg]":"42.2", "Longitude[deg]":"-83.7", "Vehicle Speed[km/h]":"40",
                   "source_file":"VED_171101_week.csv", "source_week":"2017-11-01",
                   "is_malformed":False, "malformed_reason":None})
    result.update(changes)
    return result


def frame(spark, rows):
    pandas = pd.DataFrame(rows, columns=INPUT_COLUMNS)
    pandas["bronze_row_index"] = np.arange(len(pandas),dtype=np.int64)
    return clean_frame(spark.createDataFrame(pandas,INPUT_SCHEMA), "source_month=2017-11/test.parquet", {8:"ICE"})


def test_schema_names_types_and_audit_columns():
    assert len(FIELDS) == 22
    assert SILVER_SCHEMA.field("vehicle_id").type == pa.int64()
    assert SILVER_SCHEMA.field("elapsed_ms").type == pa.int64()
    assert SILVER_SCHEMA.field("source_week").type == pa.date32()
    assert SILVER_SCHEMA.field("battery_soc_source_pct").type == pa.float64()
    assert SILVER_SCHEMA.field("quality_flags").type == pa.list_(pa.string())


def test_nan_becomes_null_and_zero_stays_observed(spark):
    value = retained_frame(frame(spark,[row(**{"Fuel Rate[L/hr]":"0", "MAF[g/sec]":"NaN"})])).first()
    assert value.fuel_rate_lph == 0
    assert value.maf_g_s is None
    assert "missing_fuel_rate_lph" not in value.quality_flags


def test_signed_measurements_are_not_blanket_rejected(spark):
    value = retained_frame(frame(spark,[row(**{"HV Battery Current[A]":"-22", "OAT[DegC]":"-10",
                                             "Short Term Fuel Trim Bank 1[%]":"-3.125"})])).first()
    assert value.longitude_deg == -83.7
    assert value.hv_battery_current_a == -22
    assert value.outside_air_temp_c == -10
    assert value.short_fuel_trim_b1_pct == -3.125


def test_negative_timestamp_is_quarantined_not_rebased(spark):
    cleaned = frame(spark,[row(**{"Timestamp(ms)":"-100"}),row(**{"Timestamp(ms)":"0"})])
    rejected = rejected_frame(cleaned).collect()
    assert len(rejected) == 1
    assert rejected[0].elapsed_ms == -100
    assert rejected[0].exclusion_reasons == ["negative_elapsed_ms"]
    assert retained_frame(cleaned).first().elapsed_ms == 0


def test_soc_precision_clip_preserves_source_value(spark):
    value = retained_frame(frame(spark,[row(**{"HV Battery SOC[%]":"100.000030518"})])).first()
    assert value.battery_soc_pct == 100
    assert value.battery_soc_source_pct == pytest.approx(100.000030518)
    assert "soc_precision_clipped" in value.quality_flags


def test_gross_soc_is_null_without_fabrication(spark):
    value = retained_frame(frame(spark,[row(**{"HV Battery SOC[%]":"101"})])).first()
    assert value.battery_soc_pct is None
    assert value.battery_soc_source_pct == 101
    assert "soc_out_of_range" in value.quality_flags


def test_irregular_gaps_are_flagged_without_resampling(spark):
    rows = retained_frame(frame(spark,[row(), row(**{"Timestamp(ms)":"100"}), row(**{"Timestamp(ms)":"5000"})])).collect()
    assert [r.elapsed_ms for r in rows] == [0,100,5000]
    assert rows[-1].sampling_gap_ms == 4900
    assert rows[-1].gap_gt_2000ms
    assert "irregular_gap_gt_2s" in rows[-1].quality_flags


def test_invalid_optional_cells_are_null_and_flagged(spark):
    value = retained_frame(frame(spark,[row(**{"Vehicle Speed[km/h]":"-1", "Fuel Rate[L/hr]":"unknown",
                                             "Latitude[deg]":"91", "Engine RPM[RPM]":"Infinity"})])).first()
    assert value.speed_kmh is None and value.fuel_rate_lph is None
    assert value.latitude_deg is None and value.engine_rpm is None
    assert {"negative_speed_kmh", "invalid_numeric_fuel_rate_lph", "invalid_latitude", "invalid_numeric_engine_rpm"} <= set(value.quality_flags)


def test_invalid_keys_time_and_malformed_rows_reconcile(spark):
    cleaned = frame(spark,[row(),row(**{"VehId":"1.5"}),row(**{"Timestamp(ms)":"1.5"}),
                           row(**{"is_malformed":True}),row(**{"source_week":"bad"})])
    assert retained_frame(cleaned).count() == 1
    assert rejected_frame(cleaned).count() == 4


def test_duplicates_are_retained_with_distinct_source_indexes(spark):
    rows = retained_frame(frame(spark,[row(),row()])).collect()
    assert len(rows) == 2 and [r.bronze_row_index for r in rows] == [0,1]
    assert all("duplicate_observation_key" in r.quality_flags for r in rows)


def test_high_load_is_advisory_not_clipped(spark):
    value = retained_frame(frame(spark,[row(**{"Absolute Load[%]":"22463.5293"})])).first()
    assert value.absolute_load_pct == pytest.approx(22463.5293)
    assert "load_above_100_advisory" in value.quality_flags


def test_provenance_reconciliation_readability_and_repeat(spark,tmp_path):
    records = [row(),row(**{"Timestamp(ms)":"-100"}),row(**{"Timestamp(ms)":"100","HV Battery SOC[%]":"100.000030518"})]
    for index,value in enumerate(records):
        value["raw_line"] = f"fixture-{index}"
    source = tmp_path / "bronze.parquet"
    pq.write_table(pa.Table.from_pylist(records,schema=ARROW_SCHEMA),source)
    source_hash = sha256(source)
    destination,rejected = tmp_path / "silver/part.parquet",tmp_path / "quarantine/part.parquet"
    first = process_file(spark,source,destination,rejected,{8:"ICE"})
    assert first["input_rows"] == first["retained_rows"] + first["excluded_rows"] == 3
    assert first["retained_rows"] == 2 and first["excluded_rows"] == 1
    assert read_silver(spark,destination.parent).count() == 2
    assert read_silver(spark,rejected.parent).count() == 1
    assert set(pq.read_table(destination)["bronze_row_index"].to_pylist()) | set(pq.read_table(rejected)["bronze_row_index"].to_pylist()) == {0,1,2}
    assert sha256(source) == source_hash
    hashes = (sha256(destination),sha256(rejected))
    process_file(spark,source,destination,rejected,{8:"ICE"})
    assert hashes == (sha256(destination),sha256(rejected))
