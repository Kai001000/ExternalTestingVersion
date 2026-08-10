# Validation and Audit

This document defines what must be checked after changes.

References:
- Product behavior rules: [SYSTEM_SPEC.md](./SYSTEM_SPEC.md)
- Metric and formula rules: [METRICS_AND_LOGIC.md](./METRICS_AND_LOGIC.md)
- Data update and rebuild rules: [DATA_PIPELINE.md](./DATA_PIPELINE.md)

## Core Rule
- Every user-visible logic change must be validated against the canonical dataset and the current state model.
- Checklist items below are intended to be binary pass/fail checks.

## Global Canonical Checks
- [ ] The active code path, not a legacy helper, was used for validation.
- [ ] The source dataframe for each validated metric/output was identified.
- [ ] No active rule required for the change exists only in `HANDOFF_HISTORY.md`.
- [ ] No visible label contradicts the actual implemented logic.

## UI Refactor Checklist
Use this when the session goal is presentation-only:
- [ ] Shared visual tokens/classes were used where practical instead of adding large new page-local CSS blocks
- [ ] Any new shared UI helper remained presentation-only and did not absorb product logic
- [ ] Metric formulas remained unchanged
- [ ] Filtering semantics remained unchanged
- [ ] State ownership remained unchanged
- [ ] Map interaction semantics remained unchanged
- [ ] Shortlist identity/state semantics remained unchanged
- [ ] Report calculation inputs and outputs remained unchanged
- [ ] Public/internal mode gates remained aligned with the intended release behavior
- [ ] Validation included render checks plus at least one behavior smoke test for each touched workflow

## Public Streamlit Validation Matrix
Run these whenever public Streamlit behavior changes:
- [ ] Product introduction homepage renders and appears first in navigation
- [ ] Buy Chinese validated
- [ ] Buy English validated
- [ ] Rent Chinese validated
- [ ] Rent English validated

For each validated path:
- [ ] Filter effect matches the active controls
- [ ] Summary values match the active filtered dataset
- [ ] Listing rows match the active filtered dataset
- [ ] Displayed metrics match the active filtered dataset
- [ ] Functional behavior matches the internal baseline rather than a downgraded public path

## Market View Checklist
- [ ] Main chart renders without exception
- [ ] User-facing naming presents the legacy `REGION16` layer as Market Region where that layer is exposed
- [ ] KPI latest stable median equals the chosen chart-anchor value for the active display mode
- [ ] KPI stable cutoff date equals the chosen chart-anchor date
- [ ] KPI stable YoY is derived from the canonical stable-to-stable comparison path
- [ ] Latest market-data date is populated and sensible
- [ ] Stable median / stable cutoff date / stable YoY all align with the same active stable series
- [ ] Time-range behavior matches the documented contract
- [ ] Geography behavior matches the documented contract
- [ ] Dwelling behavior matches the documented contract
- [ ] Main KPI cards remain latest-stable summaries and are not silently rebound to the visible-window endpoint
- [ ] The median/range block is derived from stable rows within the selected visible time window only
- [ ] Price-band chart renders without exception
- [ ] Price-band chart follows the selected geography scope rather than defaulting to NSW-wide scope
- [ ] Price-band cards use the documented band summary logic
- [ ] Price-band cards follow the selected geography scope rather than defaulting to NSW-wide scope
- [ ] Price-band chart uses the visible preset while price-band cards remain latest-stable summaries
- [ ] Price-band labels do not overclaim a different anchor/comparison rule than the code uses
- [ ] `REGION / Greater Sydney / HOUSE` does not use the removed `2026-01-01` anchor override
- [ ] Forest District appears as a selectable Market Region
- [ ] Forest District Market View scope renders without exception for both `HOUSE` and `UNIT`
- [ ] Presentation-only changes do not alter latest stable median, latest stable date, stable YoY, or price-band outputs for the audited spot-check cases
- [ ] Suburb/postcode area selector state remains stable across Streamlit reruns
- [ ] Area selector widget key `mv_chart_region_area` is not overwritten only because the current dwelling/date filters return no rows
- [ ] Area options come from stable dimensions/full suburb-postcode rolling coverage, not the currently filtered visible dataframe
- [ ] Empty Market View area selections render `No data available for this selection under the current filters.` instead of resetting the selector
- [ ] Regression case: selecting `MACQUARIE PARK (2113)` with default `HOUSE + 1 Year` keeps `MACQUARIE PARK (2113)` selected and shows the empty-state message
- [ ] `MACQUARIE PARK` / postcode `2113` remains mapped to `Ryde / Northern Suburbs`
- [ ] `tests/test_market_view_area_selection.py` passes after selector or area-filter changes

