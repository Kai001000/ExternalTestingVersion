# Data Pipeline

References:
- Metric consumers and assumptions: [METRICS_AND_LOGIC.md](./METRICS_AND_LOGIC.md)
- Validation after rebuild/update: [VALIDATION_AND_AUDIT.md](./VALIDATION_AND_AUDIT.md)

## Source Systems
### Sales Data
Source:
- NSW Valuer General

Characteristics:
- authoritative transaction data
- lagged/rolling registration behavior

### Listing Data
Source:
- Domain listings

Primary files:
- sale: `data/current/nsw_sale_listings_current.parquet`
- rent: `data/current/nsw_rent_listings_current.parquet`

### Geographic Data
Source:
- ABS suburb boundary and related mapping dimensions

Uses:
- map geometry
- suburb coverage
- geography joins

Market Region source mapping:
- base source mapping remains `Reference/ABS/sydney_16_region_suburb_postcode_mapping.xlsx`
- active canonical supplement for Market Region additions is `Reference/ABS/market_region_mapping_overrides.csv`
- `Processed/dim/dim_region16_mapping.csv` now represents the canonical Market Region mapping through a legacy compatibility filename
- `utils/region16_segments.py` is the single code source for derived Market Region segment overlays such as Lower North Shore Core / Extended
- base `dim_region16_mapping.csv` defines the base Lower North Shore; Core / Extended rows are derived segment overlays and are postcode-expanded at build/runtime
- new regions such as Forest District must be introduced through canonical mapping updates, not by UI-only logic
- the current mapping model is postcode-based
- partial postcode support is not available in the current architecture
- the current supplement adds Forest District with conservative v1 postcode coverage:
  - `2085`
  - `2086`
  - `2087`

## Core Build Scripts
Pipeline scripts referenced by the project:
- `refresh_dat_manifest.py`
- `build_dim_suburb_postcode.py`
- `build_dim_region16.py`
- `build_fact_sales_year.py`
- `build_mart_daily_rolling.py`
- `build_mart_monthly_all_years.py`

Compatibility naming rule:
- `build_dim_region16.py` and downstream `region16` artifacts remain legacy compatibility paths
- canonically, those paths now build and serve the Market Region layer

## Raw Data Layout
Key raw-data areas:
- `RawData/1 page update/` for newly added weekly zip drops
- `RawData/DAT/<year>/<batch>/` for extracted DAT batches
- `RawData/manifest/dat_manifest.csv` for DAT manifest tracking

## Update Workflow
### Manual Weekly Update Flow
Canonical update flow:
1. place the newly downloaded zip into `RawData/1 page update/`
2. run `scripts/update_market_view_from_zip.py`
3. extract DAT files into the correct `RawData/DAT/<year>/<date>/` destination
4. refresh the DAT manifest
5. rebuild the affected fact-year parquet
6. rebuild downstream daily rolling marts
7. validate output timestamps, row counts, schema stability, and latest available dates

### Update Script Scope
`scripts/update_market_view_from_zip.py` is the semi-automated pipeline path for manual zip ingestion and downstream Market View refresh.

Current operational note:
- monthly mart rebuild is a distinct pipeline concern and may not be included in every manual update-script execution path

