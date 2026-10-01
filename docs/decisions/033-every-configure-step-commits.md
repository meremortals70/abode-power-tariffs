# DR-033: Every Configure step commits as it leaves

| | |
|---|---|
| Status | Accepted |
| Since | By 0.9.10 (2026-08-27), session twelve |
| Origin | Live testing, session twelve |
| Related | DR-031, DR-042 |

## Decision

Every Configure step writes the working copy back to the config entry on its
way out, whether it is moving on, showing a validation error, or anything
else. An exception in any step shows the failure instead of an empty dialog.

## Why

Every step wrote to an in-memory copy, and only "Save and finish" on the top
menu wrote it back. Closing the dialog, or never noticing that button,
silently discarded everything typed. A typed entry has to be committed
everywhere in the flow, not just at one button several screens away.

## Rejected

- **Rely on "Save and finish".** Already shown to lose edits.
- **Warn before the dialog closes.** Not possible (DR-042).

## Consequences

A step that changed nothing writes back the state it already had. Setup is
not covered: a cancelled setup creates nothing, which is the mitigation
DR-040 relies on.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `config_flow.py:1612` - `def guarded` - wraps every Configure step
- `config_flow.py:1644` - `async_update_entry` - committed on the way out
