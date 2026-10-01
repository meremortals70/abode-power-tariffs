# DR-028: The demand ratchet is researched and not proposed

| | |
|---|---|
| Status | Accepted |
| Since | Session seven (P35 research) |
| Origin | P35 |
| Related | DR-023 |

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

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** No ratchet; the peak
is per cycle.

- `const.py:112` - `DEMAND_INTERVALS` - the declared averaging intervals
- `accounting.py:189` - `def demand_cost` - this cycle's peak only