### 2026-08-10 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260810.zip` was found, was readable, and was 213,986 bytes.
- [x] Pre-run DAT check found `RawData/DAT/2026/20260810` did not exist, so the normal wrapper path was used.
- [x] The primary wrapper command `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260810` completed with exit code 0.
- [x] Recovery command `.\.venv\Scripts\python.exe -X faulthandler build_mart_daily_rolling.py` was not needed; no native crash occurred.
- [x] DAT extraction directory `RawData/DAT/2026/20260810` contains 123 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,882 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 96,466 rows with latest `contract_date` `2026-08-05`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 12,025 rows with latest date `2026-08-05`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,643 rows with latest date `2026-08-05`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 206,199 rows with latest date `2026-08-03`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,909,925 rows with latest date `2026-08-05`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,976,924 rows with latest date `2026-08-05`.
- [x] Compared with 20260803: manifest rows advanced 3,759 -> 3,882; `fact_sales_2026` rows advanced 93,875 -> 96,466; NSW/Region/Suburb/Postcode max dates advanced to `2026-08-05`; Market Region/`REGION16` max date advanced to `2026-08-03`.
- [x] `fact_sales_2026` contains 19 rows after previous max `contract_date` `2026-07-30`; latest `contract_date` `2026-08-05` contains 1 row, so newest days remain provisional due to registration lag.
- [x] Duplicate-row checks returned 0 for manifest, fact, and all five `daily_rolling_*` mart files.
- [x] Region16 lag check found mapped coverage lag: after `2026-07-24`, statewide 2026 fact rows total 60, Region16-mapped rows total 12, and mapped max `contract_date` is `2026-08-03`, matching the Region16 mart max date.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`.
- [x] Runtime data-load smoke confirmed NSW, Region, Market Region/`REGION16`, Suburb, and Postcode marts load through `utils.data.load_daily_rolling`.
- [x] Streamlit AppTest rendered Market View with 0 exceptions, 0 error elements, latest date `2026-08-05` visible, period `1 Year`, level `AREA`, and selector value `MACQUARIE PARK (2113)`.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` returned 200; logs had no Traceback/Exception text; the server process was stopped and port `8510` was released.
- [x] Market View latest loaded data date is `2026-08-05`.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` from saved state variant `Macquarie Park (2113)` and produced the expected empty filtered result.

### 2026-08-03 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260803.zip` was found, was readable, and was 226,465 bytes.
- [x] The primary wrapper command `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260803` exited 1 before extraction because `RawData/DAT/2026/20260803` already existed and was non-empty; no traceback or native crash occurred.
- [x] Existing `RawData/DAT/2026/20260803` contents matched the ZIP DAT names and sizes, so `--force` was not used to clear the directory.
- [x] Direct wrapper-internal build steps completed with exit code 0: `refresh_dat_manifest.py`, `build_fact_sales_year.py --overwrite`, and `build_mart_daily_rolling.py`.
- [x] Recovery command `.\.venv\Scripts\python.exe -X faulthandler build_mart_daily_rolling.py` was not needed.
- [x] DAT extraction directory `RawData/DAT/2026/20260803` contains 123 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,759 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 93,875 rows with latest `contract_date` `2026-07-30`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 12,013 rows with latest date `2026-07-30`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,619 rows with latest date `2026-07-30`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 205,804 rows with latest date `2026-07-24`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,895,352 rows with latest date `2026-07-30`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,971,409 rows with latest date `2026-07-30`.
- [x] Compared with 20260727: manifest rows advanced 3,636 -> 3,759; `fact_sales_2026` rows advanced 91,071 -> 93,875; NSW/Region/Suburb/Postcode max dates advanced to `2026-07-30`; Market Region/`REGION16` max date advanced to `2026-07-24`.
- [x] `fact_sales_2026` contains 20 rows after previous max `contract_date` `2026-07-23`; latest `contract_date` `2026-07-30` contains 1 row, so newest days remain provisional due to registration lag.
- [x] Duplicate-row checks returned 0 for manifest, fact, and all five `daily_rolling_*` mart files.
- [x] Region16 lag check found mapped coverage lag: after `2026-07-23`, statewide 2026 fact rows total 20, Region16-mapped rows total 2, and mapped max `contract_date` is `2026-07-24`, matching the Region16 mart max date.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`.
- [x] Streamlit AppTest rendered NSW, Region, Market Region/`REGION16`, and `MACQUARIE PARK (2113)` AREA saved-state cases with 0 exceptions and latest date `2026-07-30` visible.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text; the server process was stopped and port `8510` was released.
- [x] Market View latest loaded data date is `2026-07-30`.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` from saved state variant `Macquarie Park (2113)` and produced the expected empty filtered result.

