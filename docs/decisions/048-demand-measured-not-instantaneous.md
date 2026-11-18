# DR-048: Demand is measured over a metering interval, never from an instant

| | |
|---|---|
| Status | Accepted |
| Since | 0.9.13 (2026-11-18) |
| Origin | Owner challenge on register entry 1 |
| Related | DR-023, DR-027, DR-028 |

## Decision

The demand averaging interval offers 15, 30 and 60 minutes. There is no
instantaneous basis. A stored interval of zero is read as the 30-minute
default and reported, both in Configure and as a repair, rather than being
refused or quietly corrected.

## Why

The interval list used to offer `0 = instantaneous` as a fourth choice. It was
wrong, and it was wrong from the outset.

Every tariff bills demand as an average over a metering interval - 30 minutes
in Australia, 15 in the United States, half-hourly for UK capacity charges -
because a sample of one instant is an artefact of when the meter happened to
be polled, and one motor start would set a monthly charge. Nothing bills that
way.

So the code that measured the instantaneous draw was doing something no bill
could reflect, and the register entry that read "instantaneous demand never
produces a peak" described a fiction rather than a defect.

Withdrawing the option is not the same as refusing it. There is no config entry
migration and nothing may rewrite a stored entry (DR-037), so a plan that
stores zero still loads - but reading it as 30 minutes changes what the stored
value means, and a silent change of meaning is the truth failure this project
is built against. It is therefore said twice: Configure's "Worth checking"
block, and a repair naming the affected rates. Saving the rate through
Configure replaces the zero with what the form now offers.

## Rejected

- **Keep the instantaneous basis and measure it over the meter's own reporting
  span.** That span is a property of how often the integration is polled, not
  of the tariff, so the number would change with network conditions and mean
  nothing against a bill.
- **Nominate a power sensor and measure live draw.** A different measurement of
  a different thing - useful, and not a demand charge. Left open as its own
  proposal rather than folded into this one.
- **Refuse a plan that stores zero, or rewrite it silently.** Refusing breaks a
  plan that has worked, and there is no migration path to soften it. Rewriting
  silently changes a stored value without telling the owner, which is worse
  than either.

## Consequences

A plan authored before this build reads as 30 minutes and is told so, once,
until the rate is saved again. Nothing else changes: the arithmetic refuses a
zero interval as it always did, so a hand-written declaration cannot divide by
zero.

Revisit if a retailer ever bills a demand charge from a single sample. Nothing
in the Australian market does, and the record above is where that evidence
lives.

## In the code

Checked against: 0.9.13 (2026-11-18). **Conforms.**

- `const.py:140` - `DEMAND_INTERVALS` - 15, 30 and 60 minutes; no instantaneous token
- `const.py:207` - `ISSUE_INSTANTANEOUS_DEMAND` - the repair's key
- `plan.py:344` - `_one_of_int` - a stored zero falls back to the 30-minute default
- `validate.py:416` - `instantaneous_demand_problems` - finds a stored zero by key, before the model has coerced it
- `validate.py:395` - `INSTANTANEOUS_DEMAND_ADVICE` - what Configure says about it
- `coordinator.py:977` - `_report_legacy_demand_basis` - the repair, raised at setup
- `coordinator.py:1014` - `_instantaneous_issue_id` - cleared unconditionally on the next start
- `config_flow.py:1771` - `_plan_text` - appends the advice to "Worth checking"
- `accounting.py:132` - `def interval_key` - a zero interval has no key and returns None
- `accounting.py:145` - `def interval_is_complete` - and never completes