### 20260803 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260803.zip`
- source package size: 226,465 bytes
- primary update command attempted: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260803`
- primary wrapper exit result: exit code 1 before extraction because `RawData/DAT/2026/20260803` already existed and was non-empty
- recovery command for native mart crash: not used; no native crash occurred
- direct build commands used after ZIP-to-existing-DAT verification:
  - `.\.venv\Scripts\python.exe refresh_dat_manifest.py --min_year 2026 --max_year 2026`
  - `.\.venv\Scripts\python.exe build_fact_sales_year.py --min_year 2026 --max_year 2026 --rebuild_if_inputs_newer --overwrite`
  - `.\.venv\Scripts\python.exe build_mart_daily_rolling.py`
- DAT extraction directory: `RawData/DAT/2026/20260803`
- DAT files present: 123

Run note:
- The ZIP was readable and contained 123 `.DAT` files.
- Existing DAT files in `RawData/DAT/2026/20260803` matched ZIP DAT names and sizes, so the directory was not cleared with `--force`.
- Manifest refresh, fact rebuild, and daily rolling mart rebuild completed with exit code 0.

Validated outputs from the 20260803 run:
- `RawData/manifest/dat_manifest.csv`: 3,759 rows, modified `2026-08-03 17:12:42`
- `Processed/fact_sales/fact_sales_2026.parquet`: 93,875 rows, latest `contract_date` `2026-07-30`, modified `2026-08-03 17:12:49`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 12,013 rows, latest date `2026-07-30`, modified `2026-08-03 17:12:54`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,619 rows, latest date `2026-07-30`, modified `2026-08-03 17:12:55`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 205,804 rows, latest date `2026-07-24`, modified `2026-08-03 17:12:55`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,895,352 rows, latest date `2026-07-30`, modified `2026-08-03 17:12:56`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,971,409 rows, latest date `2026-07-30`, modified `2026-08-03 17:12:57`

Comparison to 20260727:
- DAT count: 123 -> 123 for the weekly ZIP batch
- manifest rows: 3,636 -> 3,759
- `fact_sales_2026` rows: 91,071 -> 93,875
- `fact_sales_2026` latest `contract_date`: `2026-07-23` -> `2026-07-30`
- rows after previous max `contract_date` `2026-07-23`: 20
- rows on latest `contract_date` `2026-07-30`: 1
- NSW rolling rows/latest date: 11,999 / `2026-07-23` -> 12,013 / `2026-07-30`
- Region rolling rows/latest date: 23,591 / `2026-07-23` -> 23,619 / `2026-07-30`
- Market Region/`REGION16` rolling rows/latest date: 205,735 / `2026-07-23` -> 205,804 / `2026-07-24`
- Suburb rolling rows/latest date: 9,879,654 / `2026-07-23` -> 9,895,352 / `2026-07-30`
- Postcode rolling rows/latest date: 3,964,927 / `2026-07-23` -> 3,971,409 / `2026-07-30`

Validation notes:
- duplicate-row checks returned 0 for manifest, fact, and all five `daily_rolling_*` mart files
- Region16 lags NSW/Region, but mapped coverage explains the lag: after `2026-07-23`, statewide 2026 fact rows total 20, Region16-mapped rows total 2, and mapped max `contract_date` is `2026-07-24`
- `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests
- `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`
- Streamlit AppTest rendered NSW, Region, Market Region/`REGION16`, and `MACQUARIE PARK (2113)` AREA saved-state cases with 0 exceptions
- local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text, and Market View rendered data as of `2026-07-30`
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected under the saved-state variant `Macquarie Park (2113)` and produced the expected empty filtered result
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation
- latest post-`2026-07-23` fact rows are thin and should be treated as provisional registration-lag data

