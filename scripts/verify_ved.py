"""Verify retained official VED archives without extracting any files."""
import hashlib
import json
import shutil
import time
from pathlib import Path
import py7zr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ved"


def main():
    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    initial = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
    free = shutil.disk_usage(ROOT).free
    dynamic = [s for s in manifest["sources"] if s["filename"].endswith(".7z")]
    largest = max(s["expanded_bytes"] for s in dynamic)
    staged = ROOT / "data/tmp/ved"
    initial -= sum(p.stat().st_size for p in staged.rglob("*.csv")) if staged.exists() else 0
    # One archive staged at a time, 1 GB output allowance and 500 MB scratch.
    peak = initial + largest + 1_000_000_000 + 500_000_000
    if peak >= 5_000_000_000 or free < largest + 1_500_000_000:
        raise RuntimeError(f"Insufficient bounded extraction budget: {peak=}, {free=}")
    manifest["bounded_peak_estimate_bytes"] = peak
    manifest["disk_free_before_extraction_bytes"] = free
    for entry in dynamic:
        path = RAW / entry["filename"]
        if path.stat().st_size != entry["bytes"]:
            raise RuntimeError("Archive size mismatch")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                raise RuntimeError("Archive hash mismatch")
        started = time.perf_counter()
        with py7zr.SevenZipFile(path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Member CRC failure")
        entry["integrity"] = "all member CRCs passed"
        entry["integrity_seconds"] = time.perf_counter() - started
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps({"archive": path.name, "integrity": entry["integrity"],
                          "seconds": entry["integrity_seconds"], "bounded_peak_bytes": peak,
                          "free_bytes": free}), flush=True)


if __name__ == "__main__":
    main()
