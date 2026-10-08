"""Compare optimized execution with a previously published real weekly file."""
import json
import tempfile
from pathlib import Path
from src.ingestion.ingest_ved import ROOT, OUTPUT, spark_session, sha256
from src.processing.silver_ved import SILVER, QUARANTINE, process_file
from src.quality.fuel_feasibility import static_types


def main():
    previous = json.loads((ROOT / "results/day3/silver_quality.json").read_text())
    baseline = previous["files"][0]
    relative = Path(baseline["bronze_file"])
    spark = spark_session()
    spark.sparkContext.setLogLevel("ERROR")
    spark.conf.set("spark.sql.codegen.maxFields", "200")
    try:
        with tempfile.TemporaryDirectory(prefix="day3-equivalence-",dir=ROOT / "data/tmp") as directory:
            destination = Path(directory).resolve()
            assert destination.is_relative_to(ROOT.resolve())
            first,second = destination / "silver.parquet",destination / "quarantine.parquet"
            result = process_file(spark,OUTPUT/relative,first,second,static_types())
            assert sha256(first) == baseline["silver_sha256"] == sha256(SILVER/relative)
            assert sha256(second) == baseline["quarantine_sha256"] == sha256(QUARANTINE/relative)
            report = {"passed":True,"bronze_file":relative.as_posix(),"rows":result["input_rows"],
                      "recompute_seconds":result["elapsed_seconds"],"both_output_hashes_identical":True}
            (ROOT / "results/day3/execution_equivalence.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
            print(json.dumps(report),flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
