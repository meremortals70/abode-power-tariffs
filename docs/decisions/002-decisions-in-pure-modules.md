# DR-002: Decisions live in pure modules

| | |
|---|---|
| Status | Accepted |
| Since | First release; `accounting.py` joined at 0.8.8 |
| Origin | Design |
| Related | DR-004, DR-023 |

## Decision

Every decision about the plan lives in modules that import nothing from Home
Assistant: `const`, `plan`, `validate`, `intervals`, `allowance`,
`accounting`, `strip` and `serialise`. The coordinator and the entity
platforms gather inputs and publish results. A test fails the build if a pure
module grows a `homeassistant` import.

## Why

The decisions are where the bugs are: daylight-saving arithmetic, period
coverage, billing-cycle boundaries, which rate a minute belongs to. Kept pure,
they can be tested in under a second with almost nothing installed, and a
reviewer can read them without knowing Home Assistant.

## Rejected

- **Move the pure modules into a subpackage with an empty `__init__`.** Would
  remove the `tests/_pure.py` shim that loads them off disk. Judged not worth
  the churn.
- **Test only against real Home Assistant.** Slow, and the stub suite missing
  real-Home-Assistant bugs is answered by running both (the real suite in
  `tests_real_ha/`), not by dropping the fast one.

## Consequences

Importing anything from the package normally runs `__init__.py`, which
imports Home Assistant, so `tests/_pure.py` reads the pure files into a
synthetic package. The stub suite cannot see anything the frontend does,
label lookup included; `tests_real_ha/` exists for that.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** Eight pure modules,
all listed in the enforcing test.

- `tests/test_attributes.py:362` - `PURE` - the eight modules
- `tests/test_attributes.py:373` - `test_no_home_assistant_imports` - the build fails on an import