### 20260727 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260727.zip`
- primary update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260727`
- recovery command for mart step: not used; wrapper completed with exit code 0
- DAT extraction directory: `RawData/DAT/2026/20260727`
- DAT files extracted: 123

Run note:
- The primary wrapper completed extraction, manifest refresh, fact rebuild, and daily rolling mart rebuild successfully.
- No native exit code `3221225477` occurred in this run.

Validated outputs from the 20260727 run:
- `RawData/manifest/dat_manifest.csv`: 3,636 rows, modified `2026-07-27 20:11:22`
- `Processed/fact_sales/fact_sales_2026.parquet`: 91,071 rows, latest `contract_date` `2026-07-23`, modified `2026-07-27 20:11:25`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,999 rows, latest date `2026-07-23`, modified `2026-07-27 20:11:27`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,591 rows, latest date `2026-07-23`, modified `2026-07-27 20:11:28`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 205,735 rows, latest date `2026-07-23`, modified `2026-07-27 20:11:28`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,879,654 rows, latest date `2026-07-23`, modified `2026-07-27 20:11:30`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,964,927 rows, latest date `2026-07-23`, modified `2026-07-27 20:11:31`

Comparison to 20260720:
- DAT count: 127 -> 123 for the weekly ZIP batch
- manifest rows: 3,513 -> 3,636
- `fact_sales_2026` rows: 88,519 -> 91,071
- `fact_sales_2026` latest `contract_date`: `2026-07-16` -> `2026-07-23`
- rows after previous max `contract_date` `2026-07-16`: 15
- rows on latest `contract_date` `2026-07-23`: 3
- NSW rolling rows/latest date: 11,985 / `2026-07-16` -> 11,999 / `2026-07-23`
- Region rolling rows/latest date: 23,563 / `2026-07-16` -> 23,591 / `2026-07-23`
- Market Region/`REGION16` rolling rows/latest date: 205,170 / `2026-07-09` -> 205,735 / `2026-07-23`
- Suburb rolling rows/latest date: 9,863,975 / `2026-07-16` -> 9,879,654 / `2026-07-23`
- Postcode rolling rows/latest date: 3,958,728 / `2026-07-16` -> 3,964,927 / `2026-07-23`

Validation notes:
- duplicate-row checks returned 0 for manifest, fact, and all five `daily_rolling_*` mart files
- Region16 is not lagging in this run; NSW, Region, and Region16 all have max date `2026-07-23`
- Region16 mapped coverage check: after `2026-07-09`, 68 statewide 2026 fact rows and 14 Region16-mapped rows, mapped max `contract_date` `2026-07-23`; after `2026-07-16`, 15 statewide rows and 4 mapped rows, mapped max `contract_date` `2026-07-23`
- `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests
- `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`
- Streamlit AppTest rendered NSW, Region, Market Region/`REGION16`, and `MACQUARIE PARK (2113)` AREA saved-state cases with 0 exceptions
- local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected under the saved-state variant `Macquarie Park (2113)` and produced the expected empty filtered result
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation
- latest post-`2026-07-16` fact rows are thin and should be treated as provisional registration-lag data

### 20260720 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260720.zip`
- primary update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260720`
- recovery command for mart step: `.\.venv\Scripts\python.exe -X faulthandler build_mart_daily_rolling.py`
- DAT extraction directory: `RawData/DAT/2026/20260720`
- DAT files extracted: 127

Run note:
- The primary wrapper completed extraction, manifest refresh, and `fact_sales_2026` rebuild, then the mart step exited with native exit code `3221225477` and no Python traceback.
- Direct mart rebuild with `-X faulthandler` completed successfully and wrote the active rolling artifacts.

Validated outputs from the 20260720 run:
- `RawData/manifest/dat_manifest.csv`: 3,513 rows, modified `2026-07-20 16:38:43`
- `Processed/fact_sales/fact_sales_2026.parquet`: 88,519 rows, latest `contract_date` `2026-07-16`, modified `2026-07-20 16:38:47`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,985 rows, latest date `2026-07-16`, modified `2026-07-20 16:39:34`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,563 rows, latest date `2026-07-16`, modified `2026-07-20 16:39:35`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 205,170 rows, latest date `2026-07-09`, modified `2026-07-20 16:39:35`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,863,975 rows, latest date `2026-07-16`, modified `2026-07-20 16:39:37`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,958,728 rows, latest date `2026-07-16`, modified `2026-07-20 16:39:37`

Comparison to 20260713:
- DAT count: 127 -> 127
- manifest rows: 3,386 -> 3,513
- `fact_sales_2026` rows: 86,050 -> 88,519
- `fact_sales_2026` latest `contract_date`: `2026-07-09` -> `2026-07-16`
- rows after previous max `contract_date` `2026-07-09`: 12
- NSW rolling rows/latest date: 11,971 / `2026-07-09` -> 11,985 / `2026-07-16`
- Region rolling rows/latest date: 23,535 / `2026-07-09` -> 23,563 / `2026-07-16`
- Market Region/`REGION16` rolling rows/latest date: 205,063 / `2026-07-07` -> 205,170 / `2026-07-09`

Validation notes:
- `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests
- `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`
- local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text, and Market View rendered data as of `2026-07-16`
- Streamlit AppTest rendered NSW, Region, and Market Region/`REGION16` views with 0 exceptions
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected under the saved-state variant `Macquarie Park (2113)` and produced the expected empty filtered result
- Region16 latest date lag is explained by underlying mapped fact coverage: Region16-mapped fact rows after `2026-07-09` total 0
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation
- latest post-`2026-07-09` fact rows are thin and should be treated as provisional registration-lag data