### 2026-07-27 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260727.zip` was ingested with `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260727`.
- [x] The primary wrapper completed extraction, manifest refresh, fact rebuild, and daily rolling mart rebuild with exit code 0; no native crash occurred.
- [x] Recovery command `.\.venv\Scripts\python.exe -X faulthandler build_mart_daily_rolling.py` was not needed.
- [x] DAT extraction directory `RawData/DAT/2026/20260727` contains 123 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,636 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 91,071 rows with latest `contract_date` `2026-07-23`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 11,999 rows with latest date `2026-07-23`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,591 rows with latest date `2026-07-23`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 205,735 rows with latest date `2026-07-23`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,879,654 rows with latest date `2026-07-23`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,964,927 rows with latest date `2026-07-23`.
- [x] Compared with 20260720: manifest rows advanced 3,513 -> 3,636; `fact_sales_2026` rows advanced 88,519 -> 91,071; NSW/Region max dates advanced to `2026-07-23`; Market Region/`REGION16` max date advanced to `2026-07-23`.
- [x] `fact_sales_2026` contains 15 rows after previous max `contract_date` `2026-07-16`; latest `contract_date` `2026-07-23` contains 3 rows, so newest days remain provisional due to registration lag.
- [x] Duplicate-row checks returned 0 for manifest, fact, and all five `daily_rolling_*` mart files.
- [x] Region16 lag check found no lag: Region16 mart max date is `2026-07-23`; Region16-mapped 2026 fact rows after `2026-07-09` total 14 with mapped max `contract_date` `2026-07-23`.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`.
- [x] Streamlit AppTest rendered NSW, Region, Market Region/`REGION16`, and `MACQUARIE PARK (2113)` AREA saved-state cases with 0 exceptions.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text.
- [x] Market View latest loaded data date is `2026-07-23`.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` from saved state variant `Macquarie Park (2113)` and produced the expected empty filtered result.

