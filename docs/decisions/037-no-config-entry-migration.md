# DR-037: No config entry migration and no config entry version

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.4 |
| Origin | Standing rule 13; the owner's instruction, session three |
| Related | DR-038, DR-039 |

## Decision

There is no config entry migration and no config entry version. The version
in `manifest.json` is the build number and nothing else. A stored key that
turns out to be misnamed keeps its name and gains a comment.

## Why

A migration shipped at 0.8.3 renamed stored rates to scope them to their
timetable. Renaming a rate renames its entities and breaks any `utility_meter`
the user built on it, which lives in a config entry this integration does not
own. The migration was removed in full at 0.8.4: the steps, the version
counters and their tests.

## Rejected

- **Keep the mechanism for later.** Bumping a config entry version without a
  migration makes every existing install refuse to load with "Migration
  handler not found".
- **Rename misnamed keys.** Needs the migration this record removes.

## Consequences

A shape change before production is made without compatibility (DR-039).
Misnamed keys stay: `gst_percent`, `prices_include_gst` and
`demand_rate_per_kw_month` each carry their correction in a comment.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** No `VERSION` and no
`async_migrate_entry` anywhere in the integration.

- `plan.py:202` - `A stored key cannot be renamed` - a misnamed key's comment
- `manifest.json:13` - `version` - the build number only
