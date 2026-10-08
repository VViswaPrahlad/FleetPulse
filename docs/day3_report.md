# FleetPulse Day 3 — Silver, quality and ML feasibility

Date: 2026-10-08 (Asia/Calcutta). **Day 3 deliverables are complete.**
The original ICE/HEV fuel target is retained as the approved proposal but
is not viable for its planned vehicle-held-out evaluation. A target/cohort
decision needs user approval before future ML work. No ML was trained.

## Priority 1: fuel-rate feasibility, completed before Silver

Analysis used existing Bronze only; no CSV re-extraction, dataset download,
Day 2 ingestion, or Day 2 test replay occurred. A key-only pass scheduled
whole-trip analysis, then required sensor columns were read once. No trip
crosses a Bronze file. Analysis runtime: **82.0454 seconds**.

Nonmissing direct fuel rate occurs in **13 vehicles**
and **1,357 trips**, totaling **896,097** observations.
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
**1 vehicle, 1 trip and
1 paired training window**; there are
27 target-only 60-second windows.
At 10 seconds, only one vehicle still qualifies (five paired windows).
One vehicle cannot supply disjoint vehicle-grouped train/validation/test
populations. **The original target is not viable as defined.**
No target or eligible population was silently changed.

| Population | Max gap (s) | Usable vehicles | Usable trips | Target-only 60s windows | Paired 60+60s windows | Disjoint 120s pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ICE | 1 | 0 | 0 | 0 | 0 | 0 |
| ICE | 2 | 1 | 1 | 27 | 1 | 1 |
| ICE | 5 | 1 | 3 | 43 | 4 | 3 |
| ICE | 10 | 1 | 3 | 46 | 5 | 3 |
| PHEV | 1 | 8 | 49 | 1,783 | 261 | 60 |
| PHEV | 2 | 12 | 527 | 15,282 | 2,187 | 898 |
| PHEV | 5 | 12 | 677 | 20,108 | 3,549 | 1,355 |
| PHEV | 10 | 12 | 744 | 22,643 | 4,432 | 1,708 |

### Actual vehicle-level continuous coverage (2-second rule)

Every observed fuel-rate vehicle is listed. Covered seconds sum the lengths
of valid contiguous segments; longest seconds is the longest single segment.
All other vehicles have zero direct fuel-rate coverage.

| Vehicle | Type | Fuel observations | Recorded-row fuel coverage | Covered seconds | Longest segment (s) | Paired windows |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 9 | PHEV | 1,465 | 100.00% | 914.7 | 224.6 | 1 |
| 119 | ICE | 1,822 | 100.00% | 1179.6 | 173.1 | 1 |
| 379 | PHEV | 1,313 | 100.00% | 794.8 | 241.0 | 1 |
| 457 | PHEV | 200,675 | 100.00% | 110510.0 | 589.4 | 626 |
| 492 | PHEV | 92,803 | 100.00% | 59105.8 | 768.4 | 464 |
| 536 | PHEV | 42,734 | 100.00% | 24319.2 | 583.8 | 104 |
| 537 | PHEV | 109,864 | 100.00% | 72410.6 | 436.4 | 141 |
| 542 | PHEV | 41,010 | 100.00% | 25308.1 | 699.4 | 80 |
| 545 | PHEV | 13,563 | 100.00% | 8330.4 | 582.0 | 38 |
| 550 | PHEV | 95,833 | 100.00% | 61977.9 | 681.9 | 177 |
| 554 | PHEV | 38,863 | 100.00% | 25040.0 | 624.7 | 86 |
| 567 | PHEV | 13,047 | 100.00% | 8402.6 | 457.2 | 26 |
| 569 | PHEV | 243,105 | 100.00% | 156736.1 | 1330.6 | 443 |

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
   the same 2-second policy. 73.25% of diagnostic target labels are zero;
   this limited, zero-heavy cohort would need grouped evaluation and baselines.
3. **Next-minute mean reported HV battery current**: a narrower measurement
   target. Preserve manufacturer-specific sign conventions; do not call it
   energy consumption without validating current/voltage semantics.

| Alternative signal | Usable vehicles | Usable trips | Paired windows | Disjoint 120s pairs |
| --- | ---: | ---: | ---: | ---: |
| speed | 318 | 6,864 | 34,348 | 11,671 |
| battery_current | 28 | 2,060 | 9,810 | 3,629 |

These are feasibility counts, not trained models or performance claims.
**Target selection remains pending user approval.**

## Priority 2: Silver contract and investigations

Implementation: `src/processing/silver_ved.py`. Existing Python 3.12.10,
PySpark 4.0.3, JDK 21.0.12.1, Pandas/NumPy and PyArrow
were reused. No new dependency, download or system setting was introduced.
Bronze retains its original strings and raw records and is unchanged.

Focused anomaly investigation took **22.6056 seconds**:
- All **358 SOC overshoots** equal **100.000030518**, across two vehicles and
  three trips; none exceeds 100.001. This is consistent with a precision
  overshoot; the source's causal explanation is not independently established.
- **2,702 negative timestamps**, −1,658,400 to −100 ms, occur in four ICE
  vehicles/trips. Each affected trip has both negative and nonnegative rows.
  No validated basis exists to reconstruct/rebase those negative offsets.
