# DR-049: Each meter declares its unit and a mismatch is advisory

| | |
|---|---|
| Status | Accepted |
| Since | 0.9.13 (2026-11-18) |
| Origin | Owner instruction on meter units |
| Related | DR-003, DR-021, DR-030 |

## Decision

Each energy meter has its own declared unit: Wh, kWh or MWh, defaulting to
kWh. Readings are scaled to kWh before they reach a ledger. When a reading is
taken, the unit the meter's state reports is compared with the declared one;
a mismatch logs a warning and raises a repair naming the meter, what it
reports and what the plan expects. It never refuses the reading. The repair
clears when the two agree again.

## Why

The integration read the bare number from the nominated meter and called it
kWh. A meter publishing watt-hours was counted a thousand times too high, and
one publishing megawatt-hours a thousand times too low. Nothing said so: every
allowance count, demand average and published energy figure was silently
wrong by three orders of magnitude.

The owner's instruction was explicit: there must be a field to choose the
unit, and a warning at read time if the meter disagrees, so the user has an
opportunity to fix it. A mismatch is information about a wrong declaration,
not evidence that the reading is unusable. The declaration is what the number
means, so refusing the meter would replace one silent failure with another.

Both fields are optional in stored configuration. A plan saved before this
build reads as kWh, which is what it was already assuming. There is no config
entry migration (DR-037), so nothing rewrites a stored entry.

## Rejected

- **Detect the unit from the meter's `unit_of_measurement` alone.** A missing
  or wrongly labelled unit is exactly the case that caused the defect, and
  choosing silently would hide the disagreement rather than show it.
- **Refuse to read a meter whose unit disagrees.** The user asked for a chance
  to correct the choice, not a veto; stopping the count would leave the cycle
  incomplete over a setting that takes one form submission to fix.
- **One unit for both meters.** Import and export are separate flows with
  separate meters (standing rule 5); the same source can publish different
  units on different entities.

## Consequences

The two extra fields appear in setup and Configure, with a default so setup
still asks the minimum. A mismatched meter produces a warning on every read
boundary and one repair, which clears itself once the two agree.

Revisit if a meter reports a unit outside Wh/kWh/MWh; the conversion table is
the one place to extend.

## In the code

Checked against: 0.9.13 (2026-11-18). **Conforms.**

- `const.py:44` - `CONF_IMPORT_ENERGY_UNIT` - the stored import declaration
- `const.py:45` - `CONF_EXPORT_ENERGY_UNIT` - the stored export declaration
- `const.py:49` - `ENERGY_UNITS` - Wh, kWh and MWh
- `const.py:50` - `DEFAULT_ENERGY_UNIT` - kWh, for a plan with no field stored
- `const.py:52` - `ENERGY_UNIT_TO_KWH` - the one conversion table
- `const.py:203` - `ISSUE_METER_UNIT` - the repair's key
- `coordinator.py:894` - `_read_kwh` - reads, scales and returns kWh
- `coordinator.py:918` - `_unit_for` - the declaration for this meter's side
- `coordinator.py:926` - `_check_meter_unit` - warn and raise on disagreement
- `coordinator.py:966` - `_clear_meter_unit_issue` - clears it when they agree
- `config_flow.py:925` - `CONF_IMPORT_ENERGY_UNIT` - the import field on the form
- `config_flow.py:2858` - `CONF_IMPORT_ENERGY_UNIT` - Configure reads the stored value
- `config_flow.py:2874` - `CONF_EXPORT_ENERGY_UNIT` - and the export one
