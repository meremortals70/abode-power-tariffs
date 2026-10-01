# DR-012: A rate is scoped to its timetable by a pointer field

| | |
|---|---|
| Status | Superseded by DR-013 |
| Since | P4 for import rates; 0.8.10 (P37) for export rates |
| Origin | P4; P37 Part A; finding A1c |
| Related | DR-013, DR-016, DR-039 |

## Decision

Rates are held in one plan-wide list per side. Each `Rate` and `ExportRate`
carries a `timetable: str | None` field naming the timetable it belongs to.
`None` means a rate stored before scoping existed, resolved by a
same-name-anywhere fallback.

## Why

Before P4, two timetables could not each have a Peak: a rate's name was its
identity across the whole plan, so users prefixed names with the timetable by
hand. A pointer field gave each rate a timetable without moving where rates
were stored. P37 gave export rates the same field, because they still had the
pre-P4 shape.

## Rejected

- **Keep prefixing names by hand.** The prefix is a convention nothing
  enforces, and it leaks into every published name.

## Consequences

Every lookup needed the scoped-then-unscoped precedence, and every screen had
to remember to pass the timetable. A Configure picker keyed on the bare name
was found in session eleven; checking it showed the fault was the storage
shape, not the picker, and the same flaw was on the import side.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Superseded.** Removed by DR-013;
neither the `timetable` field nor the unscoped fallback remains.
