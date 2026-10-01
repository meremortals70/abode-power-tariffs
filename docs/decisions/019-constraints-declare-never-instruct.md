# DR-019: Constraints declare, they never instruct

| | |
|---|---|
| Status | Accepted |
| Since | First release; coasting folded in as a constraint by 0.8.9 |
| Origin | Standing rule 9 |
| Related | DR-001, DR-014 |

## Decision

A rate can carry constraints such as `no_grid_import`, `grid_charge_battery`,
`precool_opportunity` and `coasting_permitted`, and the user can mark any of
them enforceable. The integration enforces none of it. Enforceable means the
user declared the rule part of what the rate means, so a consumer should
treat it as a rule rather than a hint. Each distinct constraint name declared
anywhere in the plan gets one binary sensor, on whenever the rate in force
carries it, with whether it is enforceable and which rate and period it is
attached to.

## Why

A constraint is a commitment the household made under its tariff, and only
the consumer can act on it. The hvac coordinator's DR-034 reads these as
absolute; this integration only states them. A sensor per name, not per rate,
lets an automation watch one entity for "no grid import" whatever rate
carries it.

## Rejected

- **A fixed list of constraints only.** Suggested names seed the form, but a
  user can declare their own, and a consumer this integration has never heard
  of can read them.
- **Coasting as its own tickbox.** It says the same kind of thing as every
  other rule, so it was folded in as one.
- **One sensor per rate.** Says nothing useful while a different rate is in
  force.

## Consequences

A consumer decides what enforceable means for it.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** A sensor is
on while a rate in force on either side carries its rule, and reports the
rate and period on each side it is attached to.

- `const.py:75` - `KNOWN_CONSTRAINTS` - suggested names, not a closed list
- `plan.py:795-800` - `export_rate.constraints` - names gathered from both sides
- `binary_sensor.py:67` - `_import_rate` - the import rate in force
- `binary_sensor.py:74` - `_export_rate` - the export rate in force
- `binary_sensor.py:90` - `def is_on` - either side
