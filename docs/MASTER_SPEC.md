# MASTER_SPEC (Legacy Index)

`MASTER_SPEC.md` is no longer the single mixed source-of-truth document.

Project documentation has been split into topic-based canonical files plus a dedicated history log under `docs/`.

## Read These Files Instead
- System behavior: [SYSTEM_SPEC.md](./SYSTEM_SPEC.md)
- Technical architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Metric definitions and formulas: [METRICS_AND_LOGIC.md](./METRICS_AND_LOGIC.md)
- Data sources and rebuild/update flow: [DATA_PIPELINE.md](./DATA_PIPELINE.md)
- Validation standards and audit expectations: [VALIDATION_AND_AUDIT.md](./VALIDATION_AND_AUDIT.md)
- Dated session history and rationale: [HANDOFF_HISTORY.md](./HANDOFF_HISTORY.md)
- Overview and docs map: [README.md](./README.md)

## Migration Note
The previous `MASTER_SPEC.md` mixed:
- canonical product rules
- technical architecture notes
- metrics/calculation logic
- data pipeline notes
- validation/audit expectations
- dated session handoffs

Those materials have now been reorganized by topic so current truth is easier to locate and maintain.

## Current Product Strategy Note
- The refined former external workflow is now the baseline product behavior.
- Internal mode uses that baseline directly.
- External mode is now the stricter public/test layer on top of the same baseline.
- The former richer internal-only workflow, including the old ranking-first path, is deprecated.
