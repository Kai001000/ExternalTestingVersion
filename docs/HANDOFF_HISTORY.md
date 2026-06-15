# Handoff History

## Authority Rule
- Current truth lives in the canonical topic files:
  - `SYSTEM_SPEC.md`
  - `ARCHITECTURE.md`
  - `METRICS_AND_LOGIC.md`
  - `DATA_PIPELINE.md`
  - `VALIDATION_AND_AUDIT.md`
- `HANDOFF_HISTORY.md` records dated session history and rationale.
- The latest dated handoff overrides earlier handoffs only until its resulting active rule has been incorporated into the canonical docs.
- Older handoffs remain historical context and must not silently override the current topic-based specs.

## Reverse-Chronological Session Record

### 2026-06-15 — Market View Weekly Data Update 20260615

Context: weekly Market View data refresh | Streamlit deploy branch data sync | selector empty-state regression check

Source and command:
- Source package: `RawData/1 page update/20260615.zip`
- Command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260615`
- DAT destination: `RawData/DAT/2026/20260615`
- DAT files extracted: 122

Validated outputs:
- `RawData/manifest/dat_manifest.csv`: 2,883 rows, modified `2026-06-15 13:06:19`
- `Processed/fact_sales/fact_sales_2026.parquet`: 70,698 rows, latest `contract_date` `2026-06-11`, modified `2026-06-15 13:06:21`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,915 rows, latest date `2026-06-11`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,423 rows, latest date `2026-06-11`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 203,731 rows, latest date `2026-06-05`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,781,027 rows, latest date `2026-06-11`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,926,569 rows, latest date `2026-06-11`

Validation:
- Pipeline completed successfully with no fatal error or traceback.
- `.\.venv\Scripts\python.exe -m pytest` was attempted but the `.venv` environment does not have `pytest` installed.
- `.\.venv311\Scripts\python.exe -m pytest` was attempted but `.venv311` also does not have `pytest` installed.
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed: 7 tests.
- Local Streamlit smoke test used `home.py` on port `8510`; Market View loaded, latest date `2026-06-11` was visible, and NSW / Region / Market Region views showed no UI exception.
- `MACQUARIE PARK (2113)` + `HOUSE` + `1 Year` rendered the empty-state message and kept `MACQUARIE PARK (2113)` selected.

Deployment sync:
- Branch: `deploy/streamlit-cloud-safe-2026-03-29`
- Active deploy data files are the tracked `Processed/fact_sales/`, `Processed/mart_daily_rolling/`, and `RawData/manifest/dat_manifest.csv` artifacts.
- `RawData/DAT/` and weekly source zip files remain ignored raw inputs and were not staged for deployment.
- Final commit hash is reported in the session handoff after commit creation.

### 2026-06-08 — Market View Area Selector Fix And 20260608 Data Sync

Context: Market View suburb/postcode selector | Macquarie Park empty state | weekly data refresh | deploy branch data parity

What changed:
- Fixed the Market View area selector reset bug for `mv_chart_region_area`.
- Root cause: `_prepare_region_selector_state()` treated a valid area with no visible rows under the current dwelling/date filters as invalid and overwrote `st.session_state["mv_chart_region_area"]` before the selectbox rendered.
- Regression case: `MACQUARIE PARK (2113)` exists as suburb `MACQUARIE PARK`, postcode `2113`, mapped to `Ryde / Northern Suburbs`; default `HOUSE + 1 Year` has no visible rows and must keep the selection while showing an empty-state message.
- Area options now come from stable suburb/postcode dimension plus full rolling suburb/postcode coverage, not from the currently visible filtered rows.
- Downstream area filtering now uses normalized suburb/postcode comparison.
- Empty-state copy: `No data available for this selection under the current filters.`

Files involved in selector fix:
- `pages/1_Market_View.py`
- `utils/market_view_area.py`
- `utils/i18n.py`
- `tests/test_market_view_area_selection.py`

20260608 data update:
- Source package: `RawData/1 page update/20260608.zip`
- Command: `.\.venv\Scripts\python.exe scripts\update_market_view_from_zip.py --date 20260608`
- DAT destination: `RawData/DAT/2026/20260608`
- DAT files extracted: 126
- `RawData/manifest/dat_manifest.csv`: 2,761 rows, modified `2026-06-08 12:44:38`
- `Processed/fact_sales/fact_sales_2026.parquet`: 67,239 rows, latest `contract_date` `2026-06-04`, modified `2026-06-08 12:44:41`
- `Processed/mart_daily_rolling/daily_rolling_nsw.parquet`: 11,901 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:42`
- `Processed/mart_daily_rolling/daily_rolling_region.parquet`: 23,395 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:43`
- `Processed/mart_daily_rolling/daily_rolling_region16.parquet`: 203,557 rows, latest date `2026-06-01`, modified `2026-06-08 12:44:43`
- `Processed/mart_daily_rolling/daily_rolling_suburb.parquet`: 9,765,671 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:44`
- `Processed/mart_daily_rolling/daily_rolling_postcode.parquet`: 3,920,841 rows, latest date `2026-06-04`, modified `2026-06-08 12:44:45`