### 20260713 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260713.zip`
- update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260713`
- DAT extraction directory: `RawData/DAT/2026/20260713`
- DAT files extracted: 127

Validated outputs from the 20260713 run:
- `RawData/manifest/dat_manifest.csv`: 3,386 rows, modified `2026-07-13 20:24:12`
- `Processed/fact_sales/fact_sales_2026.parquet`: 86,050 rows, latest `contract_date` `2026-07-09`, modified `2026-07-13 20:24:15`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,971 rows, latest date `2026-07-09`, modified `2026-07-13 20:24:16`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,535 rows, latest date `2026-07-09`, modified `2026-07-13 20:24:17`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 205,063 rows, latest date `2026-07-07`, modified `2026-07-13 20:24:17`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,849,316 rows, latest date `2026-07-09`, modified `2026-07-13 20:24:19`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,952,868 rows, latest date `2026-07-09`, modified `2026-07-13 20:24:20`

Comparison to 20260706:
- DAT count: 126 -> 127
- manifest rows: 3,259 -> 3,386
- `fact_sales_2026` rows: 83,176 -> 86,050
- `fact_sales_2026` latest `contract_date`: `2026-07-01` -> `2026-07-09`
- rows after previous max `contract_date` `2026-07-01`: 30
- NSW rolling rows/latest date: 11,955 / `2026-07-01` -> 11,971 / `2026-07-09`
- Region rolling rows/latest date: 23,503 / `2026-07-01` -> 23,535 / `2026-07-09`
- Market Region/`REGION16` rolling rows/latest date: 204,763 / `2026-06-30` -> 205,063 / `2026-07-07`

Validation notes:
- update pipeline completed without fatal error or traceback
- `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests
- `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`
- local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text, and Market View rendered data as of `2026-07-09`
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected after case-insensitive option coercion and produced the expected empty filtered result
- Region16 latest date lag is explained by underlying mapped fact coverage: Region16-mapped fact rows after `2026-07-01` total 5 and max at `2026-07-07`
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation
- latest post-`2026-07-01` fact rows are thin and should be treated as provisional registration-lag data

### 20260706 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260706.zip`
- update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260706`
- DAT extraction directory: `RawData/DAT/2026/20260706`
- DAT files extracted: 126

Validated outputs from the 20260706 run:
- `RawData/manifest/dat_manifest.csv`: 3,259 rows, modified `2026-07-06 08:55:35`
- `Processed/fact_sales/fact_sales_2026.parquet`: 83,176 rows, latest `contract_date` `2026-07-01`, modified `2026-07-06 08:55:38`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,955 rows, latest date `2026-07-01`, modified `2026-07-06 08:55:39`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,503 rows, latest date `2026-07-01`, modified `2026-07-06 08:55:40`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 204,763 rows, latest date `2026-06-30`, modified `2026-07-06 08:55:40`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,834,425 rows, latest date `2026-07-01`, modified `2026-07-06 08:55:43`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,946,820 rows, latest date `2026-07-01`, modified `2026-07-06 08:55:45`

Comparison to 20260629:
- DAT count: 127 -> 126
- manifest rows: 3,133 -> 3,259
- `fact_sales_2026` rows: 79,472 -> 83,176
- `fact_sales_2026` latest `contract_date`: `2026-06-25` -> `2026-07-01`
- rows after previous max `contract_date` `2026-06-25`: 55
- NSW rolling rows/latest date: 11,943 / `2026-06-25` -> 11,955 / `2026-07-01`
- Region rolling rows/latest date: 23,479 / `2026-06-25` -> 23,503 / `2026-07-01`
- Market Region/`REGION16` rolling rows/latest date: 204,556 / `2026-06-25` -> 204,763 / `2026-06-30`

Validation notes:
- update pipeline completed without fatal error or traceback
- `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests
- `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `scripts/update_market_view_from_zip.py`, `build_fact_sales_year.py`, `refresh_dat_manifest.py`, and `build_mart_daily_rolling.py`
- Streamlit AppTest confirmed NSW, Region, and Market Region/`REGION16` views rendered without exceptions
- local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`, 200 from `/`, and 200 from `/Market_View`; the server process was stopped after validation
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected and rendered the `market_view_no_selection_data` empty state in Market View
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation
- latest post-`2026-06-25` fact rows are thin and should be treated as provisional registration-lag data

