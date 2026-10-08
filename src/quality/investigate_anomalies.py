"""Focused Bronze diagnostics for Silver decisions; no source mutation."""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from src.ingestion.ingest_ved import ROOT, OUTPUT


def main():
    started = time.perf_counter()
    soc_rows, negative_rows, load_counts = [], [], {"above_100": 0, "above_200": 0, "above_1000": 0}
    for path in sorted(OUTPUT.rglob("*.parquet")):
        frame = pq.read_table(path, columns=["VehId", "Trip", "Timestamp(ms)", "HV Battery SOC[%]", "Absolute Load[%]"]).to_pandas()
        soc = pd.to_numeric(frame["HV Battery SOC[%]"], errors="coerce")
        elapsed = pd.to_numeric(frame["Timestamp(ms)"], errors="coerce")
        load = pd.to_numeric(frame["Absolute Load[%]"], errors="coerce")
        for threshold in (100, 200, 1000):
            load_counts[f"above_{threshold}"] += int((load > threshold).sum())
        for index in np.flatnonzero(soc.to_numpy() > 100):
            soc_rows.append({"bronze_file": path.relative_to(OUTPUT).as_posix(), "bronze_row_index": int(index),
                             "vehicle_id": int(frame.iloc[index]["VehId"]), "trip_id": int(frame.iloc[index]["Trip"]),
                             "soc_source_token": frame.iloc[index]["HV Battery SOC[%]"], "soc_value": float(soc.iloc[index])})
        for index in np.flatnonzero(elapsed.to_numpy() < 0):
            negative_rows.append({"bronze_file": path.relative_to(OUTPUT).as_posix(), "bronze_row_index": int(index),
                                  "vehicle_id": int(frame.iloc[index]["VehId"]), "trip_id": int(frame.iloc[index]["Trip"]),
                                  "elapsed_source_token": frame.iloc[index]["Timestamp(ms)"], "elapsed_ms": float(elapsed.iloc[index])})
    directory = ROOT / "results/day3"
    pd.DataFrame(soc_rows).to_csv(directory / "soc_overshoots.csv", index=False)
    pd.DataFrame(negative_rows).to_csv(directory / "negative_timestamp_rows.csv", index=False)
    soc_frame, negative_frame = pd.DataFrame(soc_rows), pd.DataFrame(negative_rows)
    report = {"soc_above_100_rows": len(soc_rows), "soc_above_100_min": float(soc_frame.soc_value.min()),
              "soc_above_100_max": float(soc_frame.soc_value.max()),
              "soc_above_100_tokens": soc_frame.soc_source_token.value_counts().to_dict(),
              "soc_affected_vehicles": int(soc_frame.vehicle_id.nunique()),
              "soc_affected_trips": len(soc_frame[["vehicle_id","trip_id"]].drop_duplicates()),
              "soc_above_100_001_rows": int((soc_frame.soc_value > 100.001).sum()),
              "negative_timestamp_rows": len(negative_rows), "negative_timestamp_min_ms": float(negative_frame.elapsed_ms.min()),
              "negative_timestamp_max_ms": float(negative_frame.elapsed_ms.max()),
              "negative_timestamp_vehicles": int(negative_frame.vehicle_id.nunique()),
              "negative_timestamp_trips": len(negative_frame[["vehicle_id","trip_id"]].drop_duplicates()),
              "load_advisory_counts": load_counts, "elapsed_seconds": time.perf_counter()-started}
    (directory / "anomaly_investigation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)


if __name__ == "__main__":
    main()
