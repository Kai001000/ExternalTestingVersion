# Architecture

## Technical Stack
- Python
- Streamlit
- Plotly
- Polars
- Pandas

## Project Structure
```text
home.py

pages/
  0_External_Home.py
  1_Market_View.py
  2_Ranking.py
  3_Buy_Budget.py
  4_Rent_Budget.py

utils/
  data.py
  charts.py
  tables.py
  metrics.py
  map_view.py
  i18n.py
  ui.py
  ui_style.py
  ranking_view.py
  config.py
  perf.py
```

## Application Entry Points
- `home.py` is the main Streamlit entry point
- page modules under `pages/` own the user-facing workflows
- shared logic lives under `utils/`
- operational update scripts live at repo root and under `scripts/`

## Performance Instrumentation
- performance instrumentation helper: `utils/perf.py`
- page timing logs: `logs/page_timings.jsonl`
- performance instrumentation is an implementation/operations aid, not a product-behavior contract

## Shared UI Layer
- `utils/ui.py` owns shared theme injection and common sidebar/header hooks
- `utils/ui_style.py` owns shared internal visual tokens and reusable presentation helpers such as hero blocks, card shells, filter-panel wrappers, and semantic chip styles
- shared UI helpers are presentation-only and must not become a second source of truth for metrics, filter state, map state, shortlist state, or report logic

## Public Streamlit Data Layer
- public Streamlit uses the same full functional data paths as internal mode
- Market View reads the pipeline-backed `Processed/mart_daily_rolling/` and `Processed/fact_sales/` datasets
- Buy Budget and Rent Budget read the current listing datasets under `data/current/`
- `Processed/dim/` remains the canonical dimension layer for geography attribution
- `data/public_market_view/` is retained only as a legacy snapshot layer and is not the active full-public runtime path
- `data/cache/` remains disposable and must not act as a runtime dependency

## Page and Module Responsibilities
### Market View
Responsibilities:
- rolling-median market trend display
- stability-aware KPI display
- price-band trend display
- geography/dwelling/time-range controls
- internal presentation may reuse the shared hero/filter/card system while preserving the existing KPI, chart, and price-band data paths

Key dependencies:
- daily rolling marts
- chart helpers
- stability helpers
- i18n helpers

### Ranking
Responsibilities:
- retired page stub only
- prevents the legacy internal ranking workflow from acting as an active product path

### Buy Budget
Responsibilities:
- sale listing filtering
- shortlist workflows
- suburb focus and listing browser behavior
- sale map/list interaction
- sale PDF/report workflows where enabled
- internal presentation may reuse shared UI helpers, but the page must continue to own its canonical sale filtered dataset and report context path

Sale report workflow notes:
- the current local iteration path may generate a sale PDF outside the Streamlit UI for faster report development
- this local path must still reuse canonical Buy Budget and Market View logic/data rather than introduce an independent report-only metric framework
- reusable report-generation logic lives under `utils/`
- local sample/iteration entrypoints live under `scripts/`

### Rent Budget
Responsibilities:
- rent listing filtering
- suburb focus and listing browser behavior
- rent map/list interaction
- internal presentation may reuse shared UI helpers, but the page must continue to own its canonical rent filtered dataset and must not mix sale/rent pipelines

## State Model
Canonical page-state layers:
- top-level filters define the filtered result universe
- focused suburb is a local interaction/view state
- selected listing is subordinate to focused suburb

State-model rules:
- visible controls must be the real source of truth
- translated labels must not become persisted canonical keys
- hidden legacy state must not override active visible controls
- pagination/detail-panel changes must not incorrectly mutate the map universe
- persisted state must use stable canonical keys rather than translated display labels

## External / Internal Boundaries
### Public Streamlit Mode
- keeps the product introduction homepage as page 0
- functional pages run the full internal product behavior
- public/external downgrade gates should be bypassed for functional pages
- no separate public-restricted product branch should be used for Market View, Buy Budget, or Rent Budget
- safety gates still read the raw deployment mode to hide unfinished report downloads and upstream listing platform names in public deployment

### Internal Mode
- runs the same refined full product path as public Streamlit functional pages
- remains the local review and development baseline

## Data Flow by Page
### Market View
- reads daily rolling marts by selected geography level
- derives stable flags, visible chart series, and KPI anchors from the selected scope
- price-band section uses the filtered sales fact path for band construction

### Buy Budget
- reads the sale listing dataset
- constructs a page-specific canonical filtered sale dataset
- drives map, listing browser, shortlist, and sale-report outputs from that page dataset
- local sale-report generation for iteration must resolve the target listing from the current sale listing data, then derive report sections from the same canonical filtered universe and reused metric/helper paths

### Rent Budget
- reads the rent listing dataset
- constructs a page-specific canonical filtered rent dataset
- drives map, listing browser, and rent-side outputs from that page dataset

## Architecture Notes Promoted From Handoffs
- the public Streamlit functional workflow is aligned with the full internal version
- public restrictions are not active on functional pages; only the product introduction homepage remains public-specific
- public deployment safety gates remain active for source-label suppression and report-download suppression
- Buy and Rent must continue to use separate listing datasets and separate filtered-universe pipelines
- focused suburb must not be treated as the page-global filter source of truth
- map highlight and browser sync must be maintained together when interaction logic changes
- layout/state work should preserve a single source of truth for filtered scope, focused suburb, and selected listing
- listing selection should continue to use the single-map path rather than duplicate map render paths
- visible controls must remain the effective source of truth and must not be shadowed by hidden legacy state
- the shared theme injector currently applies globally; future cleanup may narrow internal-only styling more explicitly without reintroducing functional-page public downgrades
