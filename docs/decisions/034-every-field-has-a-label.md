# DR-034: Every field on a form has a label

| | |
|---|---|
| Status | Accepted |
| Since | After six fields shipped unnamed across two releases |
| Origin | Standing rule 16 |
| Related | DR-002 |

## Decision

Every field on every form has an entry in `strings.json`.
`translations/en.json` is identical to it, and every string change goes in
both.

## Why

A field with no entry renders as a box with no name against it. Nothing
raises and no behaviour changes, so nothing noticed: six fields shipped
unnamed across two releases.

## Rejected

- **Rely on review.** Missed six times.

## Consequences

Only the declaration tests can catch it, because the stub suite cannot see
the frontend's label lookup.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `tests/test_declaration.py:760` - `test_every_setup_field_is_named` - setup forms
- `tests/test_declaration.py:764` - `test_every_configure_field_is_named` - Configure forms
- `tests/test_attributes.py:251-255` - `read_bytes` - the two files compared byte for byte
