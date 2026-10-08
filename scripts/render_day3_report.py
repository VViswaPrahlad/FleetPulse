"""Render documented Day 3 rules and measured findings from validated artifacts."""
import json
import xml.etree.ElementTree as ET
import pandas as pd
from src.ingestion.ingest_ved import ROOT, footprint
from src.processing.silver_ved import FIELDS, SILVER_SCHEMA

RESULTS = ROOT / "results/day3"


def load(name):
    return json.loads((RESULTS/name).read_text())


def main():
    fuel,quality,anomalies,repeat = [load(n) for n in ["fuel_feasibility.json","silver_quality.json","anomaly_investigation.json","reproducibility.json"]]
    tests = ET.parse(RESULTS/"day3_pytest.xml").getroot().find("testsuite")
    assert quality["complete"] and repeat["passed"] and tests.attrib["failures"] == tests.attrib["errors"] == "0"
    attempts = load("silver_initial_attempt.json").get("attempts",[])
    worker_seconds = sum(a["attempt_elapsed_seconds"] for a in attempts) + quality["elapsed_seconds"]
    primary = fuel["primary"]
    sensitivity = "\n".join(f"| {r['engine_type']} | {r['max_gap_ms']/1000:g} | {len(r['vehicles'])} | {r['trips']} | {r['target_windows']:,} | {r['paired_windows']:,} | {r['nonoverlap_pairs']:,} |"
                             for r in fuel["gap_sensitivity"] if r["engine_type"] in {"ICE","PHEV"})
    vehicles = pd.read_csv(RESULTS/"fuel_by_vehicle.csv")
    observed = vehicles[vehicles.fuel_rows>0]
    vehicle_rows = "\n".join(f"| {int(r.vehicle_id)} | {r.engine_type} | {int(r.fuel_rows):,} | {r.fuel_fraction*100:.2f}% | {r.fuel_2000ms_covered_seconds:.1f} | {r.fuel_2000ms_longest_seconds:.1f} | {int(r.fuel_2000ms_paired_windows)} |"
                               for r in observed.itertuples())
    missing = "\n".join(f"| {name} | {count:,} | {100*count/quality['retained_rows']:.4f}% |" for name,count in quality["retained_null_counts"].items())
    schema = "\n".join(f"| `{old}` | `{new}` | `{SILVER_SCHEMA.field(new).type}` |" for old,new in FIELDS.items())
    alternative_rows = "\n".join(f"| {name} | {len(mode['vehicles'])} | {mode['trips']:,} | {mode['paired_windows']:,} | {mode['nonoverlap_pairs']:,} |"
                                   for name,mode in fuel["alternative_support"].items())
    zero_pct = 100*fuel["diagnostic_fuel_label_summaries"]["PHEV"]["zero_windows"]/2187
    text = f"""# FleetPulse Day 3 — Silver, quality and ML feasibility

Date: 2026-10-08 (Asia/Calcutta). **Day 3 deliverables are complete.**
The original ICE/HEV fuel target is retained as the approved proposal but
is not viable for its planned vehicle-held-out evaluation. A target/cohort
decision needs user approval before future ML work. No ML was trained.

## Priority 1: fuel-rate feasibility, completed before Silver

Analysis used existing Bronze only; no CSV re-extraction, dataset download,
Day 2 ingestion, or Day 2 test replay occurred. A key-only pass scheduled
whole-trip analysis, then required sensor columns were read once. No trip
crosses a Bronze file. Analysis runtime: **{fuel['elapsed_seconds']:.4f} seconds**.

Nonmissing direct fuel rate occurs in **{fuel['fuel_observed_vehicles']} vehicles**
and **{fuel['fuel_observed_trips']:,} trips**, totaling **{fuel['fuel_observations']:,}** observations.
Twelve observed vehicles are PHEVs and one is ICE; all HEV/EV fuel-rate values
are missing. Each of those 13 vehicles has fuel rate on every recorded row;
fleet missingness is structural vehicle coverage, not a random set of holes.
Time gaps still prevent continuous coverage. Reported presence does not prove
each repeated value is a fresh fuel-sensor update or laboratory ground truth.

### Explicit conservative window contract

- Prediction anchors are observed timestamps exactly on a one-second trip grid.
- Measured endpoints must exist at t−60s, t, and t+60s; no boundary extrapolation.
- Every source row over the 120-second span must have finite nonnegative fuel
  rate and valid nonnegative integral timestamps, without duplicate timestamps.
- Adjacent observed gaps must be at most **2 seconds** by default; sensitivities
  at 1, 5 and 10 seconds are also measured. Two seconds is a conservative policy
  informed by the Day 2 row-cadence p95; it is not a physical sensor law.
- Past speed must be finite/nonnegative throughout [t−60s,t]. Future speed is
  not used to filter a fuel target. Fuel history is required for the proposed
  persistence baseline. A target-only count is reported separately.
- Fuel liters use trapezoidal integration between observed endpoints:
  Σ[(rate_i+rate_(i+1))/2 × delta_ms / 3,600,000]. No missing fuel row is filled.
  This numerical integration convention estimates interval fuel from reported
  rates; it does not create new sensor measurements.
- Paired-window counts may overlap. The separate nonoverlap count greedily
  selects disjoint 120-second contexts within each trip. No split or model
  fitting was performed; no Gold training table was persisted.

These strict exact-endpoint counts are lower bounds under this documented
policy. Different interpolation/anchor choices would require a separate
audited analysis; counts are not claimed for those untested conventions.

### Original target verdict

At a 2-second maximum gap, the original ICE/HEV proposal supports
**{primary['usable_vehicles']} vehicle, {primary['usable_trips']} trip and
{primary['paired_training_windows']} paired training window**; there are
{primary['target_only_60s_windows']} target-only 60-second windows.
At 10 seconds, only one vehicle still qualifies (five paired windows).
One vehicle cannot supply disjoint vehicle-grouped train/validation/test
populations. **The original target is not viable as defined.**
No target or eligible population was silently changed.

| Population | Max gap (s) | Usable vehicles | Usable trips | Target-only 60s windows | Paired 60+60s windows | Disjoint 120s pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{sensitivity}

### Actual vehicle-level continuous coverage (2-second rule)

Every observed fuel-rate vehicle is listed. Covered seconds sum the lengths
of valid contiguous segments; longest seconds is the longest single segment.
All other vehicles have zero direct fuel-rate coverage.

| Vehicle | Type | Fuel observations | Recorded-row fuel coverage | Covered seconds | Longest segment (s) | Paired windows |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{vehicle_rows}

Per-trip coverage, segment counts, maximum/median observed gaps and window
counts are in `results/day3/fuel_by_trip.csv`; per-vehicle aggregates are in
`fuel_by_vehicle.csv`. Gap metrics describe recorded observations, not
unobservable sensor freshness.

### Alternatives supported by measurements — approval required

1. **Next-60-second mean speed** (or equivalently speed-integrated distance),
   recommended for broad fleet support. It uses real speed readings and
   time-weighted integration. It would replace the original fuel target.
2. **PHEV-only next-minute fuel use**, a population change: 12 vehicles,
   527 trips, 2,187 paired windows and 898 disjoint 120-second pairs under
   the same 2-second policy. {zero_pct:.2f}% of diagnostic target labels are zero;
   this limited, zero-heavy cohort would need grouped evaluation and baselines.
3. **Next-minute mean reported HV battery current**: a narrower measurement
   target. Preserve manufacturer-specific sign conventions; do not call it
   energy consumption without validating current/voltage semantics.

| Alternative signal | Usable vehicles | Usable trips | Paired windows | Disjoint 120s pairs |
| --- | ---: | ---: | ---: | ---: |
{alternative_rows}

These are feasibility counts, not trained models or performance claims.
**Target selection remains pending user approval.**

## Priority 2: Silver contract and investigations

Implementation: `src/processing/silver_ved.py`. Existing Python 3.12.10,
PySpark {quality['spark']}, JDK {quality['java']}, Pandas/NumPy and PyArrow
were reused. No new dependency, download or system setting was introduced.
Bronze retains its original strings and raw records and is unchanged.

Focused anomaly investigation took **{anomalies['elapsed_seconds']:.4f} seconds**:
- All **358 SOC overshoots** equal **100.000030518**, across two vehicles and
  three trips; none exceeds 100.001. This is consistent with a precision
  overshoot; the source's causal explanation is not independently established.
- **2,702 negative timestamps**, −1,658,400 to −100 ms, occur in four ICE
  vehicles/trips. Each affected trip has both negative and nonnegative rows.
  No validated basis exists to reconstruct/rebase those negative offsets.
- Absolute load has {anomalies['load_advisory_counts']['above_100']:,} values
  above 100, {anomalies['load_advisory_counts']['above_200']:,} above 200, and
  {anomalies['load_advisory_counts']['above_1000']:,} above 1,000. These are
  advisory observations; no unverified manufacturer-specific upper cap is imposed.

### Every cleaning/filtering rule (ved-silver-1)

1. Require the verified 27-column Bronze schema; mismatch stops the file.
2. Parse numeric source fields as finite float64. Null, blank and case-insensitive
   NaN markers become NULL. Unrecognized/nonfinite nonmissing tokens become
   NULL with `invalid_numeric_*` flags. Real zeros remain real zeros.
3. Vehicle/trip IDs must be finite nonnegative integers. Elapsed milliseconds
   must be finite integers and nonnegative. DayNum must be finite and at least
   one; source week must parse as a date. Malformed/unknown malformed-state
   rows and any essential-key/time/date failure go to quarantine with reasons.
4. Negative speed, MAF, RPM, load, fuel rate, AC/heater power and battery voltage
   become NULL with field flags; they do not exclude an otherwise valid row.
   Signed longitude, battery current, temperature and fuel trims remain signed.
5. Coordinates outside ±90/±180 degrees become NULL with flags. Temperature
   below −273.15°C becomes NULL with a flag. No guessed upper temperature cap.
6. SOC in (100,100.001] becomes 100 and receives `soc_precision_clipped`.
   Original parsed SOC is retained in `battery_soc_source_pct`, and the exact
   original token remains in Bronze. SOC below 0 or above 100.001 becomes NULL
   with `soc_out_of_range`. Missing SOC stays missing.
7. Load above 100 receives an advisory flag and is retained unchanged.
8. Missing speed/fuel receive descriptive flags. All optional sensor missingness
   is counted; no fill, smoothing, forward-fill or resampling occurs.
9. Static engine types are joined from existing workbooks; duplicate static IDs
   fail. Unmatched types are flagged and retained, not invented.
10. Duplicate vehicle/trip/elapsed keys are flagged and retained, not deduplicated.
11. Retained rows are ordered by vehicle/trip/elapsed and source index. The first
    row's gap is NULL; later gaps above 2,000 ms get a flag and are retained.
    Trip-local calculations are allowed because feasibility verified zero
    cross-file trips. The same contract is checked before processing.
12. Output is deterministic fixed-name Zstandard Parquet, validated and atomically
    replaced. Every original row identity belongs exactly once to Silver or
    quarantine; checks compare the full source-index set, not only aggregate counts.

No absolute timestamp/timezone is invented. DayNum remains fractional days;
elapsed_ms remains integer milliseconds. Source-week/source-month describe
file origin, not transformed observation date. Provenance is
`(bronze_file, bronze_row_index)` into immutable Bronze. Retained and excluded
records share the typed schema plus flags and exclusion reasons.

| Original column | Silver field | Arrow type |
| --- | --- | --- |
{schema}

Additional fields: original parsed SOC, engine type, source CSV/week, Bronze
file/row index, ordered quality flags, exclusion reasons, gap milliseconds
and gap>2s boolean. Unit names remain explicit; no unverified AC-channel merge.

## Reconciliation and data-quality summary

**{quality['input_rows']:,} input = {quality['retained_rows']:,} retained +
{quality['excluded_rows']:,} quarantined.**
Retained: {quality['retained_vehicles']} vehicles, {quality['retained_trips']:,} trips.
Excluded rows are never silently dropped; their typed records and reasons are
in `data/quarantine/ved/`, with Bronze pointers for the original source values.
Spark reads back and reconciles both complete output sets. All 54 Bronze
hashes match the pre-feasibility baseline after processing.

Exclusion reasons (counts can overlap for generic multi-error rows):
`{quality['exclusion_reasons']}`.
Retained quality flags (descriptive flags can overlap):
`{quality['quality_flags']}`.

| Retained field | NULL rows | NULL percentage |
| --- | ---: | ---: |
{missing}

Outputs mirror the 13 source-month partitions and 54 weekly input filenames.
Silver footprint: **{quality['silver_bytes']:,} bytes**; quarantine:
**{quality['quarantine_bytes']:,} bytes**. No full duplicate raw-data copy.
Detailed per-file counts/ranges/nulls/flags/provenance are in `silver_quality.json`.

## Tests, reproducibility, runtime and storage

**{tests.attrib['tests']} Day 3 tests passed**, zero failures/errors, in
**{float(tests.attrib['time']):.4f} seconds** on the final fixture run.
Tests cover exact-window integration/units, missing-row continuity, gap
sensitivity, measured endpoints, no future-speed filtering of past context,
valid zeros/signed current, timestamp duplicates, typed schemas, null handling,
signed sensors, SOC precision/gross errors, quarantine/reconciliation,
irregular gaps, invalid optional/essential fields, duplicate retention,
advisory load, provenance, Parquet readability and byte-identical recomputation.

Execution tuning retained identical cleaning rules. Two early workers were
checkpoint-stopped, first for Arrow task grouping and then for an interpreted
flag-array expression identified in the installed Spark classes. A real
489,414-row recomputation produced byte-identical Silver and quarantine files
before the final resume. Completed outputs were reused, not regenerated.

Measured final Silver resume wall time: **{quality['elapsed_seconds']:.4f} seconds**,
including {sum(r['cached'] for r in quality['files'])} verified cached weeks.
Sum of measured worker-attempt wall times (including interrupted partial work):
**{worker_seconds:.4f} seconds ({worker_seconds/60:.2f} minutes)**.
Sum of committed per-file transformation/write times:
**{sum(r['elapsed_seconds'] for r in quality['files']):.4f} seconds**.
These are distinct measurements; no fresh single-pass full-run timing is claimed.

A final cached repeat preserved all **{repeat['unchanged_output_files']}**
Silver/quarantine file hashes and all counts, and reverified Bronze unchanged.
Repeat runtime: **{repeat['elapsed_seconds']:.4f} seconds**. Fixture and real-week
audits separately validate fresh recomputation. Measured artifacts remain local
under `results/day3/`; no GitHub push occurred.

Current project logical file storage: **PROJECT_BYTES bytes**, below the
10,000,000,000-byte maximum and preferred 5 GB target. Recorded final-worker
peak: **{quality['peak_project_bytes_observed']:,} bytes**. Footprint includes
existing .venv, archives, Bronze, Silver, quarantine, reports and task temporaries;
external Python/JDK installations are excluded. The worker samples storage
each second and cancels jobs at 9 GB. Allocated filesystem space and unsampled
instantaneous peaks are not claimed. Interrupted-worker temporary files are
included in the current footprint.

## Limits and stopping point

Fuel eligibility is policy-dependent; exact endpoints and strict continuity
produce conservative overlapping-window counts. Reported sensor presence
does not establish freshness/calibration. Future ML requires approved target
selection, vehicle-grouped splitting, leakage controls and actual model evaluation.
The provided PyArrow writer/explicit-file Spark reader handles Windows IO;
native Hadoop directory IO remains unavailable. No blocking issue remains
for Silver. No ML training, dashboard, Gold training table or Day 4 work occurred.
**Stopped after Day 3; alternative target approval remains pending.**
"""
    report = ROOT / "docs/day3_report.md"
    for _ in range(3):
        report.write_text(text.replace("PROJECT_BYTES",f"{footprint():,}"),encoding="utf-8")
    print(json.dumps({"report":str(report),"project_bytes":footprint(),"worker_seconds":worker_seconds}),flush=True)


if __name__ == "__main__":
    main()
