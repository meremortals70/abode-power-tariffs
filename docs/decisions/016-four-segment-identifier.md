# DR-016: A rate's identifier is four segments: plan, timetable, side, name

| | |
|---|---|
| Status | Accepted |
| Since | Two segments from P4; four by 0.9.10 (2026-08-27) |
| Origin | Standing rule 10; `ARCHITECTURE-GAPS.md` items 1 and 4 |
| Related | DR-013, DR-014, DR-017, DR-023 |

## Decision

A rate is its plan, its timetable, its side and its name, published as
`plan.timetable.import.peak` or `plan.timetable.export.peak`. Always four
segments, on both sides, never inferred from the absence of a segment.
Anything keyed on a bare name, or on fewer than four segments, is a bug.

## Why

Two timetables can each have a Peak. Keying on the bare name in `strip.py`
once turned two timetables into one colour. Once export rates could carry a
ledger, an import rate and an export rate of the same name on the same
timetable had to stop sharing a key. And with rates nested inside timetables
(DR-013), the plan is the one piece of context that lives outside a rate
however it is reached.

## Rejected

- **Two segments, `timetable.rate`.** Rejected explicitly: an import and an
  export rate of the same name on one timetable collide.
- **Three segments with the side implied for import.** A missing segment
  cannot be told apart from a default.

## Consequences

Ledgers, the tariff select and the constraint attributes all use the full
identifier. What a human reads can be shorter (DR-017), but the identifier is
always available beside it.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.** The identifier
is built in one place and used for ledgers, the select write-back and the
tariffs of the utility meter Configure creates.

- `plan.py:122` - `qualified_name` - always four segments
- `coordinator.py:323` - `def ledger` - keyed on the identifier
- `coordinator.py:1012` - `qualified_name` - the select write-back
- `config_flow.py:3036` - `rate_id(self.config_entry.title` - the meter's tariffs
