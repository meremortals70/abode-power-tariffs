# DR-031: An edit changes only what was edited

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.6 (P31, P32) |
| Origin | Standing rule 14; findings A1a, A1b, A2, A3 |
| Related | DR-032, DR-033 |

## Decision

Configure is menu-driven: the user picks one thing to change, and nothing
else about the plan may be affected. An edit screen writes the fields it owns
onto the record already stored and touches nothing else. Creation may omit a
field, because absent at creation means not declared, which is true. An edit
may not.

## Why

Screens rebuilt their records from the fields they showed. Anything they did
not show was deleted by a user who came to change something else: renaming a
timetable deleted the export allowance declared beside it.

## Rejected

- **Rebuild the record from the form.** Every field added later has to be
  remembered on every screen that writes the object; it was not.

## Consequences

The mechanism is DR-032. A field stored and never shown on any screen still
survives every edit; the declaration tests prove it with exactly such a
field.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `tests/test_declaration.py:279` - `test_changing_a_timetables_feed_in_price_keeps_its_allowance` - the original fault
- `tests/test_declaration.py:297` - `test_changing_a_rates_price_keeps_the_rest_of_the_rate` - a rate edit
- `tests/test_declaration.py:609` - `test_an_edited_rate_has_every_key` - nothing dropped
