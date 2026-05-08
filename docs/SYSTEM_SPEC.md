# System Spec

## Purpose and Scope
NSW Property Analytics is a data-driven property decision platform for NSW sale and rent use cases. It is not a general listing portal. The product is intended to support:
- purchase decision support
- rental decision support
- market trend analysis
- property analytics SaaS workflows

Current stage:
- Public Streamlit full-internal alignment

## Version Strategy
### Internal Version
Purpose:
- baseline product behavior
- internal review and validation
- day-to-day product use against the active refined workflows

Allowed capabilities:
- current refined Market View / Buy Budget / Rent Budget workflows
- full working shortlist report download where implemented
- category labels may include counts where the baseline workflow still exposes them

### Public Streamlit Version
Purpose:
- public product entry through Streamlit Cloud
- outward-facing access to the same functional product behavior as internal mode

Allowed capabilities:
- keep the existing product introduction homepage as page 0
- Market View, Buy Budget, and Rent Budget follow full internal behavior
- shortlist, map, listing, link, report, table, and filter behavior should not be downgraded only because the app is running publicly

Public Streamlit rules:
- the product introduction homepage is the first navigation page
- functional pages are the current internal/full versions
- external/public downgrade gates must not hide or disable functionality on functional pages
- Streamlit Cloud should reflect the latest internal processed/current datasets included in deployment

Public deployment safety gates:
- public deployment keeps full internal analytical behavior
- specific upstream listing platform names must not appear in user-facing UI, tooltips, captions, warnings, tables, or report text
- user-facing listing provenance should use neutral wording such as `market listing data`, `listing data`, `market data`, or `publicly available market records`
- report download remains internal-only until the report feature is production-ready
- safety gates are controlled separately from functional mode so public deployment can keep full analysis while still hiding unfinished report/export entry points

## Public vs Internal Data Architecture
### Public Streamlit And Internal Mode
Public Streamlit and internal mode MUST:
- use the full `Processed/` datasets
- reflect the latest local data updates
- use the same Market View daily rolling marts and fact-sales paths

### Cache Rule
`data/cache/` is non-canonical:
- it must never be used as a runtime dependency
- it may exist only as a disposable acceleration layer for local/internal workflows

## Page Structure
Current pages:
1. Product introduction homepage
2. Market View
3. Buy Budget
4. Rent Budget

Retired page path:
- Ranking is no longer part of the active product baseline and the legacy internal ranking workflow is deprecated

## Page-Level Behavior
### Market View
Core behaviors:
- market trend visualization
- rolling median display
- price-band view
- stability analysis

### Buy Budget
Core behaviors:
- budget filtering
- map interaction
- shortlist management
- listing browser
- property decision support

### Rent Budget
- same overall interaction model as Buy Budget, with rent-specific listing data and filters

## Listing Rules
### Sale Listing Filters
External sale listing behavior:
- filter out price < 50,000
- filter out price > 10,000,000
- retain null price rows where product logic permits
- sort numeric price rows ahead of non-numeric rows

### Rent Listing Filters
External rent listing behavior:
- filter out rent < 80/week
- filter out rent > 5000/week
- retain null rent rows where product logic permits
- sort numeric rent rows ahead of non-numeric rows

## Listing UI Baseline
Presentation rules:
- visual refactors may change hierarchy, spacing, wrappers, and shared styling helpers
- visual refactors must remain UI-only and must not change metric formulas, filtering semantics, state ownership, map interaction rules, shortlist identity/state rules, report calculations, or public restriction behavior

### Sale Columns
- Price
- Address
- Suburb
- Type
- Beds
- Baths
- Parking
- Land
- Agency

### Rent Columns
- Weekly Rent
- Address
- Suburb
- Type
- Beds
- Baths
- Parking
- Agency

## Shortlist and Export Rules
Shortlist system requirements:
- toggle shortlist membership
- session persistence
- stable listing identity

Export/report constraints:
- internal/full mode remains the baseline working path for report download where the page already supports it
- public Streamlit functional pages use the same report/export behavior as internal/full mode
- public deployment must hide or disable report download entry points until reports are production-ready
- report/export outputs must remain consistent with the active canonical dataset for the page producing them
- no hidden mismatch is allowed between listing browser, shortlist, metrics, map state, and report content

### Sale Report Product Rules
Canonical sale-report principle:
- the sale report must be structured around one core user question: `What is the positioning of this listing?`
- sections must support a single decision narrative rather than read like independent stitched-together exports

Required page order for the current sale report:
- Page 1:
  - Hero Summary
  - Key Metrics
  - Current Sale Market Positioning
  - Transaction Market Snapshot
- Page 2:
  - Price Band Analysis
  - Price Distribution Chart
- Page 3:
  - Budget Sensitivity
  - Rent & Yield Snapshot
  - Final Summary

Required narrative/visual behavior:
- Hero Summary must appear at the top of page 1
- Hero Summary must include address, property type, price, and a short narrative combining asking-market positioning, transaction-market condition, and supply/comparable context
- each section must include a short explanatory sentence rather than only raw metrics
- metric-card style grouped blocks are preferred over raw table-first presentation
- raw local dataset paths, parquet paths, or debug-style source paths must not appear in the visible PDF

Final summary behavior:
- the closing summary must include structured insight on:
  - pricing vs market
  - transaction trend
  - supply / comparables
  - investment signal
- the report must remain factual and must not provide buy/sell recommendations

## Budget/Search Form Rules
- use `st.form`
- require explicit search/apply behavior
- no live-sync filter mutation
- no callback-driven hidden filter application

## Slider Rules
### Sale
- 0 to 10M

### Rent
- 75 to 5000

## Current Operating Phase
Current phase:
- External product stabilization
- External filter consistency remains a high-priority trust issue

