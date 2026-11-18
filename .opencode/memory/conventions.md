> Coding conventions specific to Abode Power Tariffs.

## General

1. Solve the smallest version first. Add complexity only when justified.
2. Prefer explicit over clever.
3. Keep functions small and focused.
4. Name things after the domain, not the implementation.

## Home Assistant conventions

- Keep the eight pure modules free of Home Assistant imports.
- Public entity IDs, service names, config-flow keys and stored data keys are preserved unless an issue explicitly asks to change them.
- Comments explain why, and cite the design rule number when the reason is a standing rule.
- Docs and changelog use Australian/British spelling (`behaviour`, `licence`). Code identifiers and HA API names stay as upstream.

## Testing

- Every behaviour change needs a regression test that fails before and passes after.
- Pure tests go in `tests/` and must run without HA installed.
- HA behaviour tests go in `tests/test_config_flow.py`, `test_platform.py`, `test_runtime.py` as appropriate.
- Run the full CI before handing anything over: ruff, ruff format, mypy strict on the eight pure modules, full test suite, coverage ≥ 90%.

## Time handling

- Normalise to UTC before comparing or subtracting aware datetimes.
- Everything published leaves the component in local time with offset.
- Wall-clock plan definitions do not bend to DST.

## Proposals and findings

- One proposal open at a time.
- Findings are bullets in this file / `project.md`; proposals are numbered separately.
- Say what a proposal costs before asking for a decision.
