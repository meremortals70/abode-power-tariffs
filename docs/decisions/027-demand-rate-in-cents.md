# DR-027: The demand rate is entered in cents, like every other price

| | |
|---|---|
| Status | Accepted |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | Live testing, session twelve |
| Related | DR-014 |

## Decision

A demand rate is entered and stored in cents per kW, like every other price
in the plan, and held and used internally in dollars.

## Why

Every other price on the form is in cents. The demand rate alone was in
dollars, so a user typing the number from their bill in the same unit as the
field beside it entered a demand charge a hundred times too high.

## Rejected

- **Keep dollars and relabel the field.** Still the one field in a different
  unit from its neighbours.

## Consequences

The stored key keeps its historical name, `demand_rate_per_kw_month`, which
is also wrong about the basis now that a rate may be charged per day; it
cannot be renamed (DR-037) and carries a comment instead.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:297` - `_cents_to_dollars` - import demand rate, cents in
- `plan.py:444` - `_cents_to_dollars` - export demand rate, cents in
- `plan.py:202` - `A stored key cannot be renamed` - the misnamed key's comment
