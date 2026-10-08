import csv
import io
from pathlib import Path
import pyarrow.parquet as pq
import pytest
from pyspark.sql import functions as F
from src.ingestion.ingest_ved import (HEADERS, SOURCE_SCHEMA, ARROW_SCHEMA,
    spark_session, write_bronze, read_bronze, inspect_source, sha256)
from src.ingestion.inspect_ved import numeric_view, invalid_timestamp, duplicate_counts
from src.ingestion.inspect_ved import xlsx_rows


@pytest.fixture(scope="session")
def spark():
    session = spark_session()
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def fixture_file(tmp_path, rows):
    path = tmp_path / "VED_171101_week.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return path


def row(timestamp="0", fuel="NaN"):
    return ["1.5", "8", "706", timestamp, "42.2", "-83.7", "40", "NaN",
            "1000", "30", "-2", fuel] + ["NaN"] * 10


def test_schema_matches_observed_header():
    assert len(HEADERS) == 22
    assert HEADERS[10] == "OAT[DegC]"
    assert SOURCE_SCHEMA.names == HEADERS
    assert all(field.dataType.simpleString() == "string" for field in SOURCE_SCHEMA)


def test_input_parsing_preserves_tokens(spark, tmp_path):
    original = row("200", "0.00")
    original[10] = " -2 "
    source = fixture_file(tmp_path, [original])
    destination = tmp_path / "bronze/part.parquet"
    result = write_bronze(spark, source, destination)
    table = pq.read_table(destination)
    assert result["source_rows"] == result["bronze_rows"] == 1
    assert table["Fuel Rate[L/hr]"].to_pylist() == ["0.00"]
    assert table["OAT[DegC]"].to_pylist() == [" -2 "]
    assert table["MAF[g/sec]"].to_pylist() == ["NaN"]
    assert not table["is_malformed"][0].as_py()


def test_malformed_records_are_retained(spark, tmp_path):
    source = fixture_file(tmp_path, [row(), ["broken", "8"], row() + ["extra"], []])
    destination = tmp_path / "bronze/part.parquet"
    result = write_bronze(spark, source, destination)
    assert result["source_rows"] == result["bronze_rows"] == 4
    assert result["malformed_rows"] == 3
    assert len(pq.read_table(destination)["raw_line"]) == 4


def test_duplicates_are_identified_and_preserved(spark, tmp_path):
    source = fixture_file(tmp_path, [row(), row(), row("100")])
    write_bronze(spark, source, tmp_path / "bronze/part.parquet")
    frame = read_bronze(spark, tmp_path / "bronze")
    assert frame.count() == 3
    assert duplicate_counts(frame, ["raw_line"]) == {"groups": 1, "excess_rows": 1}
    assert duplicate_counts(numeric_view(frame), ["vehicle_id", "trip_id", "timestamp_ms"])["excess_rows"] == 1


def test_timestamp_validity_without_imputation(spark, tmp_path):
    source = fixture_file(tmp_path, [row("0"), row("200"), row("-1"), row("abc"), row("1.5")])
    write_bronze(spark, source, tmp_path / "bronze/part.parquet")
    numeric = numeric_view(read_bronze(spark, tmp_path / "bronze"))
    assert numeric.where(invalid_timestamp(numeric)).count() == 3
    assert numeric.where(F.col("fuel_lph").isNotNull()).count() == 0


def test_bronze_readable_by_spark_and_arrow(spark, tmp_path):
    source = fixture_file(tmp_path, [row(), row("200")])
    destination = tmp_path / "bronze/part.parquet"
    write_bronze(spark, source, destination)
    assert pq.read_schema(destination).equals(ARROW_SCHEMA, check_metadata=False)
    frame = read_bronze(spark, tmp_path / "bronze")
    assert frame.count() == 2
    assert frame.schema["Timestamp(ms)"].dataType.simpleString() == "string"


def test_repeated_run_is_reproducible(spark, tmp_path):
    source = fixture_file(tmp_path, [row("200"), row(), row()])
    destination = tmp_path / "bronze/part.parquet"
    first = write_bronze(spark, source, destination)
    first_hash = sha256(destination)
    second = write_bronze(spark, source, destination)
    assert first_hash == sha256(destination)
    assert first["bronze_rows"] == second["bronze_rows"] == 3
    assert len(list(destination.parent.glob("*.parquet"))) == 1


def test_unexpected_schema_fails_explicitly(tmp_path):
    source = fixture_file(tmp_path, [row()])
    source.write_text(source.read_text().replace("OAT[DegC]", "Outside Air Temperature[DegC]"))
    with pytest.raises(ValueError, match="header mismatch"):
        inspect_source(source)


def test_repeated_header_cannot_silently_drop_records(spark, tmp_path):
    source = fixture_file(tmp_path, [row(), HEADERS])
    with pytest.raises(RuntimeError, match="reconciliation failed"):
        write_bronze(spark, source, tmp_path / "bronze/part.parquet")


def test_quoted_field_preserves_embedded_comma_and_quote(spark, tmp_path):
    original = row()
    original[10] = 'sensor, "value"'
    source = fixture_file(tmp_path, [original])
    destination = tmp_path / "bronze/part.parquet"
    result = write_bronze(spark, source, destination)
    assert result["malformed_rows"] == 0
    assert pq.read_table(destination)["OAT[DegC]"].to_pylist() == ['sensor, "value"']


def test_static_xlsx_shared_strings_and_sparse_cells(tmp_path):
    import zipfile
    path = tmp_path / "static.xlsx"
    namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{namespace}"><si><t>VehId</t></si><si><t>Vehicle Type</t></si><si><t>HEV</t></si></sst>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row><c r="A2"><v>5</v></c><c r="B2" t="s"><v>2</v></c><c r="G2"><v>3500</v></c></row></sheetData></worksheet>')
    assert xlsx_rows(path) == [{"A": "VehId", "B": "Vehicle Type"}, {"A": "5", "B": "HEV", "G": "3500"}]
