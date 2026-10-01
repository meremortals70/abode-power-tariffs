# DR-001: It reports, it never commands

| | |
|---|---|
| Status | Accepted |
| Since | First release |
| Origin | Standing rule 1 |
| Related | DR-000, DR-019, DR-047 |

## Decision

The integration publishes facts and writes nothing, with one exception: a
`utility_meter` tariff select the user has explicitly nominated is set to the
rate in force. That write maintains a projection of state; it is not a
decision.

## Why

A source of truth that also acts has become a controller, and the consumers
it serves can no longer tell whether a price changed because the plan says so
or because the integration decided something. Home Assistant's energy
management needs accumulation split by tariff, which only a `utility_meter`
helper provides, and the only way to tell one which tariff is current is to
write its select. That one write is the plan restated, not a choice.

## Rejected

- **Control the battery, the charger or the inverter directly.** That is the
  consumer's decision; a rule declared on a rate (DR-019) is how the plan
  reaches them.
- **No write at all.** The energy dashboard then cannot split cost by tariff
  without the user building an automation that restates the plan.

## Consequences

Anything that has to act on a price or a constraint lives in another
integration. The select is only ever written when the user named it, and only
with an option it already has.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** The only service call
the coordinator makes is `select.select_option` on nominated entities.

- `coordinator.py:998` - `_async_write_tariff_selects` - the one write
- `coordinator.py:1004` - `CONF_TARIFF_SELECTS` - only selects the user nominated
- `coordinator.py:1038` - `select_option` - the call itself
