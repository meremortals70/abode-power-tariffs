# DR-025: Fixed charges are declared, never accumulated

| | |
|---|---|
| Status | Superseded by DR-026 |
| Since | 0.8.2 (P11); revoked session seven |
| Origin | Standing rule 11 (original) |
| Related | DR-026 |

## Decision

The daily supply charge and other fixed charges are declared on the plan and
published as declared. The integration does not accumulate them; a consumer
that wants a running total multiplies for itself.

## Why

P11 removed a supply-charge accumulator on the principle that the integration
is a system of truth, not an accounting system. Consumers calculate from the
published facts.

## Rejected

- **Accumulate the supply charge.** At the time, outside what the integration
  was for.

## Consequences

The billing cycle day was declared only, with nothing derived from it.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Superseded.** Replaced by the
accrual in DR-026.
