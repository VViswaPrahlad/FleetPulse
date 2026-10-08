"""Verify a full repeat invocation leaves all 54 Bronze file hashes unchanged."""
import json
import subprocess
import sys
import time
from pathlib import Path
from src.ingestion.ingest_ved import ROOT, OUTPUT, sha256


def main():
    report_path = ROOT / "results/day2_ingestion.json"
    original_text = report_path.read_text(encoding="utf-8")
    original = json.loads(original_text)
    if not original["complete"]:
        raise RuntimeError("First ingestion is incomplete")
    (ROOT / "results/day2_ingestion_full.json").write_text(original_text, encoding="utf-8")
    before = {str(p.relative_to(OUTPUT)): sha256(p) for p in OUTPUT.rglob("*.parquet")}
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-u", "src/ingestion/ingest_ved.py"], cwd=ROOT)
    if result.returncode:
        raise RuntimeError("Repeat ingestion failed")
    repeated = json.loads(report_path.read_text(encoding="utf-8"))
    after = {str(p.relative_to(OUTPUT)): sha256(p) for p in OUTPUT.rglob("*.parquet")}
    assert before == after
    assert repeated["bronze_rows"] == original["bronze_rows"]
    assert all(f["cached"] for f in repeated["files"])
    report = {"passed": True, "unchanged_files": len(before), "bronze_rows": repeated["bronze_rows"],
              "repeat_runtime_seconds": time.perf_counter() - started,
              "mode": "full invocation with validated content-hash cache; no re-extraction",
              "fresh_recompute_reproducibility": "verified separately by small Pytest fixture"}
    (ROOT / "results/day2_reproducibility.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Keep the measured original full-ingestion runtime as the main checkpoint.
    report_path.write_text(original_text, encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
