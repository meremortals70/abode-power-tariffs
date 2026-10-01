# DR-021: A declared cap is counted

| | |
|---|---|
| Status | Accepted; supersedes DR-020 |
| Since | 0.8.8 (P35); last trace of the tickbox removed by 0.9.10 |
| Origin | The owner's decision, session seven, revoking rule 7 |
| Related | DR-003, DR-020, DR-022, DR-023 |

## Decision

A declared allowance is counted. There is no opt-in and no counting tickbox:
declaring a cap is what makes the integration measure against it and switch
to the fallback price once it is spent.

## Why

A source of truth that declares a cap cannot state the current price without
knowing whether the cap is spent. Under DR-020 the published price past the
cap was wrong for every user who had not found the tickbox.

## Rejected

- **Keep the tickbox, default it on.** Still a choice that, made wrongly,
  publishes a wrong price.

## Consequences

Counting needs a meter, which is one reason the import energy sensor is
mandatory (DR-030). What is published from counting is an estimate (DR-003).

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `allowance.py:45` - `def apply` - the fallback once the cap is spent
- `coordinator.py:250` - `counting_allowance` - follows from the declaration, not a tickbox
- `plan.py:244` - `has_allowance` - the declaration
