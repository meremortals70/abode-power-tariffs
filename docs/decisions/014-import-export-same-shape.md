# DR-014: Import and export are separate flows of the same shape

| | |
|---|---|
| Status | Accepted |
| Since | Separate flows from first release; same shape by 0.9.10 (2026-08-27) |
| Origin | Standing rule 5; `ARCHITECTURE-GAPS.md` items 2 and 3 |
| Related | DR-013, DR-018, DR-023 |

## Decision

Import and export are two separate flows, with separate rates and separate
periods, never blended. What they share is shape: an import rate and an
export rate are each a name, a price, a demand declaration, an allowance
declaration, and constraints with their enforceable subset. Being on the
export side never means a rate is allowed fewer of those. The one shortcut is
the all-day feed-in tickbox, which ends the export periods branch; it does
not end the declaration, because an all-day feed-in still has a price, a cap
on it and a price past the cap.

## Why

A rate on one side says nothing about the other: an import rate can be flat
while the feed-in price moves. But treating export as a lesser kind of rate
left `ExportRate` with no demand fields and no constraints, so a plan with an
export demand charge or an export rule could not be described at all.

## Rejected

- **One rate carrying both prices.** That was `Rate.export_price`, which
  predated `ExportRate` and was removed as dead code.
- **Fix export as a special case.** The question was always whether import
  had the same flaw; the answer was a shared shape.

## Consequences

Every side-specific path has a mirror, and the four-segment identifier
(DR-016) carries the side so the two never collide.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:172` - `class Rate` - the import shape
- `plan.py:355` - `class ExportRate` - the same shape on the export side
- `plan.py:374` - `demand_rate_per_kw_month` - export demand
- `plan.py:369-370` - `enforceable_constraints` - export constraints
- `plan.py:500-503` - `export_same_all_day` - the all-day shortcut with its cap
