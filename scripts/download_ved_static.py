"""Download only the approved author-repository static workbooks and license."""
import json
from acquire_ved import RAW, download


def main():
    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = f"https://raw.githubusercontent.com/gsoh/VED/{manifest['commit']}/"
    for name in ("VED_Static_Data_ICE&HEV.xlsx", "VED_Static_Data_PHEV&EV.xlsx", "LICENSE"):
        suffix = "LICENSE" if name == "LICENSE" else "Data/" + name.replace("&", "%26")
        entry = download(base + suffix, RAW / name, 100_000)
        manifest["sources"] = [s for s in manifest["sources"] if s["filename"] != name] + [entry]
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(entry), flush=True)


if __name__ == "__main__":
    main()
