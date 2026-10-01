# DR-024: An implausible meter jump is ignored

| | |
|---|---|
| Status | Accepted |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | Live testing, session twelve |
| Related | DR-023 |

## Decision

A meter delta of zero or less, or above 10,000 kWh between two consecutive
readings, contributes nothing to a ledger. The next reading is measured from
the new total.

## Why

The only check was for a positive delta. A meter entity swapped out from
under the integration, or a hardware fault, produces one reading that jumps
by an amount no household draws between two readings, and it was silently
accepted forever after, corrupting the allowance and demand figures for the
rest of the cycle.

## Rejected

- **A ceiling tuned to this house.** Site data in source. 10,000 kWh is far
  above what even a 400 A three-phase service could draw in an hour, and
  energy monitors report every few minutes.
- **Raise a gap instead.** The meter is readable; one reading is absurd.

## Consequences

A genuine jump that large is impossible on a household service, so nothing
real is lost. A meter reset (a negative delta) resumes counting correctly,
as it already did.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `allowance.py:85` - `MAX_PLAUSIBLE_DELTA_KWH` - the ceiling
- `allowance.py:88` - `def accumulate` - rejects it
