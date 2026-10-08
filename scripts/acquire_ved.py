"""Acquire immutable VED sources; validate size, CRC and budget before extraction."""
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import py7zr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ved"
CAP = 5_000_000_000


def footprint():
    return sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())


def download(url, path, maximum):
    with urlopen(Request(url, method="HEAD"), timeout=60) as response:
        expected = int(response.headers["Content-Length"])
    additional = 0 if path.exists() else expected
    if expected > maximum or footprint() + additional > CAP:
        raise RuntimeError(f"Unexpected download size/budget: {expected}")
    if not path.exists():
        partial = path.with_suffix(path.suffix + ".partial")
        total = 0
        with urlopen(url, timeout=120) as response, partial.open("wb") as out:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > expected:
                    raise RuntimeError("Download exceeds declared size")
                out.write(block)
        if total != expected:
            raise RuntimeError("Truncated download")
        partial.rename(path)
    if path.stat().st_size != expected:
        raise RuntimeError("Existing source size differs from remote")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"url": url, "filename": path.name, "bytes": expected, "sha256": digest}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    with urlopen("https://api.github.com/repos/gsoh/VED/commits/master", timeout=60) as response:
        commit = json.load(response)["sha"]
    base = f"https://raw.githubusercontent.com/gsoh/VED/{commit}/"
    manifest = {"commit": commit, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "sources": [], "budget_bytes": CAP}
    archives = []
    for part in (1, 2):
        name = f"VED_DynamicData_Part{part}.7z"
        path = RAW / name
        entry = download(base + "Data/" + name, path, 120_000_000)
        with py7zr.SevenZipFile(path) as archive:
            members = archive.list()
            entry["expanded_bytes"] = sum(m.uncompressed or 0 for m in members)
            entry["members"] = [{"name": m.filename, "bytes": m.uncompressed,
                                  "crc32": m.crc32} for m in members if not m.is_directory]
            for member in members:
                target = (RAW / "dynamic" / member.filename).resolve()
                if not target.is_relative_to((RAW / "dynamic").resolve()):
                    raise RuntimeError("Unsafe archive member")
        manifest["sources"].append(entry)
        archives.append(path)
        (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(entry), flush=True)
    # Extraction is delegated to the ingestion pipeline, one archive at a time.
    expanded = sum(e["expanded_bytes"] for e in manifest["sources"])
    staged = ROOT / "data/tmp/ved"
    staging_bytes = sum(p.stat().st_size for p in staged.rglob("*.csv")) if staged.exists() else 0
    manifest["bounded_peak_estimate_bytes"] = footprint() - staging_bytes + max(e["expanded_bytes"] for e in manifest["sources"]) + 1_500_000_000
    manifest["disk_free_before_extraction_bytes"] = shutil.disk_usage(ROOT).free
    if manifest["bounded_peak_estimate_bytes"] >= CAP:
        raise RuntimeError("Bounded extraction estimate exceeds project cap")
    if shutil.disk_usage(ROOT).free < max(e["expanded_bytes"] for e in manifest["sources"]) + 1_500_000_000:
        raise RuntimeError("Insufficient free disk for bounded staging")
    for entry, path in zip(manifest["sources"], archives):
        started = time.perf_counter()
        with py7zr.SevenZipFile(path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Archive integrity check failed")
        entry["integrity"] = "all member CRCs passed"
        entry["integrity_seconds"] = time.perf_counter() - started
        print(f"CRC verified: {path.name}", flush=True)
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for name in ("VED_Static_Data_ICE&HEV.xlsx", "VED_Static_Data_PHEV&EV.xlsx"):
        manifest["sources"].append(download(base + "Data/" + name.replace("&", "%26"), RAW / name, 100_000))
    manifest["sources"].append(download(base + "LICENSE", RAW / "LICENSE", 100_000))
    manifest["project_bytes_after_acquisition"] = footprint()
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"expanded_bytes": expanded, "project_bytes": footprint()}), flush=True)


if __name__ == "__main__":
    main()
