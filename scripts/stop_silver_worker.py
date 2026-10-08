"""Stop only this project's active Silver worker for a checkpointed restart."""
import json
import time
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        if process.info["name"] not in {"python.exe", "python"}:
            continue
        command = process.info["cmdline"] or []
        if (any("src/processing/silver_ved.py" == item.replace("\\", "/") for item in command)
            and command and Path(command[0]).resolve().is_relative_to(ROOT)):
            found.append(process)
    if not found:
        print("No project Silver worker running",flush=True)
        return
    if any(p.pid == psutil.Process().pid for p in found):
        raise RuntimeError("Refusing to stop the current process")
    record = {"reason": "unchanged-rule execution tuning with checkpoint reuse", "worker_pids": [p.pid for p in found],
              "attempt_elapsed_seconds": max(time.time()-p.create_time() for p in found)}
    descendants = {p.pid:p for root in found for p in root.children(recursive=True)}
    for process in list(descendants.values()) + found:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    checkpoint = ROOT / "results/day3/silver_quality.json"
    if checkpoint.exists():
        record["completed_files"] = len(json.loads(checkpoint.read_text())["files"])
    history_path = ROOT / "results/day3/silver_initial_attempt.json"
    previous = json.loads(history_path.read_text()) if history_path.exists() else None
    attempts = previous.get("attempts", [previous]) if previous else []
    attempts.append(record)
    history_path.write_text(json.dumps({"attempts": attempts},indent=2),encoding="utf-8")
    print(json.dumps(record),flush=True)


if __name__ == "__main__":
    main()
