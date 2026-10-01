# DR-011: Monthly figures run on the billing cycle, starting on day 1 to 28

| | |
|---|---|
| Status | Accepted |
| Since | Day declared at 0.8.4 (P12); computed at 0.8.8 (P35) |
| Origin | P12; rule 11's revocation, session seven |
| Related | DR-010, DR-022, DR-026 |

## Decision

Every figure that resets monthly (a monthly allowance, the demand cost for
the cycle, the supply charge this cycle) resets on the plan's billing cycle
day, never on the first of the calendar month unless the cycle day is the
first. The day must be 1 to 28; 29 to 31 are refused on the form and by
validation.

## Why

A retailer bills on cycles that start on a fixed day of the month. A calendar
month disagrees with the bill for every household whose cycle starts on any
other day.

## Rejected

- **Calendar months.** Wrong for most bills.
- **Allow 29 to 31.** A cycle starts on the same day every month, so the day
  has to be one that every month has. A retailer does not bill on the 31st.
- **Declare the day only and leave the arithmetic to consumers (P12 as
  first built).** Overtaken when rule 11 was revoked and the integration
  started accumulating against the cycle.

## Consequences

Cycle identity is a key, not a date comparison: asking whether two dates are
"the same month" has no good answer when the cycle starts on the 12th.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `const.py:27` - `MAX_BILLING_CYCLE_DAY` - 28
- `validate.py:313-317` - `MAX_BILLING_CYCLE_DAY` - refused by validation
- `config_flow.py:827` - `billing_day_out_of_range` - refused on the setup form
- `accounting.py:45` - `cycle_start` - the cycle from its declared day
- `coordinator.py:551` - `_refresh_cycle` - rolls by key
- `plan.py:716` - `billing cycle starts, 1 to 28` - the field's comment