Validation:
- `.\.venv\Scripts\python.exe -m unittest tests.test_market_view_area_selection` passed, 7 tests.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests` passed, 7 tests total.
- `py_compile` passed for the active entry/page/data/update modules.
- `app.py` was not present in the repo root; local static validation used `home.py` and `pages/1_Market_View.py`.

Deployment sync:
- Branch: `deploy/streamlit-cloud-safe-2026-03-29`
- Synced/committed active Streamlit-facing processed artifacts under `Processed/fact_sales/` and `Processed/mart_daily_rolling/`, plus `RawData/manifest/dat_manifest.csv`.
- Commit: `8c7af59069b8d3dbc5817d0c69e40c8fc6a3e351` (`Update Market View data for 20260608`)
- Push status: not pushed.
- `data/public_market_view/` remains a legacy snapshot layer and was not updated for this run.

### 2026-05-28 — Market Region Segment Definition Consolidation

Context: Market Region overlays | REGION16 compatibility | Lower North Shore Core / Extended

What changed:
- `REGION16_SEGMENT_DEFINITIONS` was consolidated into `utils/region16_segments.py`.
- `utils/data.py` and `build_mart_daily_rolling.py` now import the shared segment definitions instead of carrying duplicated constants.
- The base `dim_region16_mapping.csv` continues to define base Market Regions such as Lower North Shore.
- Lower North Shore Core / Extended remain derived postcode-expanded segment overlays; postcode membership was not changed.

Validation target:
- `daily_rolling_region16.parquet` should continue to contain Lower North Shore, Lower North Shore — Core, and Lower North Shore — Extended.
- Lower North Shore Core postcodes remain `2060`, `2061`, `2088`, `2089`, `2090`; Extended remains `2067`.

### 2026-05-08 — Homepage Redesign And Deploy Market Data Sync

Context: Streamlit Cloud data parity | homepage product narrative | cache invalidation

What changed:
- Deploy branch Market View processed parquet files were synced to the latest local internal data.
- Root cause of the Cloud/local mismatch was that the local latest parquet files were marked skip-worktree, so `git status` hid their difference from the deploy branch. The deploy commit still contained older 2026-04-16 Market View files.
- Market View daily rolling and fact-sales cache keys now include source file size/modified time so redeploys or data-file refreshes invalidate stale cached reads without removing page-level caching.
- Product homepage was redesigned around the data-source advantage: NSW Valuation / government property records, normal transactions, and off-market coverage.
- Fix commit: `de2cf0a210ac5f818414d5efd95a53cd63d21b83`.

Validation target:
- Default Market View should show data updated to 2026-04-30 with stable median $980,000 and stable cutoff 2026-03-26 for the same default NSW / HOUSE selection in both internal and external deployment modes.

Deploy data rule added:
- Before every Streamlit deploy data update, run `git ls-files -v Processed data/current | findstr "^[S]"`.
- If a target deploy data file is marked skip-worktree, clear it with `git update-index --no-skip-worktree <file>`.
- Do not rely only on `git status`; confirm deploy/index parquet content with `git show HEAD:<file>` or an equivalent index/checkout read.
- Market View deploy acceptance must record latest market date, stable anchor date, and stable median.

### 2026-05-08 — Public Deployment Safety Gates For Source Labels And Reports

Context: public Streamlit safety patch | full internal behavior retained | report and source-label restrictions

What changed:
- Public deployment keeps full internal analytical behavior and the existing product intro landing page.
- Public deployment safety gates remain active separately from functional mode.
- Specific upstream listing source names must not appear in user-facing UI, captions, warnings, table/report text, or report outputs.
- User-facing wording should use neutral labels such as `market listing data`, `listing data`, `market data`, and `publicly available market records`.
- Report download remains internal-only until the report feature is production-ready.

Validation target:
- `APP_MODE=internal` may show internal report-download controls where implemented.
- `APP_MODE=external` keeps the same functional pages but suppresses report download entry points and source-platform labels.

### 2026-05-08 — Public Streamlit Full Internal Alignment

Context: Streamlit Cloud release alignment | public homepage retained | full internal functional behavior

What changed:
- Public Streamlit now keeps the product intro landing page as the first page.
- Functional pages now follow full internal behavior:
  - Market View
  - Buy Budget
  - Rent Budget
- External/public downgrades were removed or bypassed for functional pages by making public deployment run the internal/full mode gates.
- Public deploy data expectation is now: the public Streamlit app follows the latest internal `Processed/` and `data/current/` artifacts included in the deployment.
- Performance checks and caching audit completed for the touched release path:
  - parquet/listing/dimension loads are cached through existing `st.cache_data` paths
  - functional pages load their own datasets on page entry
  - Market View keeps daily rolling, fact-sales, dimension, and price-band computations behind cached helpers
  - Buy/Rent listing reads remain cached and page-local

Validation:
- Required compile and local Streamlit smoke checks were run for this release pass.
- Public-specific homepage remains in navigation while functional pages use internal/full behavior.

### 2026-05-02 — Public Release Preparation + Session Close Handoff

Context: public/external release preparation | Streamlit sharing posture | product-safe public surface

What was decided:
- Public link sharing is acceptable for early testing and lightweight distribution, provided the app runs as a product-safe downgraded public surface.
- Market View can act as the first public-facing analytical surface because it is the most deployment-safe and least sensitive workflow.
- Buy Budget and Rent Budget may remain visible in navigation during public testing, but pages or features that are not ready for public use must be guarded so navigation cannot expose full internal behavior.
- External/public mode must not expose raw internal data, unrestricted exports, sensitive outbound listing links, or internal tooling.
- Internal mode remains the usable local baseline for review, debugging, and deeper product iteration.

Why it matters:
- Streamlit public sharing provides a low-friction way to test distribution while heavier commercialization is still uncertain.
- Initial Xiaohongshu outreach produced low conversion, so a simple public link can be used to collect lightweight feedback before investing in more complex acquisition or sales infrastructure.
- Public mode must protect trust, data footprint, and product boundaries even when the link is easy to access.

Current recommended public release posture:
- Treat external mode as a controlled public demo/test surface, not as the full internal product.
- Lead with Market View or another explicitly approved public-safe landing path.
- Keep unfinished Buy/Rent capabilities guarded, disabled, or clearly unavailable until validated for public exposure.
- Prefer simple public link access for early testing; do not add authentication or heavy commercialization layers until product demand is clearer.

Internal vs public behavior expectations:
- Internal mode may continue using full `Processed/` data, local report generation, debug/research utilities, and richer review workflows.
- Public mode must consume only approved public-safe outputs and must remain stricter than internal mode.
- Public mode should degrade capability intentionally rather than silently exposing internal paths.
- Public-visible messaging should be concise, product-facing, and clear about test/reference-only status.

Risks / safeguards:
- Navigation must not bypass public guards on pages that are visible but not release-ready.
- Public mode must hide or disable raw tables, unrestricted downloads, full exports, sensitive listing links, and internal/debug affordances.
- External Market View must continue using the public snapshot layer and must not fall back to full fact data or cache paths.
- Any public release check must validate mode, navigation, Page 1 rendering, guard behavior, and absence of raw/export/link exposure.

Next-session instructions:
- Start by checking whether the intended public entry path is the external homepage or Market View and verify navigation order accordingly.
- Validate public mode before sharing any Streamlit link.
- If Buy/Rent remain visible, confirm their guarded states cannot expose full listing/export/link functionality.
- Do not broaden public functionality until the corresponding page passes the public-release checklist.
- Keep commercialization experiments lightweight until stronger conversion evidence exists.

### 2026-04-28 — Public Data Snapshot Architecture + External Stability Fix

Context: Market View + Deployment + Data Strategy

What was done:
- Introduced `data/public_market_view/` as the canonical external dataset for Market View deployment.
- External Market View now reads only from lightweight public snapshots.
- Internal mode continues using full `Processed/` data.
- Removed dependency on `data/cache/` as a runtime source.
- Fixed the `st.session_state` widget ordering bug for `mv_chart_region_area`.

Why:
- Streamlit Cloud cannot safely rely on the full `Processed/` parquet footprint.
- External mode needs a deterministic, deploy-safe dataset rather than implicit local/full-pipeline assumptions.
- Cache-based runtime behavior is undefined for deployment and must not be treated as canonical data.
- External runtime stability depends on avoiding heavy fact loads and widget/session ordering failures.

Validation:
- External Market View renders without crash.
- External Market View shows the latest available public snapshot data (`2026-04-22`).
- External mode does not load full `fact_sales`.
- Internal mode continues using the latest full local data.
- Market View KPI outputs remained unchanged for the audited cases after the session-state fix.

Known constraints:
- The public snapshot is intentionally reduced to a 36-month window.
- External price-band support is intentionally limited to predefined public scopes.

### 2026-04-26 — Internal UI Refactor Baseline + Shared Visual System

Context: internal UI presentation refresh | shared styling layer | Market View + Buy + Rent alignment

Changes:
- Added a shared internal visual system through `utils/ui_style.py`, including reusable hero, card, filter-panel, chip, and semantic-tone styling.
- Updated the shared theme entry path in `utils/ui.py` so the common theme injector applies the new shared visual layer.
- Refreshed internal presentation on:
  - Market View
  - Buy Budget
  - Rent Budget
- Kept the session within a UI-only boundary: presentation changed, but metrics, filtering, state, map behavior, shortlist behavior, report calculations, and public restrictions were preserved.
- Closed a pre-existing Buy sale-report regression by aligning the report price-band helper with the current Market View `load_price_band_data(level, regions_selected, dwelling)` contract and the canonical transaction-geography scope rule.

Validation summary:
- `py_compile` completed for the touched pages and shared helpers.
- Streamlit/AppTest render checks completed for:
  - External Home
  - Market View
  - Buy Budget
  - Rent Budget
- Market View spot-checks confirmed no change to latest stable median, latest stable date, stable YoY, or price-band outputs for:
  - `NSW / HOUSE`
  - `Greater Sydney / HOUSE`
  - `Forest District / HOUSE`
  - `NSW / UNIT`
- Buy validation confirmed:
  - filter/search render path still works
  - focused-suburb and selected-listing state rules still hold
  - shortlist add/remove still works
  - sale report PDF generation still works without leaking raw local/debug paths
- Rent validation confirmed:
  - search submit with changed weekly-rent range still works
  - focused-suburb and selected-listing state rules still hold
  - shortlist add/remove still works
- External/public smoke checks confirmed:
  - external homepage still renders
  - public restriction gates still hold
  - property-type labels in public Buy/Rent still hide numeric counts

Rules promoted:
- Visual refactors may change presentation hierarchy and shared styling structure, but must not change product behavior, calculations, state ownership, map semantics, report semantics, or public restriction behavior.
- Shared UI helpers must remain presentation-only and must not become a hidden logic layer.

Known technical debt:
- `inject_app_theme()` currently applies globally rather than through a narrower internal-only theme boundary.
- Legacy page-local CSS remains in the homepage, Market View, Buy, and Rent pages.
- Some page styling remains duplicated and should be consolidated later into shared helpers/tokens.
- Non-blocking warnings remain:
  - Streamlit `use_container_width` deprecation warnings
  - pandas `fillna` future warning in Market View

### 2026-04-26 — Sale Report Positioning Workflow + Narrative Canonicalization

Context: Buy Budget sale report workflow | local PDF iteration | narrative report structure

Changes:
- Added a local single-listing sale-report workflow that writes report artifacts into the repo `reports/` folder for fast iteration outside the Streamlit UI.
- Promoted a canonical reuse order for report calculations: existing UI-visible logic first, existing hidden helpers second, narrowly scoped canonical-aligned calculations only when necessary.
- Promoted explicit geography and fallback disclosure rules for transaction, price-band, current-sale, and rent sections in the sale report.
- Promoted a narrative-first report structure centered on listing positioning, including a Hero Summary and revised page order.

Rules promoted:
- Sale reports must answer the core question `What is the positioning of this listing?`
- Transaction-market sections use suburb first and postcode fallback when suburb transaction coverage is insufficient for stable series or valid charting.
- Price-band performance remains geography-dependent and must use the same chosen transaction geography scope as the transaction section.
- Current active-sale comparison sections use suburb as the primary scope and must disclose any widening from tighter comparable criteria.
- Rent sections prefer geography + property type, include bedroom matching when reliable, and must disclose widened/fallback scope.
- The visible PDF must not expose raw local dataset paths, parquet paths, or debug-style source paths.
- The sale report must use the canonical narrative page order with Hero Summary first and explanatory narrative in every major section.

Notes:
- The initial implementation was exercised through a single sample listing for local iteration, but the promoted rules apply to reusable sale-report logic rather than to that one address.

The content below is preserved from the prior `MASTER_SPEC.md` handoff/history section so the dated record and session rationale are not lost.
### 2026-04-21 — External Homepage Productization + Rent/Sale UI Alignment + Cloud Deployment Stabilization

Context: External landing experience | Rent/Sale product parity | Streamlit Cloud runtime stabilization

#### 1. What Changed
- The external first page was upgraded from a test-version notice into a product-style landing page.
- Homepage positioning is now simpler and more product-facing:
  - no `free` framing
  - no heavy disclaimer tone
  - NSW presented as the clear coverage scope
  - feedback invitation made explicit and intentional
- The external homepage now follows a clearer structure:
  - hero statement
  - 3 key fact cards
  - 4 secondary guidance cards
  - softer closing note
- Rent was brought into alignment with Sale as the canonical reference surface rather than continuing as a separately shaped page.
- Rent now follows the same interaction model as Sale:
  - paginated suburb ranking
  - left-side map / right-side listing browser shell
  - aligned listing browser and detail-panel structure

#### 2. Rendering And UX Outcome
- Homepage HTML rendering was stabilized so the page no longer exposes raw HTML fragments in the UI.
- The homepage card system was unified into one consistent layout model rather than mixing broken HTML wrappers and looser native blocks.
- Spacing and padding were tightened so the landing page reads as a coherent product surface rather than a notice page with empty boxes.
- The end result is that external mode now opens on a cleaner product landing page, while Buy/Rent continue to behave as the public-restricted layer on top of the shared baseline product.

#### 3. Deployment / Runtime Lesson
- Streamlit Cloud exposed missing runtime dependencies that were already present locally, which caused Sale-page import failures even though local development appeared healthy.
- The missing runtime packages identified in this session were:
  - `matplotlib`
  - `reportlab`
- Both were added to `requirements.txt`.
- Operational takeaway: local success is not enough for Streamlit Cloud deployment; any package imported at module load time must be explicitly represented in the cloud runtime dependency file.

#### 4. Final Product State
- Internal mode remains the baseline product workflow.
- External mode now presents:
  - a product-style landing homepage
  - the same baseline product surface underneath
  - the intended public restrictions on top
- Rent and Sale now feel materially closer to the same product system instead of two differently designed workflows.

#### 5. Doc Impact
- No canonical product-spec update was required.
- This session changed presentation quality, UI parity, and deployment stability, but did not redefine the underlying product architecture or mode model.

### 2026-04-21 — Rent UX Alignment To Sale + Public Report Placeholder Buttons

Context: Rent/Sale UX parity | Mojibake cleanup | Public placeholder reports

#### 1. What Changed
- Brought the Rent page onto the Sale interaction model instead of leaving Rent on its older scroll/list layout.
- Rent suburb ranking now uses the same paginated table pattern as Sale.
- Rent now uses the same side-by-side shell as Sale:
  - map panel on the left
  - listing browser on the right
  - fixed-height panel treatment
- Rent listing browsing now mirrors Sale more closely:
  - paginated card list
  - selected-listing detail state
  - same-suburb follow-on panel
  - suburb-scoped browser behavior
- Public report controls now stay visible and intentionally non-downloading:
  - Rent shortlist public mode shows a visible report button with in-development messaging
  - Buy shortlist review public mode uses the same placeholder-button model
- Normalized remaining touched shortlist labels:
  - `打开 shortlist 工作区`
  - `查看`
  - `对比`

#### 2. Root Causes Addressed
- Rent divergence: the Rent page had retained an older ranking/browser architecture after Sale moved to the map-plus-browser shell, which made the two surfaces feel like separate products.
- Visible corruption in touched shortlist UI: a few surviving shortlist/workspace strings were still corrupted and needed literal normalization in the page files.
- Public report affordance mismatch: public mode needed an intentional placeholder interaction instead of a hidden control or a dead-looking download state.

#### 3. Validation Summary
- `python -m py_compile home.py utils\i18n.py pages\3_Buy_Budget.py pages\4_Rent_Budget.py`
- `rg -n "\?\?\?" home.py utils\i18n.py pages\3_Buy_Budget.py pages\4_Rent_Budget.py`
  - zero matches after cleanup
- Streamlit AppTest runtime checks completed for:
  - Buy internal zh load + search
  - Rent internal zh load + search
  - Buy internal en load
  - Rent internal en load
  - External homepage zh load
  - Buy external zh load + search + shortlist interaction
  - Rent external zh load + search + shortlist interaction
- Runtime evidence confirmed that the external Rent shortlist renders a visible `下载报告` button after shortlist interaction.

#### 4. Doc Impact
- No canonical spec update was required in this handoff because the mode architecture and core product rules did not change.
- This session implemented UX alignment and public placeholder behavior within the already-established baseline/public-layer model.

### 2026-04-21 — Mode Reset Regression Repair: Buy Map Stability + Rent Text Recovery

Context: Product mode reset follow-up | Buy map runtime stability | Rent i18n rendering | Internal/external validation

#### 1. What Changed
- Fixed the Buy map regression where `_build_map(...)` could reach `fig.add_trace(...)` after a cache miss without ever creating a Plotly figure.
- Restored clean Rent-page text rendering by recovering the corrupted translation source and Rent page labels from the last clean pre-regression version.
- Kept the product mode model unchanged:
  - internal = baseline
  - external = baseline + public restrictions
  - `IS_PUBLIC_MODE` remains the only public restriction gate

#### 2. Root Causes
- Buy crash: a dead `else` branch still owned the only `fig = go.Figure()` initialization after the mode reset. The cache-hit path returned correctly, but the cache-miss path skipped figure creation and later fell into stale map code that assumed `fig` already existed.
- Rent garbled labels: the active `utils/i18n.py` and `pages/4_Rent_Budget.py` content had been text-corrupted in the working tree, which surfaced as `???` / mojibake labels in the rendered page.

#### 3. Validation Summary
- Streamlit AppTest runtime loads completed without exceptions for Buy, Rent, and the external homepage.
- Buy and Rent search flows were exercised in both internal and external mode.
- Internal mode still shows category counts; external mode hides those counts.
- External navigation still includes the dedicated test-version homepage first; internal navigation does not.
- Canonical product docs were not changed because the target behavior was already documented; this session restored the intended behavior rather than redefining it.

### 2026-04-21 — Product Mode Strategy Reset: External Baseline Promotion

Context: Product mode architecture | Internal / External layering | Navigation | Public restrictions

#### 1. What Changed
- The refined former external workflow was promoted to the shared baseline product path.
- Internal mode now runs that refined baseline directly.
- External mode remains available, but now acts only as a stricter public/test layer on top of the same baseline.
- The legacy richer internal workflow was retired from default navigation and stopped acting as the source of truth.

#### 2. Product Consequences
- Ranking was removed from the active product navigation and left as a retired stub rather than an active legacy branch.
- External mode gained a dedicated homepage explaining test/beta/reference-only status.
- On the Buy page, report download remains visible in external mode but is blocked for public use.
- On Buy and Rent, external property-category labels no longer show numeric counts.

#### 3. Architecture Direction
- Compatibility aliases may still exist in code during migration, but active behavior must come from the refined shared baseline path.
- Public restrictions must be applied through explicit external/public gates rather than by reviving the old internal branches.
- Future product work should start from the shared baseline and then decide whether a narrower public restriction is still needed.

#### 4. Validation Summary
- Mode configuration was rebased so default app mode is internal while the refined baseline path remains active for both modes.
- Navigation was checked to ensure external shows the new homepage first and ranking no longer appears in active nav.
- Buy public report control was checked to remain visible while disabled under external/public mode.
- Buy and Rent property-type and subtype labels were checked to strip counts only in external/public mode.

### 2026-04-21 — Market Region Taxonomy Migration + Forest District Introduction

Context: Geography Layer Redesign | Market Region | Canonical Mapping | Product Taxonomy

#### 1. What Changed
- The former `REGION16 / regional16` geography layer was upgraded semantically to Market Region.
- The product is no longer constrained to a fixed “16-region” model.
- Forest District was introduced as a first-class standalone Market Region.

#### 2. Why This Change Was Made
- The old `REGION16` framing was not aligned with user-recognized market structure.
- The product is decision-focused and market-oriented rather than bound to administrative labels.
- The geography model needed to become flexible and extensible so new market-defined regions can be added cleanly.

#### 3. Data / Model Changes
- Canonical postcode mapping was updated to add:
  - `2085 -> Forest District`
  - `2086 -> Forest District`
  - `2087 -> Forest District`
- Forest District was added as a new canonical Market Region.
- The mapping model now supports `17+` regions and must not be treated as fixed-size.

#### 4. System Impact
- Market View now supports Forest District as a real selectable Market Region.
- User-facing selectors now use Market Region naming.
- Rolling datasets were rebuilt through the existing pipeline.
- Existing segmented-region logic still works on top of the upgraded Market Region layer.

#### 5. Known Constraints
- The current implementation remains postcode-based.
- Partial postcode support is not available, so ambiguous cases such as `2099` remain excluded.
- Forest District is intentionally a conservative v1 definition.
- Internal `REGION16` naming still exists as a compatibility layer and remains technical debt.

#### 6. Validation Summary
- Mapping was verified in the rebuilt compatibility dimension.
- Rolling parquet outputs were verified and include Forest District.
- Selector presence was verified in Market View and downstream ranking outputs.
- Forest District Market View rendering was verified for both `HOUSE` and `UNIT`.

#### 7. Forward Guidance
- Future geography additions must follow the Market Region model rather than reusing fixed-count `REGION16` assumptions.
- No future session should reintroduce a fixed region-count assumption for this layer.
- If boundary precision needs to improve later, a suburb-level or hybrid mapping model should be evaluated in a separate controlled change.

### 2026-04-20 — Market View Page 1 Semantics Alignment and Price-Band Geography Propagation

Context: Market View Page 1 | Main KPI semantics | Range semantics | Price-band scope | Wording accuracy

#### 1. Summary of Change
- Preserved the intended page-1 product semantics:
  - main chart = visible time window
  - range block = visible-window stable range
  - main KPI cards = latest stable summary
  - price-band chart = visible time window
  - price-band cards = latest stable summary
- Fixed the active price-band production path so it now follows the selected page geography and dwelling context instead of behaving as NSW-wide by default.
- Corrected page-1 prior-year wording so it no longer overclaims exact same-day comparison when the implemented rule uses the nearest stable prior-year match.
- Confirmed the prior `REGION / Greater Sydney / HOUSE` hard-coded anchor override remains removed from the active page-1 path.

#### 2. Why This Session Was Needed
- The page-1 KPI vs chart behavior required clarification because the intended product design is not “make everything obey preset”.
- The real production bug was in the price-band section, which had drifted to NSW-wide scope even when page 1 was filtered to a narrower geography.
- Some page-1 wording was more absolute than the implemented prior-year comparison logic and therefore overstated the metric precision.

#### 3. Final Canonical Outcome
- Main KPI cards continue to communicate the latest stable market read for the selected geography / dwelling scope and do not collapse to the visible chart endpoint.
- The range block continues to describe only the stable rolling-median range inside the currently visible time window.
- The price-band section now inherits the same geography context as page 1 for:
  - NSW
  - REGION
  - REGION16
  - AREA / suburb-like scope
  - AREA / postcode-like scope
- Price-band cards continue to use latest-stable summary semantics rather than visible-window endpoint semantics.
- Prior-year wording on page 1 now matches the implemented nearest stable prior-year match rule.

#### 4. What Was Intentionally Not Changed
- The main rolling median chart algorithm was not changed.
- Stable threshold mechanics were not changed.
- Right-edge stability logic was not changed.
- The intended latest-stable KPI philosophy was not changed.
- Chart preset behavior for visible windows was not changed.
- Existing dwelling propagation behavior was not broadened beyond what was needed for price-band geography propagation.

#### 5. Validation Evidence
- Main KPI semantics were checked with `REGION / Greater Sydney / HOUSE`:
  - `3 Month` and `1 Year` both kept the latest stable anchor at `2026-03-05`
  - stable median remained `$1,420,000`
  - stable YoY remained `-8.39%`
  - latest visible market-data point still extended to `2026-04-16`
- Range semantics were checked with the same scope:
  - `3 Month` stable range = `$1,290,000` to `$1,430,000`
  - `1 Year` stable range = `$1,290,000` to `$1,620,000`
  - this confirmed the range block changes with the visible preset while the KPI anchor does not
- Price-band geography propagation was validated for:
  - `NSW / HOUSE`
  - `NSW / UNIT`
  - `REGION / Greater Sydney / HOUSE`
  - `REGION / Greater Sydney / UNIT`
  - `REGION16 / Canterbury-Bankstown / UNIT`
  - `AREA / Coffs Harbour / HOUSE`
  - `AREA / 2450 / HOUSE`
- Price-band chart vs card semantics were checked by comparing `REGION / Greater Sydney / HOUSE` under `3 Month` and `1 Year`:
  - chart rows changed with the visible preset
  - band-card latest-stable summaries stayed fixed for the same scoped geography / dwelling context

#### 6. Remaining Caveats
- Validation in this session was code-path and dataset validation, not browser click automation.
- Unused legacy translation strings still contain older same-date wording, but page-1 active labels/captions were corrected in the active render path.
- Existing pandas warning behavior in the page-1 stable-range path was left untouched because it is unrelated to the documented semantics change.

### 2026-04-20 — Market View Greater Sydney House Stable Anchor Override Removal

Context: Market View Page 1 | Core KPI | REGION / Greater Sydney / HOUSE

#### 1. Summary of Change
- Removed the hard-coded stable-anchor override for `("REGION", "Greater Sydney", "HOUSE")` from `pages/1_Market_View.py`.
- Market View page 1 now uses the normal latest-stable-anchor resolution path for Greater Sydney House, the same as other standard geography / dwelling combinations.
- No threshold, stability, rolling median, or YoY methodology was changed. This was a narrow consistency fix only.

#### 2. Why the Previous Behavior Was Incorrect
- The core KPI card was not using the true latest stable anchor for Greater Sydney House.
- Active validation confirmed the natural stable series had already advanced to `2026-03-05` with a stable median of `$1,420,000`, but the displayed KPI was still forced to `2026-01-01` with `$1,470,000`.
- This created a canonical mismatch between:
  - the active stable series derived from current data
  - the displayed stable median price
  - the displayed stable cutoff date
- Because the override was hard-coded, the UI was showing an artificial anchor instead of the true latest stable point from the current stability logic.

#### 3. New Canonical Behavior
- For `REGION / Greater Sydney / HOUSE`, Market View page 1 must now resolve:
  - stable median price
  - stable cutoff date
  - stable YoY
  from the natural latest stable anchor returned by the general stable-anchor logic.
- No manual date forcing, roll-forward, display smoothing, or replacement override should be applied for this case.
- The canonical rule is now:
  - if a geography / dwelling combination has a valid latest stable point under the normal stability rule, the KPI must display that point directly
  - product-specific anchor overrides must not be reintroduced unless explicitly redefined in a newer dated handoff

#### 4. Validation Result
- Before removal:
  - displayed stable median = `$1,470,000`
  - displayed stable cutoff date = `2026-01-01`
- After removal:
  - displayed stable median = `$1,420,000`
  - displayed stable cutoff date = `2026-03-05`
  - stable YoY = `-8.39%`
  - latest market data date = `2026-04-16`
- Validation confirmed the KPI now aligns with the active stable series and no longer uses `2026-01-01`.

________________________________________
23. Session Handoff — Market View Stable KPI / Chart Anchor Consistency (Session)
Session Title
Market View Stable KPI / Chart Anchor Consistency Fix

Deprecated status note:
- The narrow `REGION / Greater Sydney / HOUSE` `2026-01-01` anchor override described in this handoff is no longer active.
- The active canonical rule is the later `2026-04-20` handoff plus the promoted rule in `METRICS_AND_LOGIC.md`.
________________________________________
What changed
本 session 完成了面向 Market View KPI / chart 一致性的定向修复，核心变更包括：
• Stable YoY 改为严格 stable-to-stable 计算，不再使用 fallback unstable anchor
• Stable YoY 改为基于 full dataset 计算，不再受 3M / 6M / 1Y time-range filter 影响
• Stable median KPI 不再独立走 raw rolling median anchor，而是改为复用 chart 当前可见 series 的 anchor
• 在 “仅长期” 模式下，KPI 现在直接使用 chart 所绘制的 underlying_trend anchor 值，而不是单独取 rolling_median
• 新增 latest visible stable anchor marker，用于在图上明确标出 KPI 所对应的点，减少用户肉眼误判
• 对 REGION / Greater Sydney / HOUSE 增加了一个极窄范围的产品级 override，将当前 anchor 从 2025-12-31 手动推进到 2026-01-01（已于 2026-04-20 移除，现仅为历史记录）
________________________________________
Why it changed
之所以需要这次修复，是因为此前已确认：
• Stable YoY 虽然在算术上成立，但曾经可能使用“当前不稳定点 vs 去年稳定点”的 fallback 路径
• KPI 与图表在 long-term only 模式下并未真正共用同一条 y-series，导致数值“后台一致、前台观感不一致”
• Greater Sydney House / Unit 在真实 UI 中继续出现“metric 看起来与 chart 终点不一致”的信任问题

本 session 的目标不是改 rolling median 或稳定性规则本身，而是修正 KPI 与 chart 的 source-of-truth 关系。
________________________________________
Root cause / reasoning
本次确认的真实根因不是 Plotly spline 或 line interpolation。

真实问题有两层：
• Stable YoY 旧逻辑允许 display layer 使用 post-stable fallback anchor，因此展示为 “Stable YoY” 的值并不总是 stable-to-stable
• Chart 在 “仅长期” 模式下展示的是 transformed series（underlying_trend），而 KPI 曾经读取的是另一条 raw series，因此即使 anchor date 相同，用户看到的图表终点和 KPI 数字也会不同

因此，本次修复采取的原则是：
• YoY 单独走 full-history stable anchor 解析
• Stable median KPI 必须读取当前 chart 实际可见 series 在 chosen anchor date 上的 plotted y-value
• 若产品需要人为推进某个 anchor date，必须做成窄范围 override，而不是修改全局稳定性逻辑
________________________________________
Resulting behavior now
修复后，当前期望行为为：
• Stable YoY = latest stable point across full history ÷ closest prior-year stable point - 1
• 如果无法找到有效 stable comparison，则 Stable YoY 应显示为 N/A，而不是 fallback
• Stable median KPI 与 chart 现在共用同一个 visible anchor source
• 在 “仅长期” 模式下，KPI 显示值应与图上 latest visible stable point 完全一致，而不是近似一致
• 3M / 6M / 1Y 切换不应再改变 Stable KPI 或 Stable YoY
• REGION / Greater Sydney / HOUSE 在 long-term only 模式下，曾短暂使用 2026-01-01 override；该规则现已废止，当前以自然 latest stable anchor 为准
• REGION / Greater Sydney / UNIT 在 long-term only 模式下，KPI 与 chart anchor 现已对齐
________________________________________
Validation / evidence
本 session 已完成的关键验证包括：
• REGION / Greater Sydney / HOUSE / Long-term only：
  anchor date = 2026-01-01
  KPI = 1441230.7747252746
  chart anchor = 1441230.7747252746
  3M / 6M / 1Y 下保持不变
• REGION / Greater Sydney / UNIT / Long-term only：
  anchor date = 2026-03-08
  KPI = 826008.0263157894
  chart anchor = 826008.0263157894
  3M / 6M / 1Y 下保持不变
• 回归 spot check 已覆盖：
  REGION / Rest of NSW
  REGION16 / Lower North Shore — Core
  REGION16 / Upper North Shore — Core
• `py_compile` 已通过
• 当前部署分支已提交并推送：
  branch = deploy/streamlit-cloud-safe-2026-03-29
  commit = 31ea52ed57c4b6ae71c536253486188ad9383815
  message = Fix Market View stable KPI and chart anchor consistency
________________________________________
Operational notes
后续若再次出现 KPI / chart 不一致，优先按以下顺序排查：
• 当前 display mode 是否为 “仅长期”，因为此时 chart 使用的是 underlying_trend 而不是 raw rolling_median
• KPI 是否读取了 visible chart series 的 anchor y-value，而不是独立重算的 raw median
• 某些产品级 anchor override 是否仅限目标 region / dwelling / level，没有意外扩散到其他区域
• 浏览器端是否因 marker 不明显或缓存导致用户仍旧误判终点

本 session 未修改：
• rolling median 生成逻辑
• global stable threshold policy
• mart / parquet pipeline
• 非目标区域的基础稳定性规则
________________________________________
Open issues / next steps
当前仍建议下一 session 继续关注：
• 在真实 Streamlit Cloud 页面做浏览器级确认，确保 latest anchor marker 在实际 UI 中足够明确
• 继续监控 pandas fillna warning 与 Streamlit use_container_width warning，这些不是本 session 的根因，但仍会影响维护质量
• 若未来业务希望 Dual-line mode 下 KPI 也显式声明其基于哪条 series，需要单独做产品定义，不应在本 session 基础上继续隐式扩展
• Greater Sydney House 的 2026-01-01 override 已被移除；后续若再出现类似需求，必须先更新 canonical docs，再写 handoff
________________________________________
24. Session Handoff — External Filter Stabilization (Session)
### Handoff Authority Rule

The latest **dated** Session Handoff entry is the authoritative source of truth for the current system behavior and implementation standard.

Older dated Session Handoff entries are historical context only and must NOT override, reintroduce, or be treated as more current than the latest dated handoff.

If any older handoff content conflicts with the latest dated handoff, the latest dated handoff wins.

When starting a new implementation session:

* first identify the latest dated Session Handoff entry
* use it as the active source of truth for:

  * layout
  * state model
  * coverage logic
  * interaction behavior
* treat earlier handoffs as historical reference only

### 2026-04-19 — Map Suburb Focus + Browser Sync Fix (Sale & Rent)

Context: Buy Budget + Rent Budget | Map Interaction | Listing Browser Sync

#### 1. Summary of Changes
- Fixed the listing-browser sync issue on both Sale and Rent pages so that clicking a suburb on the map now switches the right-side listing browser to the matching listings for that focused suburb.
- Clarified and enforced the interaction rule that map click must preserve the global filtered suburb universe and only add a local focused-suburb highlight, rather than visually collapsing the map to a single-suburb result set.
- Standardized Sale and Rent so they now share the same map-click interaction semantics: map highlight/local focus on the clicked suburb, browser rows filtered to the clicked suburb, and browser title/count switched to focused-suburb semantics.
- Browser heading and list meaning are now explicitly focused-suburb aware instead of remaining ambiguous global-browser output after a suburb click.

#### 2. Root Cause
- The responsibility of `selected_suburb` / focused suburb had drifted, so local map focus and global filtered-universe semantics were too easy to mix together.
- Browser rows were being resolved before `_build_map(...)` returned the updated focused suburb. This created a timing bug: the map click updated suburb focus, but the right-side browser in that same render still used rows computed from the old state.
- The map’s focused-suburb visual layer was incomplete, especially on the Rent path, so users could read the interaction as “the map only has one suburb left” even when the underlying filtered suburb universe still existed.
- Sale and Rent were no longer fully aligned in focused-suburb highlight behavior and browser-title semantics, which created inconsistent user expectations across the two pages.

#### 3. Final Canonical Logic

##### A. Global Filtered Universe
- Top-level filters define the global filtered universe.
- The global filtered universe controls:
  - which suburbs are present in the map result set
  - suburb ranking
  - top-level/global metrics
  - the default listing-browser result set

##### B. Focused Suburb
- Map click creates a focused suburb.
- Focused suburb is only allowed to control:
  - map highlight / local focus
  - listing-browser local filtering
  - browser heading and browser count semantics
- Focused suburb must not rewrite:
  - the global filtered universe
  - suburb ranking
  - top/global metrics

##### C. Map Behavior
- After a suburb is clicked, the map must continue to retain all suburbs from the current filtered universe.
- The clicked suburb may be highlighted, outlined, recolored, or recentered, but it must remain a local visual focus within the existing filtered-universe map.
- Focused suburb must not be used to shrink the map layer, suburb summary, choropleth input, or map polygon dataset to a single suburb.

##### D. Browser Behavior
- In the default state, the browser shows the global filtered listings.
- After a map suburb click, the browser must recompute its rows in the same render cycle using the latest focused suburb returned from `_build_map(...)`.
- Browser heading, browser count, and browser listing content must all switch to focused-suburb semantics.
- Clicking a different suburb later must repeat the same process and switch the browser again to the new focused suburb.

#### 4. Sale vs Rent Consistency
- Sale and Rent must continue to use the same map-click interaction semantics.
- It is not acceptable for one page to highlight the clicked suburb without switching the browser while the other page switches the browser correctly.
- It is not acceptable for one page to preserve the full filtered suburb map while the other page visually behaves as if only one suburb remains.
- Focused-suburb highlight and browser sync must be maintained together on both pages whenever related interaction logic is changed.

#### 5. Validation Evidence
- `py_compile` passed for:
  - `pages/3_Buy_Budget.py`
  - `pages/4_Rent_Budget.py`
- Streamlit AppTest runtime loading completed without exceptions for Sale and Rent.
- Seeded focused-suburb cases were validated for both Sale and Rent.
- Multi-suburb focused cases were validated; browser text changed with the selected suburb across more than one suburb on both pages.
- English and Chinese paths were exercised through AppTest/state-seeded validation and were not broken by this fix.
- Validation performed for this session was based on syntax checks, code-path inspection, and AppTest seeded-state runs.

#### 6. Known Limitations
- This was a minimal interaction fix and did not refactor the full page-state architecture.
- Validation in this session relied on `py_compile`, code-path inspection, and Streamlit AppTest seeded-state checks, not real browser click automation.
- If focused-suburb emphasis later still feels too weak visually, light UI polish is acceptable, but the canonical interaction logic above must not be changed again.

#### 7. Operational Guidance
- Do not treat `selected_suburb` / focused suburb as the global filter source of truth.
- Do not let map click rewrite the global filtered universe.
- Do not finalize browser rows before `_build_map(...)` returns the latest focused suburb.
- Browser rows must be recomputed from the newest focused suburb after map interaction resolves.
- Map visual highlight and browser sync must always be maintained together; fixing one without the other is not acceptable.
- Sale and Rent interaction fixes in this area should be implemented and reviewed as a pair to prevent future behavior drift.

### 2026-04-18 — External Map + Panel Alignment & Unified State Model

#### 1. Summary
- External Buy/Rent map + panel layout finalized.
- Bottom-edge alignment fixed as a visual-baseline problem, not just an equal-height problem.
- Unified interaction model across filters, map, ranked suburbs, and listing browser/detail panel.
- Coverage logic finalized with filtered-result outputs separated from full-universe coverage-map behavior.

#### 2. Root Causes
- Map and panel were misaligned because their visible bordered rectangles sat on different vertical baselines, not only because of a height mismatch.
- Helper text sitting outside the map shell pushed the map card lower than the right panel.
- Panel height was being driven by inner content flow instead of the outer visible shell.
- Coverage logic had previously used a filtered-only denominator, which forced coverage toward 100%.
- Interaction state was not fully unified across map suburb focus, ranked suburb focus, and listing selection.

#### 3. Key Changes Implemented

### A. Layout
- Introduced a shared external shell height constant: `EXTERNAL_MAP_PANEL_HEIGHT`.
- Map and panel now both use bordered fixed-height containers in the external path.
- Helper text was moved inside the map shell so the visible map card and visible panel card share the same vertical baseline.
- Internal scrolling remains confined to the right panel rather than stretching the page.
- Map canvas was expanded by reducing unnecessary internal whitespace and trimming non-map chrome.
- Map colorbar was tightened to reduce visual waste inside the map area.

### B. State Model (CRITICAL)
- Filters define the full filtered result universe.
- Map click and ranked suburb click both set the focused suburb.
- Focused suburb then updates:
  - metrics
  - listing browser
  - detail panel
- Ranked suburbs remain the full positive-match filtered set and do not collapse to only the focused suburb.
- Selected listing is subordinate to the focused suburb and is cleared when it becomes invalid under a suburb-focus change.

### C. Coverage Logic
- `coverage = matched / total`
- Denominator = full suburb listings within the selected property-type universe.
- Numerator = filtered listings within the same suburb and property-type scope.
- Map shows:
  - `0%` → grey
  - partial match → grey-to-green gradient
  - `100%` → full green
- Ranked suburbs use the same coverage logic but exclude zero-match suburbs.

#### 4. Final Behavior
- Default (no suburb focus):
  - metrics = full filtered result
  - map = full suburb coverage context + filtered listing markers
- Focused suburb:
  - metrics + listing browser = suburb-level filtered result
  - map zooms/focuses to that suburb
- Listing selected:
  - detail panel updates to that listing
  - focused suburb remains consistent with the selected listing
- Pagination does not rerender the map when only the right-panel page changes.

#### 5. Validation
- Buy and Rent were both updated under the same external model.
- Chinese and English paths were both covered.
- `py_compile` passed for the touched pages.
- Streamlit AppTest was used partially for runtime validation.
- Final validation still requires browser-level visual confirmation for:
  - bottom-edge alignment
  - list mode vs detail mode alignment
  - responsive behavior

#### 6. Operational Notes
- External layout is now stable; avoid introducing new parallel layout paths.
- Do not reintroduce multiple map containers or duplicate external map shells.
- Maintain a single source of truth for:
  - filtered scope
  - focused suburb
  - selected listing
- Future UI work should not break visual alignment or the unified external state model.

### 2026-04-17 — External Browse → Address Click Map Selection Flow

#### Summary
- Unified the external listing-to-map trigger around the listing browse address cell on both Buy Budget and Rent Budget pages.
- Removed the visible broken locate-label path that previously rendered mojibake in the Buy browse action column.
- Preserved the existing external two-level map model: suburb polygon overview, focused suburb listing markers, and single-map path rendering.

#### Root Cause
- The previous dedicated locate control on Buy used corrupted localized string literals, which caused mojibake in the rendered button label.
- The external browse area did not provide a sufficiently obvious primary interaction entry point for listing-to-map selection.
- The listing-selection state and map response already existed, but the browse interaction entry point was not aligned with the intended decision loop.

#### Changes Implemented
- Converted the listing address in the external browse table into the primary map-selection trigger for both Buy and Rent.
- Kept `selected_listing_id` as the canonical listing-selection state and continued to update it without changing the focused suburb.
- Preserved the existing focused-suburb map response: selected listing recenter, selected marker highlight, and no secondary map instance.
- Added concise listing-area guidance text so the interaction is explicit in normal external usage.
- Kept suburb reset behavior unchanged so resetting focused suburb also clears `selected_listing_id`.

#### Final Behavior
- In external mode, the user focuses a suburb first, then clicks a listing address in the browse area to locate that listing on the map.
- Clicking a listing address updates `selected_listing_id`, keeps the current focused suburb unchanged, recenters the existing map to the selected listing, and highlights that listing marker.
- When the focused suburb is cleared, `selected_listing_id` is cleared as part of the same reset path.
- The external Buy and Rent pages now follow the same listing-to-map interaction pattern.

#### Validation
- Confirmed `MASTER_SPEC.md` remained UTF-8 decodable before modification.
- Verified Buy and Rent page syntax with `py_compile`.
- Verified Streamlit AppTest search render completed with zero runtime exceptions on both pages after the interaction change.
- Verified focused suburb and listing selection state transitions through AppTest.
- Buy Budget: focused suburb resolved to `Austral`, then address-trigger selection set `budget_selected_listing_id = 2020697736`.
- Rent Budget: focused suburb resolved to `Sydney`, then address-trigger selection set `rent_selected_listing_id = 16491125`.

#### Operational Notes
- Future external listing-to-map work should keep the address cell as the primary browse-to-map trigger unless a broader product-level interaction redesign is approved.
- External mode must continue to use the single-map path; no secondary map container or duplicate map render path should be introduced for listing selection.
- Future changes must preserve the canonical state pair `selected_suburb` and `selected_listing_id`, with suburb reset continuing to clear listing selection.

Session Objective
本 session 目标：
• 完成 External demo 面向用户的稳定性与一致性修复
• 修复 Buy / Rent 外部筛选、状态同步、语言切换、Reset、Summary 与 Map 范围问题
• 完成 Market View 数据刷新流程优化、稳定日期展示优化、Dwelling Type 切换修复
• 校验 Streamlit Cloud 部署分支与本地数据是否一致
________________________________________
Changes Implemented
本 session 已完成：
• 重新确认 MASTER_SPEC 架构约束与当前阶段规则
• 修复 External Buy / Rent applied filter persistence、summary completeness、property type first-search sync
• 修复 External commute filter accuracy，并改为更保守可信的外部过滤行为
• 优化 External Buy / Rent map path 与外部页面性能
• 增加 External language switching、Reset filters、beta 文案、commute beta 限制说明
• 增加 External initial empty-state，防止初始加载暴露全部 suburb / listing
• 修复 Market View Chinese / English 一致性、排序与展示文案
• 优化 Market View stable KPI 展示，增加 market data loaded to 提示
• 增加 region-level display fallback，使长期不变的 stable date 在展示层可向前推进
• 修复 External Market View dwelling type 主控件卡死问题，支持 House / Unit 双向切换
• 构建 scripts/update_market_view_from_zip.py，实现手动下载 zip 后的半自动 DAT 更新流程
• 移除 update_market_view_from_zip.py 中未被外部产品页面使用的 monthly mart build step
• 将最新 Market View 数据文件提交并推送到部署分支：
  Refresh Market View data through 2026-04-08
________________________________________
Architecture Decisions
本 session 明确并保持以下架构决策：
• 所有当前阶段修复默认仅适用于 External mode
• Internal mode 保持研究 / 调试 / 分析能力，不做行为回退
• Buy Budget 与 Rent Budget 继续使用独立 listing dataset
• 所有 external persisted state 必须使用稳定 canonical key，不得使用翻译后的 display label
• Market View stable / raw_stable 逻辑本身不修改，新增 fallback 仅作用于 KPI display layer
• External visible control 必须成为真正 source of truth，不能被隐藏 legacy state 覆盖
________________________________________
Files Modified
本 session 涉及的核心文件：
• docs/MASTER_SPEC.md
• pages/1_Market_View.py
• pages/3_Buy_Budget.py
• pages/4_Rent_Budget.py
• utils/data.py
• utils/i18n.py
• utils/map_view.py
• utils/ui.py
• scripts/update_market_view_from_zip.py
• Processed/fact_sales/fact_sales_2026.parquet
• Processed/mart_daily_rolling/daily_rolling_nsw.parquet
• Processed/mart_daily_rolling/daily_rolling_region.parquet
• Processed/mart_daily_rolling/daily_rolling_region16.parquet
• Processed/mart_daily_rolling/daily_rolling_suburb.parquet
• Processed/mart_daily_rolling/daily_rolling_postcode.parquet
• RawData/manifest/dat_manifest.csv
________________________________________
Validation Performed
本 session 已执行：
• py_compile 语法校验
• Streamlit AppTest 页面渲染校验
• Buy / Rent Chinese / English external filter scenario validation
• Property type first-submit validation
• Commute filter correctness validation
• Reset filter state transition validation
• Market View language consistency validation
• Market View region-level stable date / fallback validation
• Market View dwelling type House / Unit interaction validation
• 本地数据与 Git HEAD 数据日期差异比对
• Git branch / commit / modified artifact / push 状态校验
________________________________________
Known Issues
当前仍需注意：
• Streamlit testing 对部分 translated widgets 仍有局限，个别真实点击路径需浏览器级验证
• pandas fillna future warning 仍存在
• Streamlit use_container_width deprecation warning 仍存在
• Market View live Streamlit Cloud runtime 是否已经完成自动 redeploy，本 session 无法直接从 Cloud dashboard 最终确认
• 外部产品当前显示逻辑已包含 stable-date display fallback，因此 live app KPI 日期不应再按旧稳定点直接显示
________________________________________
Next Session Priorities
建议下一 session 优先处理：
• 在真实 Streamlit Cloud 环境确认最新 commit 已完成部署
• 若 Cloud 仍显示旧数据，执行 Reboot app / Clear cache 并复核 Greater Sydney
• 浏览器级验证 External Market View / Buy / Rent 真实交互路径
• 继续清理 Market View 与 Buy / Rent 的残余 warning / cold-start bottleneck
• 如业务需要，再讨论是否调整 stable threshold policy，而不是仅 display fallback
________________________________________
Stability Status
当前判断：
• External Buy / Rent: significantly improved, but仍建议继续做浏览器级 regression validation
• External Market View: major UX / language / KPI / dwelling switch issues 已修复
• Market View data update pipeline: simplified and operational
• Deployment branch data: 已同步至 2026-04-08 数据批次
________________________________________
External vs Internal Impact
影响范围：
• External mode：本 session 为主要修复目标，已进行多项 UX / state / data / deployment 改进
• Internal mode：原则上保持不变，仅保留必要 shared helper 兼容
• 未移除 Internal debug / analytics / research capabilities
________________________________________
Session Conclusion
Session Status: Closed
Handoff Status: Completed
Ready for Next Session

## Legacy Pre-Split Status Blocks Preserved From Prior MASTER_SPEC

These undated status/stabilization blocks appeared before the later dated handoff stream in the previous `MASTER_SPEC.md`. They are preserved here so no operational context is lost, but the current canonical rules now live in the topic-based docs.

### Legacy Section 20 — Current Status
- External ready
- Internal preserved
- Demo ready

### Legacy Section 21 — External Buy/Rent Filter Stabilization Session (Revised)
Summary of work recorded in the old spec:
- external Buy Budget filter stabilization
- external Rent Budget filter stabilization
- shared stabilization work across applied-state persistence, widget rehydration, commute filter behavior, property-group consistency, applied-summary expansion, and Chinese/English rendering fixes

Validation scope recorded in the old spec:
- Buy Budget external — Chinese
- Buy Budget external — English
- Rent Budget external — Chinese
- Rent Budget external — English

Architecture clarification recorded in the old spec:
- Buy Budget and Rent Budget use independent listing data sources
- each page must maintain its own canonical filtered dataset
- each page must maintain its own applied-filter pipeline
- no unified `filtered_external_df` should be assumed

Remaining-risk notes recorded in the old spec:
- selected filters were not always fully reflected in applied summary
- listing browser could still show rows outside selected budget/rent range in unresolved scenarios
- downstream outputs might not fully match selected filters in unresolved scenarios
- full external filter stabilization was not yet complete at that point in history

### Legacy Section 22 — External Listing Filters Stabilization In Progress
Status recorded in the old spec:
- selector UI stabilized
- session-state persistence architecture implemented
- `st.form` search architecture implemented
- applied-filter model implemented
- widget rehydration implemented

Still-in-progress items recorded in the old spec:
- full listing dataset filter consistency
- applied-filter summary completeness
- budget/rent filter enforcement under all real combinations
- downstream consistency across metrics, map, listing browser, and shortlist scope
- Buy/Rent parity validation
- Chinese/English parity validation under real filter-use cases

Phase/priority recorded in the old spec:
- phase: External Filter Consistency Fix Phase
- priority: HIGH
- rationale: filter inconsistency affects user trust and must be resolved before adding new features

### Legacy Section 22.1 — External Development Rules
Rules recorded in the old spec:
- current-stage modifications should be external-only unless internal compatibility work is genuinely necessary
- internal mode should retain debug, analysis, and research capability
- all external changes must maintain Chinese/English consistency
- all external filter/listing changes must maintain Buy/Rent parity
- every external change required validation in Buy Chinese, Buy English, Rent Chinese, and Rent English
- required validation had to include filter effect, summary correctness, listing match, and metric match

