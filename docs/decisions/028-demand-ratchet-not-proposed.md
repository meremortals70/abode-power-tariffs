# DR-028: The demand ratchet is researched and not proposed

| | |
|---|---|
| Status | Superseded in part by DR-048 |
| Since | Session seven (P35 research) |
| Origin | P35 |
| Related | DR-023, DR-048 |

## Decision

The integration does not model a demand ratchet. Demand is charged on the
highest completed interval in the rate's demand window across the billing
cycle, declared by interval (15, 30 or 60 minutes, or instantaneous) and by
basis (once for the cycle, or per day of it).

## Why

A ratchet bills on the higher of this cycle's peak and a floor derived from
past cycles. It is real and specified, and it earns nothing on an Australian
residential tariff. The full research is in the P35 document; it does not
need doing a third time.

## Rejected

- **Model the ratchet.** History across cycles, for a tariff structure no
  user of this integration has.

## Consequences

A plan with a ratchet would report a demand cost lower than the bill. If a
user turns up with one, this is the record to revisit.

## In the code

Checked against: 0.9.13 (2026-11-18). **Partly.** The ratchet
decision itself conforms: there is no ratchet and the peak is per cycle. The
interval list the Decision names no longer does - the instantaneous basis was
withdrawn by DR-048, so `DEMAND_INTERVALS` offers 15, 30 and 60 minutes only.

- `const.py:140` - `DEMAND_INTERVALS` - the declared averaging intervals
- `accounting.py:190` - `def demand_cost` - this cycle's peak only
- `accounting.py:209` - `def average_kw` - energy over a declared interval, which
  is the only form a demand charge takes

## The interval list, after DR-048

The Decision above is frozen and keeps "or instantaneous" as the record of
what was decided at the time. DR-048 is the record of the withdrawal: no
tariff bills demand from a single sample. Read the two together - this record
for the ratchet, DR-048 for the interval.
