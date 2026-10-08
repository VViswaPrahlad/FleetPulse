"""Prove unchanged rules, then checkpoint-restart only the active Silver job."""
import subprocess
import sys
from src.ingestion.ingest_ved import ROOT


def main():
    for script in ["scripts/validate_day3.py","scripts/audit_silver_equivalence.py",
                   "scripts/stop_silver_worker.py","src/processing/silver_ved.py"]:
        result = subprocess.run([sys.executable,"-u",script],cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
