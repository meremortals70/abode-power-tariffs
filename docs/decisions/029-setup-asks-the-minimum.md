# DR-029: Setup asks the minimum

| | |
|---|---|
| Status | Superseded by DR-030 |
| Since | Before 0.8.4; withdrawn by the owner, session eleven; out of the code by 0.9.10 |
| Origin | Standing rule 6, mistakenly copied over from another project |
| Related | DR-030 |

## Decision

Every field that is part of what a rate is appears on the setup form, and
almost none of it is required. A field becomes required only when an earlier
answer makes it necessary: a choice that cannot be honoured without a meter
requires the meter. Everything else defaults and can be changed later in
Configure.

## Why

Recorded as a standing rule for this project. The owner confirmed in session
eleven that it had been copied over from another project by mistake and was
never this project's rule.

## Rejected

- **Require the import energy sensor for every plan.** Under this rule a
  field becomes required only when an earlier answer makes it necessary,
  and a plan with no demand charge and no allowance had nothing that
  needed the meter.

## Consequences

Under it, the import energy sensor was required only once a rate declared
demand or an allowance, and a plan without one could not report its own
data completeness.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Superseded.** The conditional
`_meter_required_without_one` is gone; the meter is always required
(DR-030).
