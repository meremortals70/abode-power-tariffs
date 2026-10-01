# DR-046: Tax is declared for the record, and never applied

| | |
|---|---|
| Status | Accepted |
| Since | First release; wording made country-neutral by 0.9.10 |
| Origin | Design; `ARCHITECTURE-GAPS.md` item 8 |
| Related | DR-037 |

## Decision

A plan declares whether its prices include tax and at what rate. The rate is
recorded and shown, and never applied to any published price. Everything the
user reads says "tax", not "GST".

## Why

Prices are published as the user entered them, which is how their bill
quotes them. Applying tax would change a price the user can check against
the bill into one they cannot. The wording says tax because Australian bills
quote GST-inclusive prices while most European and US rate sheets quote
prices without tax, and the integration is not Australian-only.

## Rejected

- **Apply the declared tax to published prices.** Every consumer then sees a
  price that is not on the bill.
- **Rename the stored keys to say tax.** Needs a migration (DR-037); the keys
  stay `gst_percent` and `prices_include_gst`.

## Consequences

A consumer that needs an ex-tax or inc-tax figure has the declaration to work
it out.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** `gst_percent` is
stored, round-tripped and shown, and read nowhere else.

- `strings.json:25` - `Prices include tax` - the label
- `strings.json:33` - `tax included` - the description, country-neutral
- `strip.py:260` - `gst_percent` - shown on the rate plan card, not applied
