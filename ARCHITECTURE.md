> Living document. Update when layers, boundaries, or conventions change.

# Architecture — Abode Power Tariffs

## Purpose

A Home Assistant custom integration that is the canonical source of truth for a household's electricity tariff plan. The user describes the plan once; the component publishes what energy costs now, what it will cost over the next N hours, which rate is in force, and what rules the user declared against it.

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Runtime | Python 3.13 |
| Platform | Home Assistant 2025.2.0+ |
| Language | Python 3.13 |
| Testing | `unittest`, `pytest-homeassistant-custom-component` (future), `ruff`, `mypy` |
| Packaging | HACS custom integration |

## Directory structure

```text
custom_components/abode_power_tariffs/
├── __init__.py              # Integration bootstrap, config entry lifecycle
├── config_flow.py           # Setup and options flow UI
├── coordinator.py           # Home Assistant coordinator, scheduling, state tracking
├── entity.py                # Base entity classes
├── sensor.py                # Published sensors (current rate, next change, forecasts, charges)
├── binary_sensor.py         # Constraint/period binary sensors
├── diagnostics.py           # Diagnostics download
├── const.py                 # Public constants and config keys
├── services.yaml            # Service definitions
├── strings.json             # Translations keys
├── icons.json               # Icon mappings
├── manifest.json            # Integration metadata
├── quality_scale.yaml       # HA quality scale checklist
├── brand/                   # Brand assets
├── translations/            # UI translations
└── pure layer (no Home Assistant imports)
    ├── plan.py              # Domain model: Plan, Rate, Period, Timetable
    ├── validate.py          # Validation rules
    ├── intervals.py         # Interval generation across DST
    ├── allowance.py         # Allowance counting logic
    ├── accounting.py        # Demand intervals, peaks, ledgers, cycle arithmetic
    ├── strip.py             # Rendering / text output
    └── serialise.py         # CSV / diagnostics serialisation

tests/
├── test_attributes.py       # Enforces pure-layer isolation
├── test_config_flow.py      # Config flow tests
├── test_core.py             # Core model tests
├── test_platform.py         # Platform tests
├── test_runtime.py          # Runtime/coordinator tests
├── _ha_stubs.py             # Hand-rolled HA stubs
└── _pure.py                 # Synthetic package loader for pure modules
```

## Layer rules

1. **Pure modules** (`plan`, `validate`, `intervals`, `allowance`, `accounting`, `strip`, `serialise`, `const`) import nothing from Home Assistant. They contain all domain decisions.
2. **Home Assistant layer** (`__init__.py`, `coordinator.py`, `config_flow.py`, `entity.py`, `sensor.py`, `binary_sensor.py`, `diagnostics.py`) translates between HA APIs and the pure layer.
3. **Tests in `tests/_pure.py`** load pure modules without running `__init__.py`, because importing the package normally imports Home Assistant.
4. **Public identifiers are preserved** unless an issue explicitly asks to change them. Users have automations and history keyed to entity IDs and service names.

## Data flow

1. User creates a config entry through `config_flow.py`.
2. `plan.py` builds a `Plan` from the stored config.
3. `coordinator.py` schedules updates and reads input sensors (import/export energy, holiday).
4. `intervals.py` generates wall-clock / DST-aware intervals.
5. `allowance.py` tracks slot-scoped or monthly allowance usage.
6. `sensor.py` / `binary_sensor.py` publish state and attributes in local time.
7. `strip.py` renders the plan as a single text table.
8. `serialise.py` exports rates/periods to CSV and diagnostics.

## Cross-cutting concerns

- **Time:** All internal datetime arithmetic normalises to UTC; everything published is local time with offset.
- **DST:** Wall-clock plan definitions do not bend to DST. A rate 16:00–21:00 stays 16:00–21:00 on both sides of a transition. Real instants are resolved via `intervals.py`.
- **Validation:** Form-level validation lives in `validate.py`; business-rule validation lives in `plan.py`.
- **Storage:** Config entry data is the source of truth. No migration mechanism exists (removed at 0.8.4).

## Decisions

| Date | Decision | Rationale |
| ---- | -------- | --------- |
| 0.8.0 | Pure / HA split | Keep domain logic testable without HA installed |
| 0.8.2 | Slot-scoped allowances | Owner rule: allowance belongs to the time slot, not the day |
| 0.8.4 | Remove config entry migration | Version in `manifest.json` is build number only |
| 0.8.4 | One-table plan render | Avoid restating rates twice under different names |

## Known issues / next work

See `.opencode/memory/project.md` for the live register.
