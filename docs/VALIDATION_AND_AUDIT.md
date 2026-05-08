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

## Market Region Validation
- [ ] Region exists in the canonical Market Region mapping
- [ ] Region appears in the relevant rolling parquet output
- [ ] Selector exposes the region where Market Region options are shown
- [ ] KPI and chart render correctly for the region
- [ ] No null postcode leakage remains for the intended mapped postcodes
- [ ] No code or validation path assumes a fixed number of regions in the layer

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
- [ ] Public deploy consumes the same processed/current artifacts included for internal functional behavior

## Data Pipeline Checklist
- [ ] Required update/rebuild script completed without crash
- [ ] Expected output artifacts were refreshed
- [ ] Output timestamps are recent for the touched artifacts
- [ ] Latest available date in rebuilt data is sensible
- [ ] Row count did not collapse abnormally
- [ ] Schema did not break unexpectedly
- [ ] Market Region mapping postcodes expected for the change are populated and not null in the compatibility dim
- [ ] Legacy `region16` outputs were refreshed if the Market Region layer changed
- [ ] Deployment/data-sync assumptions were rechecked if the rebuild is intended for release

## Public Full-Data Validation
- [ ] Public Streamlit Market View renders without crash
- [ ] Public Streamlit reads `Processed/mart_daily_rolling/` for daily trend data
- [ ] Price-band logic can use the full internal fact-sales path
- [ ] Latest visible date matches the deployed processed data
- [ ] KPI outputs remain consistent with the internal logic path
- [ ] No fallback to cache paths exists in runtime behavior

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
