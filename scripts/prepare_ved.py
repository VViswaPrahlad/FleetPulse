"""Bounded extraction and observed header inspection; no Spark required."""
import csv
import json
import shutil
from pathlib import Path
import py7zr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ved"
STAGE = ROOT / "data/tmp/ved/part1"


def main():
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["sources"][0]
    if entry.get("integrity") != "all member CRCs passed":
        raise RuntimeError("Archive integrity must be verified before extraction")
    size = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
    if size + entry["expanded_bytes"] + 1_500_000_000 >= 5_000_000_000:
        raise RuntimeError("Extraction would exceed reserved project budget")
    if shutil.disk_usage(ROOT).free < entry["expanded_bytes"] + 1_500_000_000:
        raise RuntimeError("Insufficient free disk")
    STAGE.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(RAW / entry["filename"]) as archive:
        archive.extractall(path=STAGE)
    for file in sorted(STAGE.glob("*.csv")):
        with file.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            sample = [next(reader) for _ in range(3)]
        print(json.dumps({"file": file.name, "header": header, "sample": sample}), flush=True)


if __name__ == "__main__":
    main()