### 2026-07-20 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260720.zip` was ingested with `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260720`.
- [x] The primary wrapper completed extraction, manifest refresh, and fact rebuild; the mart step initially exited with native code `3221225477`.
- [x] Recovery command `.\.venv\Scripts\python.exe -X faulthandler build_mart_daily_rolling.py` completed successfully and refreshed the active rolling artifacts.
- [x] DAT extraction directory `RawData/DAT/2026/20260720` contains 127 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,513 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 88,519 rows with latest `contract_date` `2026-07-16`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 11,985 rows with latest date `2026-07-16`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,563 rows with latest date `2026-07-16`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 205,170 rows with latest date `2026-07-09`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,863,975 rows with latest date `2026-07-16`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,958,728 rows with latest date `2026-07-16`.
- [x] Compared with 20260713: manifest rows advanced 3,386 -> 3,513; `fact_sales_2026` rows advanced 86,050 -> 88,519; NSW/Region max dates advanced to `2026-07-16`; Market Region/`REGION16` max date advanced to `2026-07-09`.
- [x] `fact_sales_2026` contains 12 rows after previous max `contract_date` `2026-07-09`; newest days remain provisional due to registration lag.
- [x] Region16 latest-date lag was checked against underlying mapped fact coverage: Region16-mapped fact rows after `2026-07-09` total 0.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text.
- [x] Market View rendered latest data date `2026-07-16` in local smoke validation.
- [x] Streamlit AppTest rendered NSW, Region, and Market Region/`REGION16` views with 0 exceptions.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` from saved state variant `Macquarie Park (2113)` and produced the expected empty filtered result.

### 2026-07-13 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260713.zip` was ingested with `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260713`.
- [x] DAT extraction directory `RawData/DAT/2026/20260713` contains 127 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,386 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 86,050 rows with latest `contract_date` `2026-07-09`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 11,971 rows with latest date `2026-07-09`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,535 rows with latest date `2026-07-09`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 205,063 rows with latest date `2026-07-07`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,849,316 rows with latest date `2026-07-09`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,952,868 rows with latest date `2026-07-09`.
- [x] Compared with 20260706: manifest rows advanced 3,259 -> 3,386; `fact_sales_2026` rows advanced 83,176 -> 86,050; NSW/Region max dates advanced to `2026-07-09`; Market Region/`REGION16` max date advanced to `2026-07-07`.
- [x] `fact_sales_2026` contains 30 rows after previous max `contract_date` `2026-07-01`; newest days remain provisional due to registration lag.
- [x] Region16 latest-date lag was checked against underlying mapped fact coverage: Region16-mapped fact rows after `2026-07-01` total 5 and max at `2026-07-07`.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 8 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `utils/tables.py`, and `tests/test_market_view_area_selection.py`.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`; `/` and `/Market_View` loaded without Traceback/Exception text.
- [x] Market View rendered latest data date `2026-07-09` in local smoke validation.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` and produced the expected empty filtered result.

### 2026-07-06 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260706.zip` was ingested with `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260706`.
- [x] DAT extraction directory `RawData/DAT/2026/20260706` contains 126 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,259 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 83,176 rows with latest `contract_date` `2026-07-01`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 11,955 rows with latest date `2026-07-01`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,503 rows with latest date `2026-07-01`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 204,763 rows with latest date `2026-06-30`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,834,425 rows with latest date `2026-07-01`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,946,820 rows with latest date `2026-07-01`.
- [x] Compared with 20260629: manifest rows advanced 3,133 -> 3,259; `fact_sales_2026` rows advanced 79,472 -> 83,176; NSW/Region max dates advanced to `2026-07-01`; Market Region/`REGION16` max date advanced to `2026-06-30`.
- [x] `fact_sales_2026` contains 55 rows after previous max `contract_date` `2026-06-25`; newest days remain provisional due to registration lag.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `scripts/update_market_view_from_zip.py`, `build_fact_sales_year.py`, `refresh_dat_manifest.py`, and `build_mart_daily_rolling.py`.
- [x] Streamlit AppTest rendered NSW, Region, and Market Region/`REGION16` views without exceptions.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health`, 200 from `/`, and 200 from `/Market_View`; the server process was stopped after validation.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` and displayed the `market_view_no_selection_data` empty state.

