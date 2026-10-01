# DR-009: The plan is wall-clock and does not bend to daylight saving

| | |
|---|---|
| Status | Accepted |
| Since | First release; fall-back instants fixed at 0.8.2 (P9) and 0.8.5 (P25, P26) |
| Origin | Standing rule 3 |
| Related | DR-008, DR-010 |

## Decision

A plan is declared in local wall-clock time. A peak declared 16:00 to 21:00
is 16:00 to 21:00 on both sides of a daylight-saving transition. Boundaries
are held as minutes past local midnight.

## Why

That is what a retailer's tariff means. A peak that shifted an hour with the
clocks would be a different tariff from the one on the bill.

## Rejected

- **Store boundaries as UTC instants.** The peak would move an hour twice a
  year.

## Consequences

Minutes past midnight do not identify an instant on the fall-back morning,
when the same wall time names two moments an hour apart. Comparing clock
digits rather than elapsed time was the cause of P9: `next_boundary` returned
an instant already in the past. Every wall-clock time is resolved to its real
instants with `instants_at`, never with wall-clock arithmetic, which always
picks the first pass.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:455` - `Period` - start and end as minutes past local midnight
- `intervals.py:146` - `instants_at` - every real instant a wall time names
- `intervals.py:166` - `next_boundary` - compared in UTC
