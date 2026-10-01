# DR-041: There is no back button

| | |
|---|---|
| Status | Accepted |
| Since | Settled; the abandoned attempt's leftovers removed by 0.9.10 |
| Origin | Settled |
| Related | DR-040 |

## Decision

The flows have no back button.

## Why

Home Assistant has no back mechanism in `data_entry_flow` and no back control
in the dialog. The only workarounds are a field inside the form or
restructuring around menus.

## Rejected

- **A "go back" field on each form.** Tried; its constants
  (`PREVIOUS_STEP`, `CONF_GO_BACK`, `SUBMIT_BACK`) survived as dead code and
  were removed.
- **Restructure setup around menus.** See DR-040.

## Consequences

Configure's menus are how a user gets back to something to change it.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** None of the three
constants remain.
