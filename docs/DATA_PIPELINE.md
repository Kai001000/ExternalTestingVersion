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

## Deployment-Relevant Notes
Current deployment baseline recorded in the docs history:
- repo/branch context: `deploy/streamlit-cloud-safe-2026-03-29`
- default app mode in deployment context: `APP_MODE = external`

These are operational notes, not product-behavior rules.