- Absolute load has 29,219 values
  above 100, 481 above 200, and
  327 above 1,000. These are
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
| `DayNum` | `day_number` | `double` |
| `VehId` | `vehicle_id` | `int64` |
| `Trip` | `trip_id` | `int64` |
| `Timestamp(ms)` | `elapsed_ms` | `int64` |
| `Latitude[deg]` | `latitude_deg` | `double` |
| `Longitude[deg]` | `longitude_deg` | `double` |
| `Vehicle Speed[km/h]` | `speed_kmh` | `double` |
| `MAF[g/sec]` | `maf_g_s` | `double` |
| `Engine RPM[RPM]` | `engine_rpm` | `double` |
| `Absolute Load[%]` | `absolute_load_pct` | `double` |
| `OAT[DegC]` | `outside_air_temp_c` | `double` |
| `Fuel Rate[L/hr]` | `fuel_rate_lph` | `double` |
| `Air Conditioning Power[kW]` | `aircon_power_kw` | `double` |
| `Air Conditioning Power[Watts]` | `aircon_power_w` | `double` |
| `Heater Power[Watts]` | `heater_power_w` | `double` |
| `HV Battery Current[A]` | `hv_battery_current_a` | `double` |
| `HV Battery SOC[%]` | `battery_soc_pct` | `double` |
| `HV Battery Voltage[V]` | `hv_battery_voltage_v` | `double` |
| `Short Term Fuel Trim Bank 1[%]` | `short_fuel_trim_b1_pct` | `double` |
| `Short Term Fuel Trim Bank 2[%]` | `short_fuel_trim_b2_pct` | `double` |
| `Long Term Fuel Trim Bank 1[%]` | `long_fuel_trim_b1_pct` | `double` |
| `Long Term Fuel Trim Bank 2[%]` | `long_fuel_trim_b2_pct` | `double` |

Additional fields: original parsed SOC, engine type, source CSV/week, Bronze
file/row index, ordered quality flags, exclusion reasons, gap milliseconds
and gap>2s boolean. Unit names remain explicit; no unverified AC-channel merge.

## Reconciliation and data-quality summary

**22,436,808 input = 22,434,106 retained +
2,702 quarantined.**
Retained: 384 vehicles, 32,552 trips.
Excluded rows are never silently dropped; their typed records and reasons are
in `data/quarantine/ved/`, with Bronze pointers for the original source values.
Spark reads back and reconciles both complete output sets. All 54 Bronze
hashes match the pre-feasibility baseline after processing.

Exclusion reasons (counts can overlap for generic multi-error rows):
`{'negative_elapsed_ms': 2702}`.
Retained quality flags (descriptive flags can overlap):
`{'missing_fuel_rate_lph': 21538009, 'irregular_gap_gt_2s': 777320, 'load_above_100_advisory': 29219, 'missing_speed_kmh': 1396, 'soc_precision_clipped': 358}`.

| Retained field | NULL rows | NULL percentage |
| --- | ---: | ---: |
| day_number | 0 | 0.0000% |
| vehicle_id | 0 | 0.0000% |
| trip_id | 0 | 0.0000% |
| elapsed_ms | 0 | 0.0000% |
| latitude_deg | 0 | 0.0000% |
| longitude_deg | 0 | 0.0000% |
| speed_kmh | 1,396 | 0.0062% |
| maf_g_s | 4,178,471 | 18.6255% |
| engine_rpm | 482,305 | 2.1499% |
| absolute_load_pct | 5,965,139 | 26.5896% |
| outside_air_temp_c | 9,368,444 | 41.7598% |
| fuel_rate_lph | 21,538,009 | 96.0056% |
| aircon_power_kw | 21,539,831 | 96.0138% |
| aircon_power_w | 19,599,729 | 87.3658% |
| heater_power_w | 21,555,748 | 96.0847% |
| hv_battery_current_a | 18,705,454 | 83.3795% |
| battery_soc_pct | 18,705,454 | 83.3795% |
| hv_battery_voltage_v | 18,705,454 | 83.3795% |
| short_fuel_trim_b1_pct | 4,754,080 | 21.1913% |
| short_fuel_trim_b2_pct | 15,644,999 | 69.7376% |
| long_fuel_trim_b1_pct | 7,263,451 | 32.3768% |
| long_fuel_trim_b2_pct | 18,126,223 | 80.7976% |

Outputs mirror the 13 source-month partitions and 54 weekly input filenames.
Silver footprint: **316,579,302 bytes**; quarantine:
**916,021 bytes**. No full duplicate raw-data copy.
Detailed per-file counts/ranges/nulls/flags/provenance are in `silver_quality.json`.

## Tests, reproducibility, runtime and storage

**20 Day 3 tests passed**, zero failures/errors, in
**23.4820 seconds** on the final fixture run.
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

Measured final Silver resume wall time: **258.4118 seconds**,
including 32 verified cached weeks.
Sum of measured worker-attempt wall times (including interrupted partial work):
**1589.9068 seconds (26.50 minutes)**.
Sum of committed per-file transformation/write times:
**1486.8937 seconds**.
These are distinct measurements; no fresh single-pass full-run timing is claimed.

A final cached repeat preserved all **108**
Silver/quarantine file hashes and all counts, and reverified Bronze unchanged.
Repeat runtime: **74.4483 seconds**. Fixture and real-week
audits separately validate fresh recomputation. Measured artifacts remain local
under `results/day3/`; no GitHub push occurred.

Current project logical file storage: **1,875,088,978 bytes**, below the
10,000,000,000-byte maximum and preferred 5 GB target. Recorded final-worker
peak: **1,921,291,570 bytes**. Footprint includes
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