### 20260629 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260629.zip`
- update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260629`
- DAT extraction directory: `RawData/DAT/2026/20260629`
- DAT files extracted: 127

Validated outputs from the 20260629 run:
- `RawData/manifest/dat_manifest.csv`: 3,133 rows, modified `2026-06-29 18:26:31`
- `Processed/fact_sales/fact_sales_2026.parquet`: 79,472 rows, latest `contract_date` `2026-06-25`, modified `2026-06-29 18:26:33`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,943 rows, latest date `2026-06-25`, modified `2026-06-29 18:26:35`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,479 rows, latest date `2026-06-25`, modified `2026-06-29 18:26:36`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 204,556 rows, latest date `2026-06-25`, modified `2026-06-29 18:26:36`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,815,097 rows, latest date `2026-06-25`, modified `2026-06-29 18:26:37`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,939,821 rows, latest date `2026-06-25`, modified `2026-06-29 18:26:38`

Comparison to 20260622:
- DAT count: 123 -> 127
- manifest rows: 3,006 -> 3,133
- `fact_sales_2026` rows: 74,725 -> 79,472
- `fact_sales_2026` latest `contract_date`: `2026-06-18` -> `2026-06-25`
- NSW rolling rows/latest date: 11,929 / `2026-06-18` -> 11,943 / `2026-06-25`
- Region rolling rows/latest date: 23,451 / `2026-06-18` -> 23,479 / `2026-06-25`
- Market Region/`REGION16` rolling rows/latest date: 204,238 / `2026-06-18` -> 204,556 / `2026-06-25`

Validation notes:
- update pipeline completed without fatal error or traceback
- `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests
- `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `scripts/update_market_view_from_zip.py`, `build_fact_sales_year.py`, `refresh_dat_manifest.py`, and `build_mart_daily_rolling.py`
- Streamlit AppTest confirmed NSW, Region, and Market Region/`REGION16` views rendered without exceptions and latest date `2026-06-25` was visible
- local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health` and 200 from `/`; the server process was stopped after validation
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected and rendered an empty state in Market View
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation

