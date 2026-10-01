# DR-005: One service holds one plan; archiving is `valid_to`

| | |
|---|---|
| Status | Accepted |
| Since | Confirmed in `ARCHITECTURE.md`, session eleven (2026-08-23) |
| Origin | Architecture definition, session eleven |
| Related | DR-007 |

## Decision

Each plan is set up as its own Home Assistant service, tied to its own
device. A household with more than one meter sets up one service per meter.
When the tariff changes, the old plan is archived by setting its `valid_to`,
and stays in place; the user sets up a new service, under the same device,
for the plan that replaces it.

## Why

A tariff changes over time and the history of what it used to be is a fact
worth keeping. Editing a plan in place to the new tariff destroys that
history. Holding several plans inside one service invents a container Home
Assistant does not have, and confused the session that assumed it until the
device page was looked at.

## Rejected

- **One service managing several plans.** Not how a service-type integration
  works, and every entity would need to say which plan it belongs to.
- **Delete the old plan's service.** Loses the history.
- **Link the new plan's `valid_from` to the old one's `valid_to`
  automatically.** Nothing ties the two services together except the device
  the user puts them under; lining up the dates is on the user.

## Consequences

A plan simply reaching `valid_to` with no successor is a different case from
archiving, and is treated as a failure (DR-007).

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `manifest.json:8` - `service` - a service-type integration
- `plan.py:893` - `is_active_on` - `valid_from` and `valid_to` decide whether the plan is in force
