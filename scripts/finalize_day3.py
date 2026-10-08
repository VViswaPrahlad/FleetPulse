"""Final cached-repeat verification and measured Day 3 documentation."""
import subprocess
import sys
from src.ingestion.ingest_ved import ROOT

if __name__ == "__main__":
    for script in ["scripts/check_day3_repeat.py","scripts/render_day3_report.py"]:
        result = subprocess.run([sys.executable,"-u",script],cwd=ROOT)
        if result.returncode:
            raise SystemExit(result.returncode)
