# DR-047: The utility meter is a one-time convenience the plan does not own

| | |
|---|---|
| Status | Accepted |
| Since | Before 0.8.3 |
| Origin | Design; restated in `ARCHITECTURE.md`, session eleven |
| Related | DR-001, DR-016 |

## Decision

Configure can create a Home Assistant `utility_meter` helper on request, with
the plan's rates as its tariffs. It is a one-time convenience: the meter
belongs to the `utility_meter` integration, renaming a rate does not rename
its tariff, and removing the plan does not remove the meter. The nominated
tariff select (DR-001) is how the plan keeps it on the right tariff.

## Why

The energy dashboard needs cost split by tariff, which only a `utility_meter`
provides. Building one by hand with the right tariff names is tedious and
easy to get wrong.

## Rejected

- **Own the meter.** It lives in a config entry this integration does not
  control, and owning it would mean renaming its tariffs, the same harm the
  0.8.3 migration did (DR-037).

## Consequences

The meter's tariffs must be the strings the select write-back sends, or the
write-back finds no matching option and only logs a warning.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** The meter is
created with the four-segment identifiers as its tariffs, the same strings
the select write-back sends, so it is switched as the rate changes.

- `config_flow.py:3009` - `async_step_meter_create` - creates the meter
- `config_flow.py:3036` - `rate_id(self.config_entry.title` - identifiers as tariffs
- `coordinator.py:1012` - `qualified_name` - what the write-back sends