Current priorities:
1. External UX
2. Listing UI
3. Bug fixing

Current risks:
1. geojson size
2. map performance
3. state management complexity
4. external responsiveness/speed

## Canonical Interaction and State Rules
### Global Filtered Universe
Top-level filters define the global filtered universe.

The global filtered universe controls:
- which suburbs are present in the map result set
- suburb ranking membership
- top-level/global metrics
- the default listing-browser result set
- downstream page outputs that depend on the filtered page dataset

### Focused Suburb
Focused suburb is a local interaction/view state created by a map click or ranked-suburb click.

Focused suburb is allowed to control:
- map highlight and local focus
- listing-browser local filtering
- browser heading and browser count semantics
- focused local metrics/detail context where the page explicitly supports that pattern

Focused suburb must not rewrite:
- the global filtered universe
- suburb ranking inputs
- top/global metrics
- the canonical filtered dataset for the page

### Map and Browser Synchronization
Canonical sync rule:
- in the default state, the browser shows the global filtered listings
- after a suburb is clicked, the map must retain the full currently filtered suburb universe and only add local suburb focus/highlight
- browser rows must be recomputed in the same render cycle using the latest focused suburb returned from the map interaction path
- browser heading, browser count, and browser rows must switch together to focused-suburb semantics
- clicking a different suburb must update the browser to the new focused suburb in the same way

### Listing Selection
- `selected_suburb` is not the global source of truth
- `selected_listing_id` is subordinate to the focused suburb
- listing selection should recenter/highlight within the existing single-map path rather than create a second map path
- clearing suburb focus should clear listing selection

### Coverage Logic
Canonical external coverage rule:
- `coverage = matched / total`
- denominator = full suburb listing universe within the selected property-type scope
- numerator = filtered listings within the same suburb and property-type scope
- map coverage visualization may show `0%`, partial coverage, and `100%` distinctly
- ranked-suburb outputs may exclude zero-match suburbs while still using the same numerator/denominator logic

## Buy / Rent Separation Rules
Buy Budget and Rent Budget use separate listing datasets.

Therefore:
- Buy and Rent filters must be applied independently
- each page must maintain its own canonical filtered dataset
- each page must maintain its own applied-filter pipeline
- no shared cross-page filtered dataframe should be assumed
- sale-side and rent-side downstream outputs must stay internally consistent with their own page dataset

## Public Streamlit Development Rules
During the current release phase:
- functional-page modifications should preserve internal/full behavior across local and Streamlit Cloud runtime
- public deployment must not silently introduce a downgraded Market View, Buy Budget, or Rent Budget path
- the product introduction homepage may remain public-specific

## Chinese / English Consistency Rules
All public functional page changes must apply to both:
- Chinese
- English

The following must stay consistent across languages:
- UI text meaning
- filter behavior
- applied summary behavior
- listing output behavior
- metric calculation behavior
- map behavior

## Buy / Rent Parity Rules
All external filter/listing interaction changes must be applied consistently to:
- Buy Budget
- Rent Budget

Required parity areas:
- filter behavior
- applied-state persistence
- summary rendering
- listing filtering
- map/browser synchronization semantics

## Market View Canonical Behavior
Current canonical Market View behavior includes:
- 28-day rolling median presentation
- stability-aware KPI presentation
- price-band context alongside the main trend view
- the legacy internal `REGION16` layer is now a user-facing Market Region layer rather than a fixed 16-region canonical product concept
- Forest District is a first-class selectable Market Region
- main chart follows the selected visible time-range preset
- main KPI cards remain latest-stable summaries for the selected geography and dwelling context rather than visible-window endpoint summaries
- the median/range block represents the stable rolling-median range within the selected visible time range only
- price-band chart follows the selected visible time-range preset
- price-band summary cards remain latest-stable summaries for each band rather than visible-window endpoint summaries
- price-band chart and price-band summary cards must follow the same selected geography and dwelling context as page 1 rather than defaulting to NSW-wide scope
- prior-year comparison wording must not claim exact same-day comparison unless the implementation literally uses the same calendar date; Market View page 1 currently uses the nearest stable prior-year match rule
- long-term mode must remain visually and semantically aligned with the same charted trend series shown to the user
- for `REGION / Greater Sydney / HOUSE`, page 1 must use the natural latest stable anchor and must not apply the removed `2026-01-01` override

## Market Region (Canonical Geography Layer)
Canonical product rule:
- the former `REGION16 / regional16` concept is superseded by Market Region
- Market Region replaces REGION16 as the product-facing geography layer
- Market Region is a user-recognition market geography layer and is not defined by administrative boundaries alone
- Market Region must not be presented as a fixed “16-region” product rule in UI or canonical docs
- it is not a fixed-size set and may expand as product-defined market structure evolves
- it is currently postcode-based in the active system architecture but may evolve later
- backward-compatible internal use of the `REGION16` token and legacy output filenames is allowed where required for migration safety
- Forest District is an official standalone Market Region and must not be folded into Northern Beaches
- Forest District is an example of a product-defined region
- the current conservative Forest District v1 definition is postcode-based and includes:
  - `2085`
  - `2086`
  - `2087`
- `2084` and `2099` are intentionally excluded from the current Forest District definition pending a separate controlled boundary review
- The system MUST NOT assume a fixed number of regions in this layer.

For metric formulas, anchor logic, and exact calculation rules, see [METRICS_AND_LOGIC.md](./METRICS_AND_LOGIC.md).

## External Browse-To-Map Behavior
In external Buy and Rent workflows:
- the listing address cell is the primary listing-to-map trigger in the browser
- clicking the address updates listing selection without silently redefining the focused suburb
- the existing single-map path must be reused for recentering/highlighting the selected listing
- clearing the focused suburb must clear the selected listing as part of the same reset path
