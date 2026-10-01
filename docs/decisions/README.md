# Decision records

Every significant decision behind this integration, one per file. The rest of
`docs/` explains how the integration behaves. This folder explains why it
behaves that way, including the options that lost.

## How a record is laid out

Each record has the same six parts, in this order ([template](TEMPLATE.md)):

1. **Header table** - status, the build that shipped it, where it came from,
   related records.
2. **Decision** - one or two plain sentences.
3. **Why** - the situation, defect or instruction that forced it.
4. **Rejected** - each alternative and the reason it lost.
5. **Consequences** - what it makes easier or harder.
6. **In the code** - file and line anchors, and whether the current build
   actually does what the record says.

## Rules

- **The decision is frozen.** Decision, Why, Rejected and Consequences are
  never edited once accepted. A changed decision is a new record, and the old
  record's status becomes "Superseded by DR-NNN".
- **Superseded records stay.** They keep the losing arguments. A decision
  that is reversed without its history tends to be made again.
- **"In the code" is the one living section.** Code moves; the record does
  not. After every build, each record's anchors are re-checked and its
  conformance line is updated to that build. A record whose code no longer
  matches is marked **Partly** or **Does not conform**, and the gap goes on the
  fix list. It is never quietly rewritten to match the code.
- **Anchors are checked by script, not by eye.** Each anchor names a file,
  a line or range, and a symbol that must appear there. Run
  `python3 docs/decisions/check_anchors.py` from the repository root.
- **Numbers are permanent.** Records are numbered in order of area, not date.
  A new record takes the next free number and joins its area in the index.
- **Origins.** "Standing rule N" is the numbered rule set kept during
  development. "P" numbers are design proposals, "A" numbers are
  architecture review findings, and "Gap N" is an item from the
  architecture-against-code review of session eleven (2026-08-23). Code
  comments that say "Gap #N" refer to the same list.

## Index

Anchors checked against 0.9.11 RC2, 2026-10-01.

### Origin

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [000](000-origin-and-purpose.md) | Origin and purpose | Accepted | The project brief | Conforms |

### Foundations

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [001](001-reports-never-commands.md) | It reports, it never commands | Accepted | Standing rule 1 | Conforms |
| [002](002-decisions-in-pure-modules.md) | Decisions live in pure modules | Accepted | Design | Conforms |
| [003](003-system-of-truth-not-accounting.md) | A system of truth, not an accounting system | Accepted | The fundamental precept | Conforms |
| [004](004-never-saved-inconsistent.md) | A plan can never be saved inconsistent | Accepted | The fundamental precept | Conforms |
| [005](005-one-service-one-plan.md) | One service holds one plan; archiving is `valid_to` | Accepted | Architecture definition, session eleven | Conforms |
| [006](006-a-gap-flags-the-cycle.md) | A gap flags the cycle incomplete and alerts at once | Accepted | P35 | Conforms |
| [007](007-expired-plan-is-a-truth-failure.md) | A plan run past `valid_to` with no successor is a truth failure | Accepted | Gap 6 | Conforms |

### Time

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [008](008-published-in-local-time.md) | Everything is published in local time, with the offset | Accepted | Standing rule 2 | Conforms |
| [009](009-wall-clock-plan.md) | The plan is wall-clock and does not bend to daylight saving | Accepted | Standing rule 3; P9, P25, P26 | Conforms |
| [010](010-a-day-is-23-24-or-25-hours.md) | A day is 23, 24 or 25 hours | Accepted | Standing rule 4 | Conforms |
| [011](011-billing-cycle-not-calendar-month.md) | Monthly figures run on the billing cycle, starting on day 1 to 28 | Accepted | P12; rule 11 revoked | Conforms |

### Plan shape

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [012](012-rate-scoped-by-pointer.md) | A rate is scoped to its timetable by a pointer field | Superseded by DR-013 | P4; P37; A1c | Superseded |
| [013](013-rates-nested-in-timetable.md) | Rates are nested inside the timetable that owns them | Accepted; supersedes DR-012 | Gap 1 | Conforms |
| [014](014-import-export-same-shape.md) | Import and export are separate flows of the same shape | Accepted | Standing rule 5; Gaps 2 and 3 | Conforms |
| [015](015-period-names-a-rate.md) | A period names a rate, carries no price, and the periods cover the day | Accepted | Design | Conforms |
| [016](016-four-segment-identifier.md) | A rate's identifier is four segments | Accepted | Standing rule 10; Gaps 1 and 4 | Conforms |
| [017](017-rate-sensor-short-name.md) | The rate sensor shows a short name; the identifier is an attribute | Accepted | Live testing, session twelve | Conforms |
| [018](018-unresolved-is-absent-not-zero.md) | A price that does not resolve is absent, never zero | Accepted | A4; P36 | Conforms |
| [019](019-constraints-declare-never-instruct.md) | Constraints declare, they never instruct | Accepted | Standing rule 9 | Conforms |