### 2026-06-29 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260629.zip` was ingested with `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260629`.
- [x] DAT extraction directory `RawData/DAT/2026/20260629` contains 127 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,133 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 79,472 rows with latest `contract_date` `2026-06-25`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 11,943 rows with latest date `2026-06-25`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,479 rows with latest date `2026-06-25`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 204,556 rows with latest date `2026-06-25`.
- [x] `Processed/mart_daily_rolling/daily_rolling_suburb.parquet` refreshed to 9,815,097 rows with latest date `2026-06-25`.
- [x] `Processed/mart_daily_rolling/daily_rolling_postcode.parquet` refreshed to 3,939,821 rows with latest date `2026-06-25`.
- [x] Compared with 20260622: manifest rows advanced 3,006 -> 3,133; `fact_sales_2026` rows advanced 74,725 -> 79,472; core rolling max dates advanced `2026-06-18` -> `2026-06-25`.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `scripts/update_market_view_from_zip.py`, `build_fact_sales_year.py`, `refresh_dat_manifest.py`, and `build_mart_daily_rolling.py`.
- [x] Streamlit AppTest rendered NSW, Region, and Market Region/`REGION16` views without exceptions and showed latest date `2026-06-25`.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health` and 200 from `/`; the server process was stopped after validation.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` and displayed `当前选择在现有筛选条件下暂无数据。`

### 2026-06-22 Market View Data Update Validation
- [x] Source package `RawData/1 page update/20260622.zip` was ingested with `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260622`.
- [x] DAT extraction directory `RawData/DAT/2026/20260622` contains 123 `.DAT` files.
- [x] `RawData/manifest/dat_manifest.csv` refreshed to 3,006 rows.
- [x] `Processed/fact_sales/fact_sales_2026.parquet` refreshed to 74,725 rows with latest `contract_date` `2026-06-18`.
- [x] `Processed/mart_daily_rolling/daily_rolling_nsw.parquet` refreshed to 11,929 rows with latest date `2026-06-18`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region.parquet` refreshed to 23,451 rows with latest date `2026-06-18`.
- [x] `Processed/mart_daily_rolling/daily_rolling_region16.parquet` refreshed to 204,238 rows with latest date `2026-06-18`.
- [x] `.\.venv\Scripts\python.exe -m pytest` was attempted; current `.venv` does not have `pytest` installed.
- [x] `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests.
- [x] `py_compile` passed for `home.py`, `pages/1_Market_View.py`, `utils/data.py`, `utils/i18n.py`, `utils/market_view_area.py`, `scripts/update_market_view_from_zip.py`, `build_fact_sales_year.py`, `refresh_dat_manifest.py`, and `build_mart_daily_rolling.py`.
- [x] Streamlit AppTest rendered NSW, Region, and Market Region/`REGION16` views without exceptions and showed latest date `2026-06-18`.
- [x] Local Streamlit server smoke on port `8510` returned 200 from `/_stcore/health` and 200 from `/`; the server process was stopped after validation.
- [x] Regression case `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` kept the selector on `MACQUARIE PARK (2113)` and displayed `当前选择在现有筛选条件下暂无数据。`

## Market Region Validation
- [ ] Region exists in the canonical Market Region mapping
- [ ] Region appears in the relevant rolling parquet output
- [ ] Selector exposes the region where Market Region options are shown
- [ ] KPI and chart render correctly for the region
- [ ] No null postcode leakage remains for the intended mapped postcodes
- [ ] No code or validation path assumes a fixed number of regions in the layer
- [ ] Derived Market Region segment overlays come from `utils/region16_segments.py`, not duplicated local constants
- [ ] Lower North Shore Core / Extended validation confirms Core postcodes `2060`, `2061`, `2088`, `2089`, `2090` and Extended postcode `2067`

## Buy Checklist
- [ ] Sale filters apply correctly to the canonical sale filtered dataset
- [ ] Applied-state persistence matches the active visible controls
- [ ] Applied summary matches the canonical sale filtered dataset
- [ ] Listing browser rows match the canonical sale filtered dataset
- [ ] Map uses the canonical sale filtered universe
- [ ] Focused suburb does not redefine the global filtered universe
- [ ] Browser rows recompute from the latest focused suburb after map interaction
- [ ] Listing selection remains subordinate to focused suburb
- [ ] Shortlist behavior matches the canonical sale listing identity/state model
- [ ] Sale report generation still works for at least one shortlisted listing after the change
- [ ] Sale report still matches the selected listing and active sale page dataset

