"""Measure label support directly from Bronze; no training or target change.

Conservative windows have measured endpoints on a 1-second anchor grid,
no missing observations inside the span, and bounded adjacent sample gaps.
Numerical integration uses only observed endpoints. No samples are filled.
"""
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.ingestion.ingest_ved import ROOT, OUTPUT, RAW, sha256, footprint
from src.ingestion.inspect_ved import xlsx_rows

GAPS_MS = (1000, 2000, 5000, 10000)
HORIZON_MS = 60_000
COLUMNS = ["VehId", "Trip", "Timestamp(ms)", "Fuel Rate[L/hr]",
           "Vehicle Speed[km/h]", "HV Battery Current[A]", "is_malformed"]


def static_types():
    result = {}
    for path in sorted(RAW.glob("*.xlsx")):
        rows = xlsx_rows(path)
        if rows[0].get("A") != "VehId" or rows[0].get("B") not in {"Vehicle Type", "EngineType"}:
            raise ValueError("Static schema changed")
        for row in rows[1:]:
            vehicle = int(row["A"])
            if vehicle in result:
                raise ValueError("Duplicate static ID")
            result[vehicle] = row["B"]
    return result


def window_support(times, values, max_gap_ms=2000, input_valid=None, nonnegative=True):
    """Exact-boundary 60-second targets and 60+60-second paired windows.

    Inputs must be sorted. Missing/invalid rows and duplicate timestamps break
    continuity rather than being removed and bridged. Returned labels are
    diagnostic integrals, not a persisted training table.
    """
    times, values = np.asarray(times, dtype=float), np.asarray(values, dtype=float)
    n = len(times)
    if n == 0:
        return {"target_windows": 0, "paired_windows": 0, "nonoverlap_pairs": 0,
                "segments": 0, "covered_seconds": 0.0, "longest_seconds": 0.0,
                "labels": np.empty(0)}
    dt = np.diff(times, prepend=times[0])
    duplicate = np.zeros(n, dtype=bool)
    duplicate[1:] |= dt[1:] == 0
    duplicate[:-1] |= dt[1:] == 0
    valid_time = np.isfinite(times) & (times >= 0) & (times == np.floor(times)) & ~duplicate
    valid = valid_time & np.isfinite(values)
    if nonnegative:
        valid &= values >= 0
    edges = np.isfinite(dt) & (dt > 0) & (dt <= max_gap_ms)
    edges[0] = False
    joined = edges & valid & np.r_[False, valid[:-1]]
    starts = np.flatnonzero(valid & ~joined)
    ends = np.flatnonzero(valid & ~np.r_[joined[1:], False])
    durations = times[ends] - times[starts]
    bad_values = np.r_[0, np.cumsum(~valid)]
    bad_edges = np.r_[0, np.cumsum(~edges)]
    anchors = np.flatnonzero(valid_time & (times % 1000 == 0))
    future = np.searchsorted(times, times[anchors] + HORIZON_MS)
    found = future < n
    future = np.minimum(future, n - 1)
    found &= times[future] == times[anchors] + HORIZON_MS

    def clear_span(start, end):
        return ((bad_values[end + 1] - bad_values[start]) == 0) & (
            (bad_edges[end + 1] - bad_edges[start + 1]) == 0)

    target = found & clear_span(anchors, future)
    past = np.searchsorted(times, times[anchors] - HORIZON_MS)
    past = np.minimum(past, n - 1)
    paired = target & (times[past] == times[anchors] - HORIZON_MS) & clear_span(past, future)
    if input_valid is not None:
        bad_input = np.r_[0, np.cumsum(~np.asarray(input_valid, dtype=bool))]
        paired &= (bad_input[anchors + 1] - bad_input[past]) == 0
    selected = anchors[paired]
    nonoverlap = 0
    last = -np.inf
    for prediction in times[selected]:
        if prediction - last >= 2 * HORIZON_MS:
            nonoverlap += 1
            last = prediction
    areas = np.zeros(n)
    indexes = np.flatnonzero(joined)
    areas[indexes] = 0.5 * (values[indexes - 1] + values[indexes]) * dt[indexes] / 3_600_000
    integral = np.r_[0.0, np.cumsum(areas)]
    labels = integral[future[paired] + 1] - integral[anchors[paired] + 1]
    return {"target_windows": int(target.sum()), "paired_windows": int(paired.sum()),
            "nonoverlap_pairs": nonoverlap, "segments": len(starts),
            "covered_seconds": float(np.sum(durations) / 1000),
            "longest_seconds": float(np.max(durations, initial=0) / 1000), "labels": labels}


