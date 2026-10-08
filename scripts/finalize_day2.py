"""Final tests, repeat-run validation, dependency check and measured docs."""
import subprocess
import sys
from src.ingestion.ingest_ved import ROOT


def main():
    commands = [[sys.executable, "-u", "scripts/validate_day2.py"],
                [sys.executable, "-u", "scripts/check_day2_reproducibility.py"],
                [sys.executable, "-m", "pip", "check"],
                [sys.executable, "-u", "scripts/render_day2_report.py"]]
    for command in commands:
        print("Running " + " ".join(command[1:]), flush=True)
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