## Rent Checklist
- [ ] Rent filters apply correctly to the canonical rent filtered dataset
- [ ] Applied-state persistence matches the active visible controls
- [ ] Applied summary matches the canonical rent filtered dataset
- [ ] Listing browser rows match the canonical rent filtered dataset
- [ ] Map uses the canonical rent filtered universe
- [ ] Focused suburb does not redefine the global filtered universe
- [ ] Browser rows recompute from the latest focused suburb after map interaction
- [ ] Listing selection remains subordinate to focused suburb
- [ ] Rent search submit still works with an updated weekly rent range after the change

## Buy / Rent Parity Checklist
- [ ] Buy and Rent use consistent filter semantics where parity is required
- [ ] Buy and Rent use consistent applied-state persistence semantics
- [ ] Buy and Rent use consistent summary semantics
- [ ] Buy and Rent use consistent map/browser synchronization semantics
- [ ] Buy and Rent do not rely on a shared canonical filtered listing dataset

## Chinese / English Parity Checklist
- [ ] Chinese and English use the same active filter behavior
- [ ] Chinese and English use the same active metric behavior
- [ ] Chinese and English use the same map/browser behavior
- [ ] Chinese and English use the same shortlist/report behavior where applicable
- [ ] No meaningful UI text is missing in one language path after the change

## Export / Report Checklist
- [ ] At least one real shortlisted listing exports successfully
- [ ] Report/PDF generation completes without crash
- [ ] Every required report section populates or degrades gracefully
- [ ] Listing metrics in the report match the active page dataset
- [ ] Suburb/context metrics in the report match the intended canonical source dataset
- [ ] Comparable listings in the report come from the intended canonical universe
- [ ] No stale dataframe or hidden refilter mismatch exists between browser, shortlist, metrics, and report values
- [ ] Public Streamlit report/export behavior matches the internal/full functional path
- [ ] Sale report page order matches the current canonical narrative structure
- [ ] Hero Summary appears first and is consistent with the downstream section evidence
- [ ] Each major section includes explanatory narrative rather than a metric-only dump
- [ ] Transaction-market geography scope is stated explicitly
- [ ] Postcode fallback is stated explicitly when suburb transaction coverage is insufficient
- [ ] Price-band geography scope matches the chosen transaction-market geography scope
- [ ] Active-sale comparison scope is stated explicitly, including any widening from tighter comparable criteria
- [ ] Rent scope is stated explicitly, including any widening/fallback
- [ ] Budget sensitivity uses the canonical sale filtered universe and documented budget-step rule
- [ ] No raw local dataset path, parquet path, or debug-style source path appears in the visible PDF

## Mode Rebase Checklist
- [ ] Internal mode follows the refined baseline product path rather than the retired legacy-internal path
- [ ] Retired internal-only pages or branches no longer act as default navigation
- [ ] Public Streamlit keeps the product intro homepage while functional pages use full internal behavior
- [ ] Public/external downgrade gates do not hide counts, links, shortlist, maps, tables, or reports on functional pages
- [ ] No separate hidden public baseline overrides the internal functional path

## Public Release Checklist
- [ ] App starts with the product introduction homepage first
- [ ] Market View renders with full internal data behavior
- [ ] Buy Budget renders with full internal data and interaction behavior
- [ ] Rent Budget renders with full internal data and interaction behavior
- [ ] Navigation exposes only the intended public homepage plus current functional pages
- [ ] Download, export, shortlist, map, table, and listing-link controls are not disabled only because of public deployment
- [ ] Report download controls are hidden or disabled in public deployment until reports are production-ready
- [ ] User-facing UI does not expose specific upstream listing platform names
- [ ] User-facing provenance wording uses neutral market/listing/record terminology
- [ ] Public deploy consumes the same processed/current artifacts included for internal functional behavior