### 20260622 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260622.zip`
- update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260622`
- DAT extraction directory: `RawData/DAT/2026/20260622`
- DAT files extracted: 123

Validated outputs from the 20260622 run:
- `RawData/manifest/dat_manifest.csv`: 3,006 rows, modified `2026-06-22 17:35:40`
- `Processed/fact_sales/fact_sales_2026.parquet`: 74,725 rows, latest `contract_date` `2026-06-18`, modified `2026-06-22 17:35:43`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,929 rows, latest date `2026-06-18`, modified `2026-06-22 17:35:45`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,451 rows, latest date `2026-06-18`, modified `2026-06-22 17:35:46`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 204,238 rows, latest date `2026-06-18`, modified `2026-06-22 17:35:46`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,797,460 rows, latest date `2026-06-18`, modified `2026-06-22 17:35:47`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,932,948 rows, latest date `2026-06-18`, modified `2026-06-22 17:35:48`

Validation notes:
- update pipeline completed without fatal error or traceback
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests
- Streamlit AppTest confirmed NSW, Region, and Market Region/`REGION16` views rendered without exceptions and latest date `2026-06-18` was visible
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected and rendered an empty state in Market View
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation

### 20260615 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260615.zip`
- update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260615`
- DAT extraction directory: `RawData/DAT/2026/20260615`
- DAT files extracted: 122

Validated outputs from the 20260615 run:
- `RawData/manifest/dat_manifest.csv`: 2,883 rows, modified `2026-06-15 13:06:19`
- `Processed/fact_sales/fact_sales_2026.parquet`: 70,698 rows, latest `contract_date` `2026-06-11`, modified `2026-06-15 13:06:21`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,915 rows, latest date `2026-06-11`, modified `2026-06-15 13:06:23`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,423 rows, latest date `2026-06-11`, modified `2026-06-15 13:06:24`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 203,731 rows, latest date `2026-06-05`, modified `2026-06-15 13:06:24`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,781,027 rows, latest date `2026-06-11`, modified `2026-06-15 13:06:25`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,926,569 rows, latest date `2026-06-11`, modified `2026-06-15 13:06:26`

Validation notes:
- update pipeline completed without fatal error or traceback
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` remained selected and rendered an empty state in local Streamlit
- deployment branch: `deploy/streamlit-cloud-safe-2026-03-29`
- final commit hash is reported in the session handoff after commit creation

### 20260608 Validated Market View Update
Latest validated package:
- source package: `RawData/1 page update/20260608.zip`
- update command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260608`
- DAT extraction directory: `RawData/DAT/2026/20260608`
- DAT files extracted: 126

Validated outputs from the 20260608 run:
- `RawData/manifest/dat_manifest.csv`: 2,761 rows, modified `2026-06-08 12:44:38`
- `Processed/fact_sales/fact_sales_2026.parquet`: 67,239 rows, latest `contract_date` `2026-06-04`, modified `2026-06-08 12:44:41`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,901 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:42`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,395 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:43`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 203,557 rows, latest date `2026-06-01`, modified `2026-06-08 12:44:43`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,765,671 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:44`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,920,841 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:45`

Validation after each update must include:
- source package path and extracted DAT count
- manifest row count and package records
- fact parquet row count, schema, latest `contract_date`, and latest-period row counts
- daily rolling row counts and latest dates for NSW, region, Market Region/`region16`, suburb, and postcode
- deploy branch/folder alignment for active Streamlit-facing artifacts
- selector regression spot-checks where area options are involved

## Downstream Outputs
### Fact Sales
Per-year fact outputs:
- `Processed/fact_sales/fact_sales_<year>.parquet`

### Daily Rolling Marts
Per-geography outputs under:
- `Processed/mart_daily_rolling/`

Typical artifacts:
- `daily_rolling_nsw.parquet`
- `daily_rolling_region.parquet`
- `daily_rolling_region16.parquet`
- `daily_rolling_suburb.parquet`
- `daily_rolling_postcode.parquet`

Compatibility note:
- `daily_rolling_region16.parquet` is the legacy filename for the Market Region daily rolling layer
- Core / Extended segment overlays are included in this layer by applying `utils.region16_segments.REGION16_SEGMENT_DEFINITIONS` during mart build

### Monthly Marts
Monthly outputs under:
- `Processed/mart_monthly/`

Compatibility note:
- `mart_monthly_region16_<label>.parquet` remains the legacy filename for the Market Region monthly layer

## Operational Conventions
- update validation should confirm the latest available market date after rebuild
- rebuild validation should confirm no schema break
- rebuild validation should confirm no abnormal row-count collapse
- deployment/data-sync work should verify that processed artifacts and deployed branch state are aligned when a data refresh is intended for release
- Market View suburb/postcode selector options must be generated from stable dimensions and full rolling coverage, not from the currently filtered visible rows
- A valid suburb/postcode selection with no rows under the current dwelling/date filters must render an empty state rather than rewriting selection state

## Deployment-Relevant Notes
Current deployment baseline recorded in the docs history:
- repo/branch context: `deploy/streamlit-cloud-safe-2026-03-29`
- default app mode in deployment context: `APP_MODE = external`

These are operational notes, not product-behavior rules.
