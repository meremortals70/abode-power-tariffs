# DR-022: A timed allowance belongs to its slot; a monthly one to the cycle

| | |
|---|---|
| Status | Accepted |
| Since | Slot scoping at 0.8.2 (P13); monthly sibling at 0.8.8 (P35) |
| Origin | Standing rule 8, the owner's hard rule |
| Related | DR-011, DR-021, DR-023 |

## Decision

A timed allowance belongs to the time slot, not the day. Each occurrence of a
capped slot has its own count, starting at zero on entry, and nothing carries
between occurrences. A monthly allowance is its sibling: it accumulates
across every slot and day of the billing cycle and resets on the billing
cycle day. Which one a rate has is declared, on the rate.

## Why

A retailer's "first 10 kWh of the evening peak" is ten kilowatt-hours each
evening, not ten a day spread across whatever rates happen to run. The count
used to reset at midnight, which split an overnight slot in two and gave a
morning slot the evening's leftovers.

## Rejected

- **A daily count reset at midnight.** Wrong for any slot that is not the
  whole day, and wrong for one spanning midnight.
- **Infer slot or month from the size of the cap.** A size says nothing about
  what the retailer meant.

## Consequences

A ledger's allowance key names the occurrence it belongs to: the slot and its
date, or the cycle. A count restored after a restart is used only if its key
matches the occurrence running now.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `const.py:137` - `ALLOWANCE_PERIODS` - slot or month, declared
- `plan.py:229` - `counts_monthly_allowance` - which one this rate has
- `accounting.py:160` - `slot_key` - one occurrence of one slot
- `accounting.py:170` - `allowance_key` - slot or cycle
- `sensor.py:535` - `allowance_key` - a restored count is kept only for the same occurrence