## Data Pipeline Checklist
- [ ] Required update/rebuild script completed without crash
- [ ] Expected output artifacts were refreshed
- [ ] Output timestamps are recent for the touched artifacts
- [ ] Latest available date in rebuilt data is sensible
- [ ] Latest-period row counts are recorded for newly added dates
- [ ] Row count did not collapse abnormally
- [ ] Schema did not break unexpectedly
- [ ] Market Region mapping postcodes expected for the change are populated and not null in the compatibility dim
- [ ] Legacy `region16` outputs were refreshed if the Market Region layer changed
- [ ] Deployment/data-sync assumptions were rechecked if the rebuild is intended for release
- [ ] Macquarie Park / postcode `2113` still appears after Market View data updates

### 2026-06-15 Market View Data Refresh Validation
- [x] Required update/rebuild script completed without crash: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260615`
- [x] Source ZIP found: `RawData/1 page update/20260615.zip`
- [x] DAT extraction directory exists: `RawData/DAT/2026/20260615`
- [x] DAT count recorded: 122
- [x] Manifest refreshed: 2,883 rows, modified `2026-06-15 13:06:19`
- [x] Fact sales refreshed: `fact_sales_2026.parquet`, 70,698 rows, max `contract_date` `2026-06-11`
- [x] Daily rolling refreshed for NSW, Region, Market Region/`region16`, suburb, and postcode
- [x] Local Streamlit smoke test loaded Market View with latest visible date `2026-06-11`
- [x] NSW, Region, and Market Region views rendered without UI exception in local Streamlit smoke validation
- [x] `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` rendered an empty state while keeping the selected area stable
- [x] Pipeline and smoke validation produced no fatal error or traceback
- [x] Full pytest was attempted, but local virtual environments do not currently include `pytest`
- [x] Selector regression unit coverage passed via `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection`

## Public Full-Data Validation
- [ ] Public Streamlit Market View renders without crash
- [ ] Public Streamlit reads `Processed/mart_daily_rolling/` for daily trend data
- [ ] Price-band logic can use the full internal fact-sales path
- [ ] Latest visible date matches the deployed processed data
- [ ] Internal and external deployment modes show the same default Market View KPI/date values for the same filters
- [ ] Market View deploy acceptance explicitly records latest market date, stable anchor date, and stable median
- [ ] KPI outputs remain consistent with the internal logic path
- [ ] No fallback to cache paths exists in runtime behavior

## Deploy Data Git Validation
Run these checks before every Streamlit deploy data update:
- [ ] Check for hidden local data changes with `git ls-files -v Processed data/current | findstr "^[S]"`
- [ ] If any target deploy data file is marked skip-worktree, clear it first with `git update-index --no-skip-worktree <file>`
- [ ] Do not rely only on `git status` for deploy data; skip-worktree can hide local parquet changes
- [ ] Compare the deploy/index content against local data with `git show HEAD:<file>` or an equivalent index/checkout read
- [ ] For parquet deploy files, verify row count and max date from both local file and `HEAD:<file>` before committing
- [ ] For Market View deploy acceptance, verify latest market date, stable anchor date, and stable median after the commit candidate is staged

## Audit Checklist
- [ ] Each visible component under audit was mapped to its active source function
- [ ] Each visible metric under audit was mapped to its source dataframe
- [ ] Geography filtering logic was verified
- [ ] Dwelling filtering logic was verified
- [ ] Time-range filtering logic was verified
- [ ] Anchor logic was verified
- [ ] Fallback behavior was explicitly identified
- [ ] Results were classified as confirmed correct, confirmed broken, or needs follow-up

## High-Risk Drift / Mismatch Checks
- [ ] No stale dataframe usage was introduced
- [ ] No hidden refiltering changed scope silently
- [ ] No independent recomputation uses a different anchor logic without documentation
- [ ] No map/browser/report output comes from a mismatched universe
- [ ] No active rule is duplicated across canonical docs with conflicting wording
