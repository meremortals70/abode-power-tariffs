# DR-000: Origin and purpose

| | |
|---|---|
| Status | Accepted |
| Since | Before the repository |
| Origin | The project brief |
| Related | Every other record |

## Decision

Build one Home Assistant integration that is the canonical source of truth
for a household's electricity tariff plan. The user describes the plan once;
the integration publishes what energy costs now, what it will cost over the
next few hours, which rate is in force, and what rules the user declared
against it.

## Why

The tariff model started inside a control project. Everything in a house that
cares about price needs the same plan: an EV charger deciding when to charge,
a battery deciding when to discharge, an air conditioner deciding when to
precool, and Home Assistant's own energy dashboard. Held inside one control
project, every other consumer either duplicates the plan or cannot see it, and
duplicates drift. Home Assistant had no clean answer for this.

It was separated out deliberately so the tariff model is useful to Home
Assistant generally, not to one automation.

## Rejected

- **Keep the tariff inside the control project.** Two sources of truth that
  drift; the hvac coordinator's own DR-004 records the same decision from the
  consuming side.
- **Adopt an existing tariff integration.** None modelled timetables,
  per-rate allowances, demand charges and declared constraints together.

## Consequences

Every later record is read against this one. A proposal that makes the
integration decide something for a consumer, or hold anything that is not a
fact about the plan or the cost of energy right now, has to argue against the
brief, not just for itself.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms** at the level of the
whole integration.

- `manifest.json:2` - `abode_power_tariffs` - the domain
- `manifest.json:8` - `service` - one service per plan (DR-005)
