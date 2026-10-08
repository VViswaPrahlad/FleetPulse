# Dataset selection decision

**Decision date:** 2026-10-08
**Status:** recommended for approval; no data downloaded and no implementation started.

## Decision

Select the **Vehicle Energy Dataset (VED)** as FleetPulse's primary dataset.

VED is the best fit among the candidates checked because it combines naturalistic vehicle time series and real movement context with an actual OBD-II fuel-rate signal. It supplies vehicle/trip keys, timestamps, speed, GPS latitude/longitude, engine measurements, fuel rate, and hybrid battery fields. Its public author repository declares Apache License 2.0. The two dynamic archives have directly accessible URLs and together are about 176.4 MB compressed, below the 5 GB project target and feasible to stage locally on a 16 GB Windows laptop.

This is a better fit than the previous EPA Fuel Economy recommendation: EPA values are vehicle-level test ratings, while VED contains time-stamped observations from vehicles on real trips. The proposed VED target is still an ECU-reported OBD signal, not a laboratory-grade independent fuel-flow instrument; document that distinction.

## Verified download and license

The data owner’s [VED repository](https://github.com/gsoh/VED) links these dynamic files:

- [VED_DynamicData_Part1.7z](https://raw.githubusercontent.com/gsoh/VED/master/Data/VED_DynamicData_Part1.7z) — HTTP 200 on 2026-10-08, `Content-Length: 82,723,769`.
- [VED_DynamicData_Part2.7z](https://raw.githubusercontent.com/gsoh/VED/master/Data/VED_DynamicData_Part2.7z) — HTTP 200 on 2026-10-08, `Content-Length: 93,662,910`.
- [Static ICE/HEV vehicle data](https://raw.githubusercontent.com/gsoh/VED/master/Data/VED_Static_Data_ICE%26HEV.xlsx) — GitHub metadata reports 21,193 bytes.
- [Static PHEV/EV vehicle data](https://raw.githubusercontent.com/gsoh/VED/master/Data/VED_Static_Data_PHEV%26EV.xlsx) — GitHub metadata reports 9,763 bytes.

Only HTTP headers and repository metadata were inspected for the large archives; the archive bodies were not downloaded. The repository README declares [Apache License 2.0](https://github.com/gsoh/VED/blob/master/LICENSE). For a public portfolio, preserve attribution and license notices, cite the dataset paper, and link to the owner-hosted data rather than committing the archives.

## Scope and known data scale

The repository README describes 383 personal cars (264 gasoline, 92 HEV, 27 PHEV/EV), collection from November 2017 through November 2018, and approximately 374,000 miles. It documents week-based CSVs and fields including `VehId`, `Trip`, `Timestamp(ms)`, `Latitude[deg]`, `Longitude[deg]`, `Vehicle Speed[km/h]`, engine channels, and `Fuel Rate[L/hr]`. For fuel-signal analysis, the paper discusses 249 ICE and 90 HEV vehicles covering 309,171 miles.

The exact number of rows/trips, missingness, time cadence by vehicle, expanded CSV size, and final Parquet size have **not** been verified. Do not imply that 383 vehicles all have every sensor or a valid fuel-rate stream.

## Alternatives not selected

- **NGSIM:** accessible USDOT video-transcribed trajectories with 11,850,526 catalog rows, timestamp, speed, acceleration, lane and road-relative coordinates. It has no fuel target or GPS; IDs repeat and do not identify the same physical vehicle across groups. The catalog says CC BY-SA 3.0. Its old bulk-export URL returned HTTP 410, although a limited CSV API query and counts work.
- **highD:** excellent drone-derived traffic trajectories (publication reports about 110,500 vehicles, six locations, 16.5 recording hours), but the historic URL now redirects to a page whose current terms refer to uniD, and no current highD-specific download/reuse terms were verified.
- **UAH-DriveSet:** attractive behavior labels and phone sensor/GPS concepts, but the old official URL currently returns a DriveSafe app page rather than the dataset. The reader tool's CC BY-NC license is not the dataset license; a dataset download and reuse grant were not verified.
- Generic OBD-II community mirrors lack standardized fields/licensing. VED is the clearly identified and source-linked OBD option from this investigation.

See [the full comparison](dataset_comparison.md) for per-field evidence and source links.

## Implementation gate

**Dataset selection is ready; implementation is not authorized by this decision alone.** Wait for explicit user approval before Day 2 work. After approval, the first data step should be a bounded, user-approved sample or integrity/schema check—not immediate full ingestion. Confirm the license notices, archive extraction, schema, time cadence, fuel-rate coverage, and projected storage before processing the full corpus. Retain raw archives outside Git; enforce the 5 GB total working budget.

## Evidence links

- [VED author repository](https://github.com/gsoh/VED)
- [VED paper](https://arxiv.org/abs/1905.02081)
- [Apache License 2.0 in repository](https://github.com/gsoh/VED/blob/master/LICENSE)
- [NGSIM FHWA overview](https://ops.fhwa.dot.gov/trafficanalysistools/ngsim.htm)
- [NGSIM data portal](https://data.transportation.gov/Automobiles/Next-Generation-Simulation-NGSIM-Vehicle-Trajector/8ect-6jqj)
- [highD dataset paper](https://arxiv.org/abs/1810.05642)
- [UAH reader](https://github.com/Eromera/uah_driveset_reader)
