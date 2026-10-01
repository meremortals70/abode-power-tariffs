# DR-020: Declaring a cap is not counting against it

| | |
|---|---|
| Status | Superseded by DR-021 |
| Since | Before 0.8.4; revoked session seven, removed from the code at 0.8.8 |
| Origin | Standing rule 7 (original) |
| Related | DR-021 |

## Decision

A rate can declare an energy allowance and a fallback rate past it, and that
declaration is a fact about the plan. Counting energy against the cap is a
separate, opt-in choice, made with its own tickbox.

## Why

The integration was a pure reporter. Declaring a cap kept the plan complete;
counting it meant measuring a meter, which a reporter does not do unless the
user asked.

## Rejected

- **Count every declared cap.** Turned the reporter into something that
  accumulates, which at the time was outside what it was for.

## Consequences

A user could declare a cap and never have it applied, and the published price
past the cap was then wrong for as long as they had not ticked the box.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Superseded.** The counting tickbox
and its stored key, `CONF_COUNT_ALLOWANCE`, are gone.
