"""Sequential validation, ingestion and inspection in one approved invocation."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    for script in ("scripts/validate_day2.py", "src/ingestion/ingest_ved.py",
                   "src/ingestion/inspect_ved.py"):
        print(f"Running {script}", flush=True)
        result = subprocess.run([sys.executable, "-u", script], cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
