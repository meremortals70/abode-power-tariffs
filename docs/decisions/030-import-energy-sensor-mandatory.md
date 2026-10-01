# DR-030: The import energy sensor is mandatory

| | |
|---|---|
| Status | Accepted; supersedes DR-029 |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | `ARCHITECTURE-GAPS.md` item 7, contingent on rule 6's removal |
| Related | DR-006, DR-021, DR-023, DR-029 |

## Decision

Every plan requires an import energy sensor, whether or not any rate in it
declares a demand charge or an allowance. Setup and Configure both refuse to
continue without one.

## Why

The import meter is what allowance and demand calculations are measured
against, and what data completeness is judged on. A plan that adds a capped
rate later, in Configure, would otherwise gain a ledger with nothing to count
against, and the conditional requirement was a rule this project never had
(DR-029).

## Rejected

- **Required only once demand or an allowance is declared (the code at
  0.8.10).** The rule it implemented was withdrawn.

## Consequences

The export energy sensor and the holiday sensor stay optional.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `config_flow.py:828-835` - `energy_sensor_required` - refused at setup
- `config_flow.py:2676-2678` - `energy_sensor_required` - refused in Configure
