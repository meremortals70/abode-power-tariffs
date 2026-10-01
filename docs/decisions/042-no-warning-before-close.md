# DR-042: There is no warning before the dialog closes

| | |
|---|---|
| Status | Accepted |
| Since | Settled |
| Origin | Settled |
| Related | DR-033, DR-040 |

## Decision

The config dialog does not warn before it closes.

## Why

It is not possible. `closeDialog` in the frontend deletes the flow and only
then tells the backend; `FlowHandler.async_remove()` is a notification, not a
veto.

## Rejected

- **A draft store** to recover an abandoned flow. Designed and rejected as
  more machinery than the problem deserves.

## Consequences

The mitigations are a short linear setup (DR-040) and Configure committing
every step as it leaves (DR-033).

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `config_flow.py:1612` - `def guarded` - the Configure mitigation