### Accumulation

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [020](020-declaring-a-cap-is-not-counting.md) | Declaring a cap is not counting against it | Superseded by DR-021 | Standing rule 7 | Superseded |
| [021](021-a-declared-cap-is-counted.md) | A declared cap is counted | Accepted; supersedes DR-020 | Rule 7 revoked, session seven | Conforms |
| [022](022-allowance-belongs-to-its-slot.md) | A timed allowance belongs to its slot; a monthly one to the cycle | Accepted | Standing rule 8; P13 | Conforms |
| [023](023-ledger-only-for-demand-or-allowance.md) | A ledger exists only for demand or an allowance, one per rate, either side | Accepted | A5; P35; Gap 4 | Conforms |
| [024](024-implausible-meter-jump-ignored.md) | An implausible meter jump is ignored | Accepted | Live testing, session twelve | Conforms |
| [025](025-fixed-charges-declared-only.md) | Fixed charges are declared, never accumulated | Superseded by DR-026 | Standing rule 11; P11 | Superseded |
| [026](026-supply-charge-lands-at-start-of-day.md) | The supply charge accumulates, landing in full at the start of each day | Accepted; supersedes DR-025 | Rule 11 revoked; Gap 5 | Conforms |
| [027](027-demand-rate-in-cents.md) | The demand rate is entered in cents, like every other price | Accepted | Live testing, session twelve | Conforms |
| [028](028-demand-ratchet-not-proposed.md) | The demand ratchet is researched and not proposed | Accepted | P35 | Conforms |

### Configuration

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [029](029-setup-asks-the-minimum.md) | Setup asks the minimum | Superseded by DR-030 | Standing rule 6 | Superseded |
| [030](030-import-energy-sensor-mandatory.md) | The import energy sensor is mandatory | Accepted; supersedes DR-029 | Gap 7 | Conforms |
| [031](031-an-edit-changes-only-what-was-edited.md) | An edit changes only what was edited | Accepted | Standing rule 14; A1a, A1b, A2, A3 | Conforms |
| [032](032-merged-is-the-only-writer.md) | `plan.merged()` is the only way to write a stored object | Accepted | Standing rule 15 | Conforms |
| [033](033-every-configure-step-commits.md) | Every Configure step commits as it leaves | Accepted | Live testing, session twelve | Conforms |
| [034](034-every-field-has-a-label.md) | Every field on a form has a label | Accepted | Standing rule 16 | Conforms |
| [035](035-optional-concept-declared-by-tickbox.md) | An optional concept is declared by a tickbox, never by a value | Accepted | P27; P36 | Conforms |
| [036](036-duplicate-asks-for-new-days.md) | Duplicating a timetable asks for new days and copies its rates | Accepted | A1c; P37 | Conforms |
| [037](037-no-config-entry-migration.md) | No config entry migration and no config entry version | Accepted | Standing rule 13 | Conforms |
| [038](038-old-rate-names-kept.md) | Old rate names are kept as stored | Superseded by DR-039 | Settled, session three | Superseded |
| [039](039-no-compatibility-before-production.md) | Nothing is kept for compatibility before production | Accepted; supersedes DR-038 | Instruction, sessions eleven and twelve | Conforms |
| [040](040-setup-is-linear.md) | Setup is a linear flow; Configure is menus | Accepted | Settled | Conforms |
| [041](041-no-back-button.md) | There is no back button | Accepted | Settled | Conforms |
| [042](042-no-warning-before-close.md) | There is no warning before the dialog closes | Accepted | Settled | Conforms |
| [043](043-no-chart-in-config-flow.md) | There is no chart in the config flow | Accepted | Settled | Conforms |

### Presentation

| DR | Decision | Status | Origin | At 0.9.11 RC2 |
|---|---|---|---|---|
| [044](044-plan-renders-as-one-table.md) | The plan renders as one table | Accepted | Standing rule 12; P23 | Conforms |
| [045](045-today-schedule-no-apostrophe.md) | "Today schedule", with no apostrophe | Accepted | Live testing, session twelve | Conforms |
| [046](046-tax-declared-never-applied.md) | Tax is declared for the record, and never applied | Accepted | Design; Gap 8 | Conforms |
| [047](047-utility-meter-not-owned.md) | The utility meter is a one-time convenience the plan does not own | Accepted | Design | Conforms |

## Fix list

Gaps between a record and the code at 0.9.11 RC2: none.
The six found against 0.9.10RC1 (DR-006, DR-007, DR-011, DR-016 with
DR-047, DR-019 and DR-034) were fixed in this build.

## Not yet recorded

Decisions visible in the code that do not have a record yet:

- The forward series assumes no future day is a public holiday, because the
  holiday sensor reports one day at a time (finding A6).
- `assert` guards values that came out of storage (finding A9).
- The services: `get_intervals`, `get_day_schedule` and `export_rates_csv`.
- The single-rate plan and the export toggle on the first setup screen (P28).
- The demand interval and demand basis declarations (P35), and demand
  charged per completed interval only.
- The rate plan card, rendered for transcription into an inverter's own
  tariff screen.
- The minute tick: the state is recomputed every minute rather than on one
  scheduled wake (P10).
