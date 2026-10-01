# DR-038: Old rate names are kept as stored

| | |
|---|---|
| Status | Superseded by DR-039 |
| Since | 0.8.4, when the migration was removed |
| Origin | Settled, session three |
| Related | DR-012, DR-037, DR-039 |

## Decision

A plan stored before rate identity was scoped has rates named, for example,
"Weekday Peak" with no timetable. They keep those names and keep working, by
a fallback that finds a rate by name anywhere when it has no timetable.

## Why

Converting them renames entities and breaks the link to any `utility_meter`
the user built, which this integration does not own. A migration that did
exactly this shipped at 0.8.3 and was removed at 0.8.4.

## Rejected

- **Convert old names.** The 0.8.3 migration; see DR-037.

## Consequences

The unscoped fallback had to be kept alive in every lookup.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Superseded.** The unscoped
fallback was removed with the pointer field (DR-013); old-shape plans are no
longer read.
