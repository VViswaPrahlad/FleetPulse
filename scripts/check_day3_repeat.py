"""Verify idempotent Silver invocation and immutable Bronze without reprocessing."""
import json
import subprocess
import sys
import time
from src.ingestion.ingest_ved import ROOT, sha256
from src.processing.silver_ved import SILVER, QUARANTINE


def main():
    checkpoint = ROOT / "results/day3/silver_quality.json"
    original_text = checkpoint.read_text()
    original = json.loads(original_text)
    assert original["complete"]
    (ROOT / "results/day3/silver_full_run.json").write_text(original_text,encoding="utf-8")
    before = {str(p.relative_to(ROOT)):sha256(p) for root in [SILVER,QUARANTINE] for p in root.rglob("*.parquet")}
    started = time.perf_counter()
    result = subprocess.run([sys.executable,"-u","src/processing/silver_ved.py"],cwd=ROOT)
    if result.returncode:
        raise RuntimeError("Idempotence verification failed")
    repeated = json.loads(checkpoint.read_text())
    after = {str(p.relative_to(ROOT)):sha256(p) for root in [SILVER,QUARANTINE] for p in root.rglob("*.parquet")}
    assert before == after and all(r["cached"] for r in repeated["files"])
    assert repeated["retained_rows"] == original["retained_rows"]
    assert repeated["excluded_rows"] == original["excluded_rows"]
    report = {"passed":True,"unchanged_output_files":len(before),"cached_weekly_inputs":len(repeated["files"]),
              "retained_rows":repeated["retained_rows"],"excluded_rows":repeated["excluded_rows"],
              "bronze_unchanged":repeated["bronze_unchanged"],"elapsed_seconds":time.perf_counter()-started}
    (ROOT / "results/day3/reproducibility.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    checkpoint.write_text(original_text,encoding="utf-8")
    print(json.dumps(report),flush=True)


if __name__ == "__main__":
    main()
