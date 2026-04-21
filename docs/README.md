# Documentation Index

NSW Property Analytics is a data-driven property decision platform focused on NSW sale, rent, and market-trend workflows.

Current operating context:
- Product stage: Baseline product consolidation + public test restriction layer
- Internal mode now uses the refined product baseline
- External mode is the public/test layer on top of that baseline
- Legacy richer internal behavior is deprecated and must not remain the default source of truth

## Docs Map
- System behavior and canonical product rules: [SYSTEM_SPEC.md](./SYSTEM_SPEC.md)
- Technical structure, ownership, and state flow: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Metric definitions and calculation logic: [METRICS_AND_LOGIC.md](./METRICS_AND_LOGIC.md)
- Data sources, rebuild flow, and update operations: [DATA_PIPELINE.md](./DATA_PIPELINE.md)
- Validation standards and repeatable audit rules: [VALIDATION_AND_AUDIT.md](./VALIDATION_AND_AUDIT.md)
- Historical session record and change rationale: [HANDOFF_HISTORY.md](./HANDOFF_HISTORY.md)

## Documentation Authority Model
- [SYSTEM_SPEC.md](./SYSTEM_SPEC.md) defines system behavior.
- [METRICS_AND_LOGIC.md](./METRICS_AND_LOGIC.md) defines calculations and formulas.
- [DATA_PIPELINE.md](./DATA_PIPELINE.md) defines data flow and rebuild/update logic.
- [ARCHITECTURE.md](./ARCHITECTURE.md) defines technical structure and state ownership.
- [VALIDATION_AND_AUDIT.md](./VALIDATION_AND_AUDIT.md) defines validation and audit rules.
- [HANDOFF_HISTORY.md](./HANDOFF_HISTORY.md) records history only.
- No active rule should exist only in `HANDOFF_HISTORY.md`.

## How To Use These Docs
- Read `SYSTEM_SPEC.md` when the question is: “How should the product behave?”
- Read `ARCHITECTURE.md` when the question is: “How is the app organized technically?”
- Read `METRICS_AND_LOGIC.md` when the question is: “How is this metric calculated?”
- Read `DATA_PIPELINE.md` when the question is: “How do I update or rebuild the data?”
- Read `VALIDATION_AND_AUDIT.md` when the question is: “What must be checked after changes?”
- Read `HANDOFF_HISTORY.md` when the question is: “What changed recently, and why?”

## Authority Model
- Current truth is topic-based and lives in the canonical files listed above.
- `HANDOFF_HISTORY.md` records dated implementation history and rationale.
- If a dated handoff introduced a rule that remains active, that rule should already be incorporated into the relevant canonical file.

## Rule Promotion Requirement
- After each session:
  - if the session introduces or changes an active rule, update the corresponding canonical document in the same session
  - if the session does not introduce or change an active rule, record the outcome only in `HANDOFF_HISTORY.md`
- Handoff entries may explain rationale, but they must not remain the sole location of an active rule.

## Single Source Of Truth Enforcement
- Each active rule must exist in only one canonical file.
- `SYSTEM_SPEC.md` = behavior
- `METRICS_AND_LOGIC.md` = calculation
- `DATA_PIPELINE.md` = data/update flow
- `ARCHITECTURE.md` = technical structure and ownership
- `VALIDATION_AND_AUDIT.md` = validation and audit requirements
- If duplication exists, keep one authoritative definition and replace other copies with references.

## Session Workflow Standard
1. Discuss or identify the change.
2. Implement the change.
3. Record the session handoff.
4. Promote any active rule into the correct canonical document.
5. Check that no active rule remains only in `HANDOFF_HISTORY.md`.

## Doc Usage Protocol For Future Sessions
- Always read `README.md` first.
- Then read only the relevant canonical docs for the task.
- Do not load every doc by default unless the task is a system-level investigation or a documentation restructuring task.
- When a question is about “what,” prefer `SYSTEM_SPEC.md`.
- When a question is about “how calculated,” prefer `METRICS_AND_LOGIC.md`.
- When a question is about “how updated,” prefer `DATA_PIPELINE.md`.
- When a question is about “what to verify,” prefer `VALIDATION_AND_AUDIT.md`.

## Documentation Quality Checklist
- Is this rule defined in the correct file?
- Is this rule duplicated anywhere else?
- Is this rule testable or auditable?
- Does this rule contradict any existing canonical rule?
- If this came from a handoff, has the active part been promoted?
