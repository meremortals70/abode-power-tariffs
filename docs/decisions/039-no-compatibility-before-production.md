# DR-039: Nothing is kept for compatibility before production

| | |
|---|---|
| Status | Accepted; supersedes DR-038 |
| Since | Session eleven (`CONF_COUNT_ALLOWANCE`); applied throughout session twelve |
| Origin | The owner's instruction, sessions eleven and twelve |
| Related | DR-013, DR-037, DR-038 |

## Decision

Until the integration is in production, an architectural change is made
without backward compatibility. Old stored shapes, sentinels and fallbacks
are removed, not migrated and not carried.

## Why

Nothing is in production yet, so the compatibility reasoning behind DR-037
and DR-038 protects data that does not exist. Carrying the old shapes kept
fallbacks alive in every lookup and kept dead keys in the tree.

## Rejected

- **Keep every old shape working.** Cost on every lookup, for no installs.

## Consequences

Entity unique ids may change with a shape change. This record has to be
revisited at the first public release: from then on, DR-037 applies with no
exception, and a shape change has to keep old plans readable.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** The `timetable=None`
sentinel, the unscoped fallback and the dead-code items are gone.

- `plan.py:181-182` - `gone rather than` - the old shape removed, not migrated
