# DR-032: `plan.merged()` is the only way to write a stored object

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.6 (P31, P32) |
| Origin | Standing rule 15 |
| Related | DR-031 |

## Decision

`plan.py` owns the shape of every stored object. A screen passes only the
fields it asked the user about to `plan.merged()`; everything else comes from
the record already stored, and the key set comes from the model.

## Why

Nine screens each hand-built their own dictionary for the same objects, so
the shape of a rate existed in ten places and the nine copies went stale.
That is how DR-031 was broken.

## Rejected

- **Fix each screen's dictionary.** The tenth screen repeats the fault.

## Consequences

Nothing can be dropped, because every key the model reads is written;
nothing invented, because keys the model does not read are not; and nothing
untouched is rewritten, because a stored value passes through exactly as
stored. A new screen does not get a tenth hand-built dictionary.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:998` - `def merged` - the single writer
- `config_flow.py:1965` - `merged(Rate` - a rate edit in Configure
- `config_flow.py:2230` - `merged(DayPattern` - a timetable edit
