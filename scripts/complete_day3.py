"""Validate Day 3 rules, then build Silver from the already analyzed Bronze."""
import subprocess
import sys
from src.ingestion.ingest_ved import ROOT


def main():
    result = subprocess.run([sys.executable,"-u","scripts/validate_day3.py"],cwd=ROOT)
    if result.returncode:
        return result.returncode
    # Tests and full pipeline use separate JVM lifetimes to release fixture memory.
    return subprocess.run([sys.executable,"-u","src/processing/silver_ved.py"],cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
