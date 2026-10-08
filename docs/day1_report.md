# Day 1 report — planning and setup

**Date:** 2026-10-08
**Status:** complete; stopped before implementation.

**Historical snapshot note:** the EPA/NRCan selection below was tentative on Day 1 and is superseded by the later VED investigation in [the dataset comparison](dataset_comparison.md) and [selection decision](dataset_selection_decision.md). No implementation was performed between those research steps.

## Work completed

- Created the requested folder layout, `.gitkeep` markers for empty working directories, `.gitignore`, requirements starter, and project documentation.
- Reviewed official catalog and documentation pages for EPA/FuelEconomy.gov, NRCan Fuel Consumption Ratings, UCI Auto MPG, USDOT NGSIM, and Apache Spark.
- Selected EPA `comb08` as a tentative target only for **test-derived vehicle rating prediction**; identified NRCan as a backup rating dataset.
- Made the missing telemetry/measurement boundary explicit. No dataset found in the reviewed material proves both trip-level telemetry and a measured fuel/energy target.
- Did not download data, install/upgrade packages, create a virtual environment, run Spark, train a model, build a dashboard, or push to GitHub.

## Environment inspection

| Check | Observed result | Implication |
|---|---|---|
| Windows / project location | Windows; project root is `C:\Users\viswa\Desktop\FleetPulse` | Local setup is appropriate. |
| Python default | `Python 3.13.7` | Default `python` is not the preferred version for this project. |
| Python 3.12 | Python launcher lists Python 3.12; directly checked interpreter reports `Python 3.12.10` | Python 3.12 is installed and can be selected explicitly with `py -3.12`. |
| Java | `java -version` reports `25.0.2`; Java is on PATH. `JAVA_HOME` is unset. | Spark 4.0 docs specify Java 17 or 21, not Java 25. Use a supported JDK and set `JAVA_HOME` before Spark work. Runtime compatibility was not tested. |
| Git | `git version 2.51.0.windows.1` | Git CLI is available. The directory is not a Git repository at this inspection; no repository was initialized. |
| Free disk space | C: approximately 52.6 GB free (48.9 GiB); D: approximately 209.3 GB free (194.9 GiB) | C: has enough headroom for the stated <5 GB project target, subject to rechecking before data download. |
| PySpark on Windows | Apache Spark 4.0 docs explicitly say Spark runs on Windows; local mode needs Java on PATH or `JAVA_HOME`. | Supported in principle. No local Spark launch was attempted, so filesystem/JDK/Py4J behavior remains unverified. |

## PySpark / Java compatibility evidence

The consulted [Spark 4.0.0 documentation](https://spark.apache.org/docs/4.0.0/) lists Python 3.9+ and Java 17/21 and states Windows is supported. Python 3.12.10 is therefore within the documented Python floor; the installed Java 25.0.2 does not match the documented Java versions for Spark 4.0. Use JDK 17 or 21 for the initial setup rather than assuming forward compatibility. Confirm the exact chosen PySpark release's requirements when setting up.

## Commands for a later Python 3.12 environment

Run from the FleetPulse root in PowerShell; these commands were documented, not executed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Before Spark execution, install/select a JDK 17 or 21 through the user's normal approved process and set `JAVA_HOME` to its installation directory. No JDK installation or environment-variable change was made.

## Dataset decision and risks

- **EPA primary candidate:** official download page states the data result from testing at EPA's National Vehicle and Fuel Emissions Laboratory and manufacturer testing with EPA oversight. `comb08` is a proposed combined-MPG target. This supports only an EPA-rating prediction claim, not measured trip consumption.
- **NRCan backup:** model-specific ratings and estimated CO2. Some 1995–2014 values are historical adjusted approximations rather than new vehicle tests.
- **UCI Auto MPG:** metadata API reports 398 instances, seven features, and target `mpg`; CC BY 4.0. Compact benchmark, not telemetry.
- **NGSIM:** USDOT/FHWA confirms public vehicle-trajectory data, but exact schema, row/vehicle/trip counts, GPS status, reuse terms, and any fuel target remain unverified from the reviewed pages.
- Exact file sizes and source record counts were not checked for EPA, NRCan, or NGSIM. Nothing was downloaded.
- Dataset-specific reuse terms for EPA/NRCan/NGSIM were not confirmed. Verify before using or redistributing data.
- No model results or performance claims exist.

## Next action

Day 2 is a dataset/target and environment gate, not an automatic implementation step. Decide whether test-rating prediction is acceptable. Then verify the selected source's license, complete schema, size, exact records, and target provenance; select a compatible JDK; and only then create the venv/download the approved dataset. If measured trip fuel/energy is mandatory, find a source that explicitly documents that target rather than treating certification ratings as real trips.
