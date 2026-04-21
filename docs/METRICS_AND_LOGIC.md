# Metrics and Logic

This document defines how metrics are calculated.

References:
- Product meaning and usage: [SYSTEM_SPEC.md](./SYSTEM_SPEC.md)
- Source datasets and rebuild assumptions: [DATA_PIPELINE.md](./DATA_PIPELINE.md)

## Market View Core Metrics
### Rolling Median
- primary displayed market-price metric is a 28-day rolling median
- Market View uses a daily rolling window representation over transaction data

### Stable Threshold
- `stable threshold = 0.55`
- applies to:
  - Market View
  - price-band logic
  - KPI stability resolution

### Stable vs Unstable Handling
- stable/unstable behavior is driven by transaction-volume sufficiency under the page’s stability rule
- stable logic should not be changed casually at the display layer
- unstable tails may still be shown visually, but stable KPIs must resolve from stable anchors only unless a newer canonical rule explicitly changes that behavior

### Stable Anchor Logic
Current canonical rules:
- stable KPI anchors resolve from the latest valid stable point across full history for the selected scope
- visible time-range presets should not redefine the full-history stable anchor unless a future product rule explicitly changes that contract
- stable median KPI and chart anchor must use the same chosen anchor source for the active display mode
- in Long-term only mode, the KPI anchor value comes from the plotted `underlying_trend` series rather than a separate raw rolling-median readout
- for `REGION / Greater Sydney / HOUSE`, the removed `2026-01-01` override is no longer canonical; the general stable-anchor logic now applies directly

### Stable YoY Logic
- stable YoY is stable-to-stable only
- stable YoY compares the latest stable point against the closest prior-year stable point according to the active stable-anchor resolution logic
- if no valid stable prior comparison exists, Stable YoY should render `N/A`
- stable YoY is resolved from full history rather than the visible 3M / 6M / 1Y chart window

### Stable Range / Median Range Semantics
- stable range blocks are ranges over the relevant stable rolling-median subset
- stable range blocks do not redefine the latest stable anchor
- on Market View page 1, the median/range block is computed from stable rows inside the selected visible time window only
- the Market View page-1 range block is `min stable rolling median` to `max stable rolling median` within that visible window

## Long-Term Trend Logic
- long-term display uses `underlying_trend`
- long-term trend display is conditional on sufficient median sales depth for the selected geography/group
- lower geographies may use lower eligibility thresholds than broader geographies
- Market Region house regions may use a narrower segmented threshold where that rule is still active in code

## Price Band Logic
### Band Definitions
- `<750k`
- `750k-1.2M`
- `1.2M-2M`
- `2M-3M`
- `>3M`

### Band Construction
- price-band logic is derived from filtered sales fact data
- each band uses rolling median plus rolling sales volume logic consistent with its Market View section
- stability rules are applied to price bands using the same core stability-threshold concept
- on Market View page 1, price-band construction must use the same selected geography context as the page:
  - NSW page selection -> NSW-wide price-band scope
  - REGION page selection -> selected REGION scope
  - Market Region page selection -> selected Market Region scope
  - AREA page selection -> the same active suburb-like or postcode-like production scope selected on page 1
- price-band construction must also use the same selected dwelling group as page 1

## Market Region Mapping Logic
- legacy internal token = `REGION16`
- canonical product-facing name = Market Region
- current Market Region assignment is postcode-based in the active architecture
- the canonical Market Region mapping is allowed to contain more or fewer than 16 regions; fixed-count assumptions are not valid product logic
- the generated compatibility dimension may expand mapped postcodes to all known suburb/postcode pairs for downstream attribution, while aggregation still resolves Market Region scope from postcode membership
- Forest District is a canonical Market Region with conservative v1 postcode coverage:
  - `2085`
  - `2086`
  - `2087`
- `2084` and `2099` remain excluded from the current Forest District definition

## Market Region Metric Continuity
- Market View metrics operate on Market Region using the same metric logic previously applied to the legacy `REGION16` layer
- Forest District does not use special-case KPI, stability, YoY, price-band, or chart logic
- the taxonomy migration changes geography semantics and mapping scope, not metric methodology

### Band Summary Semantics
- price-band cards and charts should remain internally consistent on anchor logic
- any divergence between band chart time scope and band KPI anchor scope should be treated as an audit item, not an invisible assumption
- on Market View page 1:
  - the price-band chart uses the selected visible time-range preset
  - the price-band summary cards use the latest valid stable anchor for each band across full scoped history
  - both chart and cards must share the same geography and dwelling scope
- price-band YoY wording should describe the nearest stable prior-year match logic when that is the implemented comparison path, rather than claiming exact same-date comparison

## Sale / Rent Listing Metrics
### Sale Listing Context
Canonical sale-side concepts include:
- suburb current listing median
- listing cleaned/normalized price
- comparable active listings within the active sale filtered universe
- price positioning relative to suburb listing context

### Rent Context
Canonical rent-side concepts include:
- suburb median rent
- rent-market activity/count metrics where available
- estimated gross yield may use annualized suburb median rent divided by selected sale listing price when explicitly labeled as an estimate

## Report / Export Metric Rules
- report metrics must stay consistent with the active page dataset and current canonical logic
- do not invent one-off PDF/report methodologies that disagree with page metrics
- if a metric is unavailable cleanly, degrade gracefully and label the fallback
- no hidden stale-dataframe or mismatched-scope calculation is acceptable in report outputs

## Deprecated Calculation Notes
- The former `REGION / Greater Sydney / HOUSE` `2026-01-01` anchor override is deprecated and removed.
- Any historical handoff that describes that override is superseded history, not active metric logic.