def main():
    started = time.perf_counter()
    types = static_types()
    files = sorted(OUTPUT.rglob("*.parquet"))
    bronze_hashes = {p.relative_to(OUTPUT).as_posix(): sha256(p) for p in files}
    last_file, source_rows, trip_files = {}, defaultdict(int), defaultdict(int)
    for index, path in enumerate(files):
        keys = pq.read_table(path, columns=["VehId", "Trip"]).to_pandas()
        for key, count in keys.groupby(["VehId", "Trip"], sort=False).size().items():
            key = tuple(map(int, key))
            last_file[key] = index
            source_rows[key] += int(count)
            trip_files[key] += 1
    pending, trips = {}, []
    labels_by_type = defaultdict(list)
    modes = defaultdict(lambda: {"target_windows": 0, "paired_windows": 0, "nonoverlap_pairs": 0,
                                  "vehicles": set(), "trips": 0})
    alternatives = {name: {"paired_windows": 0, "nonoverlap_pairs": 0, "vehicles": set(), "trips": 0}
                    for name in ("speed", "battery_current")}
    negative_records, fuel_records = [], []
    for index, path in enumerate(files):
        frame = pq.read_table(path, columns=COLUMNS).to_pandas()
        for column in COLUMNS[:-1]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame.sort_values(["VehId", "Trip", "Timestamp(ms)"], inplace=True, kind="stable", na_position="last")
        for key, group in frame.groupby(["VehId", "Trip"], sort=False):
            key = tuple(map(int, key))
            if key in pending:
                group = pd.concat([pending.pop(key), group], ignore_index=True)
                group.sort_values("Timestamp(ms)", inplace=True, kind="stable", na_position="last")
            if last_file[key] != index:
                pending[key] = group.copy()
                continue
            ts = group["Timestamp(ms)"].to_numpy(dtype=float)
            speed = group["Vehicle Speed[km/h]"].to_numpy(dtype=float)
            fuel = group["Fuel Rate[L/hr]"].to_numpy(dtype=float)
            malformed = group["is_malformed"].to_numpy(dtype=bool)
            fuel = np.where(malformed, np.nan, fuel)
            input_valid = np.isfinite(speed) & (speed >= 0) & ~malformed
            record = {"vehicle_id": key[0], "trip_id": key[1], "engine_type": types.get(key[0], "UNKNOWN"),
                      "rows": len(group), "fuel_rows": int(np.isfinite(fuel).sum()),
                      "fuel_fraction": float(np.isfinite(fuel).sum()/len(group)),
                      "negative_timestamp_rows": int((ts < 0).sum())}
            if record["negative_timestamp_rows"]:
                negative_records.append({k:record[k] for k in ["vehicle_id", "trip_id", "engine_type", "rows", "negative_timestamp_rows"]})
            observed_fuel_ts = ts[np.isfinite(fuel) & np.isfinite(ts) & (ts >= 0)]
            if len(observed_fuel_ts) > 1:
                gaps = np.diff(observed_fuel_ts)
                record["observed_fuel_gap_max_ms"] = float(np.max(gaps))
                record["observed_fuel_gap_median_ms"] = float(np.median(gaps))
            else:
                record["observed_fuel_gap_max_ms"] = None
                record["observed_fuel_gap_median_ms"] = None
            for gap in GAPS_MS:
                result = window_support(ts, fuel, gap, input_valid)
                for metric in ["target_windows", "paired_windows", "nonoverlap_pairs", "segments", "covered_seconds", "longest_seconds"]:
                    record[f"fuel_{gap}ms_{metric}"] = result[metric]
                mode = modes[(record["engine_type"], gap)]
                for metric in ["target_windows", "paired_windows", "nonoverlap_pairs"]:
                    mode[metric] += result[metric]
                if result["paired_windows"]:
                    mode["vehicles"].add(key[0])
                    mode["trips"] += 1
                if gap == 2000 and len(result["labels"]):
                    labels_by_type[record["engine_type"]].append(result["labels"])
            for name, value, nonnegative in [("speed", np.where(malformed, np.nan, speed), True),
                                             ("battery_current", group["HV Battery Current[A]"].to_numpy(dtype=float), False)]:
                result = window_support(ts, value, 2000, input_valid, nonnegative)
                record[name + "_paired_windows"] = result["paired_windows"]
                mode = alternatives[name]
                for metric in ["paired_windows", "nonoverlap_pairs"]:
                    mode[metric] += result[metric]
                if result["paired_windows"]:
                    mode["vehicles"].add(key[0])
                    mode["trips"] += 1
            trips.append(record)
        print(json.dumps({"file": path.name, "completed_trips": len(trips), "pending_cross_file_trips": len(pending)}), flush=True)
    assert not pending
    assert sum(r["rows"] for r in trips) == sum(source_rows.values()) == 22_436_808
    directory = ROOT / "results/day3"
    directory.mkdir(parents=True, exist_ok=True)
    trip_frame = pd.DataFrame(trips).sort_values(["vehicle_id", "trip_id"])
    trip_frame.to_csv(directory / "fuel_by_trip.csv", index=False)
    group = trip_frame.groupby(["vehicle_id", "engine_type"])
    columns = [c for c in trip_frame.columns if c.endswith(("windows", "nonoverlap_pairs", "covered_seconds", "segments"))] + ["rows", "fuel_rows", "negative_timestamp_rows"]
    vehicle_frame = group[columns].sum().reset_index()
    vehicle_frame["fuel_fraction"] = vehicle_frame["fuel_rows"] / vehicle_frame["rows"]
    for gap in GAPS_MS:
        maxima = group[f"fuel_{gap}ms_longest_seconds"].max().reset_index()
        vehicle_frame = vehicle_frame.merge(maxima, on=["vehicle_id", "engine_type"], validate="one_to_one")
    vehicle_frame.to_csv(directory / "fuel_by_vehicle.csv", index=False)
    pd.DataFrame(negative_records).to_csv(directory / "negative_timestamp_trips.csv", index=False)
    sensitivity = [{"engine_type": kind, "max_gap_ms": gap, **{k:(sorted(v) if isinstance(v,set) else v) for k,v in mode.items()}}
                   for (kind,gap), mode in sorted(modes.items())]
    primary = [r for r in sensitivity if r["engine_type"] in {"ICE", "HEV"} and r["max_gap_ms"] == 2000]
    usable_ids = sorted({v for r in primary for v in r["vehicles"]})
    label_summaries = {}
    for kind, pieces in labels_by_type.items():
        values = np.concatenate(pieces)
        label_summaries[kind] = {"min_liters": float(values.min()), "mean_liters": float(values.mean()),
                                 "max_liters": float(values.max()), "zero_windows": int((values == 0).sum()),
                                 "p50_p95_liters": np.quantile(values,[0.5,0.95]).tolist()}
    report = {"source": "existing Day 2 Bronze only", "complete": True, "rows": int(trip_frame.rows.sum()),
              "trips": len(trips), "vehicles": len(vehicle_frame),
              "trips_across_bronze_files": sum(n > 1 for n in trip_files.values()),
              "fuel_observed_vehicles": int((vehicle_frame.fuel_rows > 0).sum()),
              "fuel_observed_trips": int((trip_frame.fuel_rows > 0).sum()),
              "fuel_observations": int(trip_frame.fuel_rows.sum()),
              "primary": {"population": "ICE/HEV (existing approved proposal)", "max_gap_ms": 2000,
                          "usable_vehicle_ids": usable_ids, "usable_vehicles": len(usable_ids),
                          "usable_trips": sum(r["trips"] for r in primary),
                          "paired_training_windows": sum(r["paired_windows"] for r in primary),
                          "nonoverlap_120s_pairs": sum(r["nonoverlap_pairs"] for r in primary),
                          "target_only_60s_windows": sum(r["target_windows"] for r in primary),
                          "grouped_train_validation_test_supported": len(usable_ids) >= 3},
              "gap_sensitivity": sensitivity, "diagnostic_fuel_label_summaries": label_summaries,
              "alternative_support": {k:{**v,"vehicles": sorted(v["vehicles"])} for k,v in alternatives.items()},
              "window_contract": {"past_seconds": 60, "future_seconds": 60, "anchor_grid_ms": 1000,
                  "endpoints": "exact observed t-60s, t, t+60s; no extrapolation",
                  "continuity": "every source row in span has finite signal; bounded adjacent gaps; no duplicates or negative timestamps",
                  "input": "finite nonnegative speed at every past-window source row",
                  "integration": "trapezoid over observed fuel rate endpoints; L/h × milliseconds / 3600000",
                  "missing": "never fill or interpolate a missing sensor row", "target_changed": False},
              "bronze_sha256": bronze_hashes, "elapsed_seconds": time.perf_counter()-started,
              "project_bytes": footprint()}
    (directory / "fuel_feasibility.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "bronze_sha256"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
