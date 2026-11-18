> Project memory for Abode Power Tariffs. Update at the end of each session.

## Current objective

Builds 1–9 were released as v0.9.13 on 18 Nov 2026. All four CI jobs passed
on the release commit `b83173f`; issues #1–#9 were closed with release links.
The tracked tree is clean apart from two pre-existing untracked archive folders.
The remaining confirmed defects below are not scheduled.

## Active work

Released in v0.9.13, commit `b83173f`:

| Build | What |
| ----- | ---- |
| 1 | A completed demand interval is closed when its rate leaves force |
| 2 | Five correctness fixes: holiday-aware schedule cache, holiday gap only when a timetable uses holidays, future plan is not expired, `TOTAL` state class on resettable charges, export demand gated on the export meter |
| 3 | Meter unit chosen per meter (Wh/kWh/MWh, default kWh), readings scaled to kWh, read-time mismatch warning and repair, advisory only |
| 4 | A reading that straddles a rate boundary is split by real elapsed time, each stretch credited to the rate in force just before the boundary; a late tail raises the peak of the interval it belongs to (#10) |
| 5 | The block ("single rate") setup screens declare the cap as a monthly allowance, so it runs for the billing cycle instead of refilling at midnight |
| 6 | A flat all-day feed-in cap is counted: the timetable's own declaration has a ledger identity, a declared period, a count and a fallback price, published on the export price sensor; the block plan declares it monthly |
| 7 | Startup never blocks on the meter: one read per counted meter on the entry-setup path, an unreadable one retried in a background task (same three attempts, five seconds apart), cancelled on unload (#5) |
| 8 | The instantaneous demand interval is withdrawn: 15/30/60 minutes only, a stored zero read as 30 minutes with a Configure warning and a repair saying so (#1) |
| 9 | Documentation drift: 98 decision-record anchors re-pointed (142 now check clean), 49 conformance lines and the index updated, "seven" → "eight" pure modules with `accounting.py` added to the tree and to CI mypy, meter-unit passage in `README.md` and `docs/architecture.md`, DR-028 restored with a new DR-048 for the withdrawal, and the four test files reformatted |

## Recently completed

| Date | What |
| ---- | ---- |
| 18 Nov 2026 | Released v0.9.13: tag pushed, GitHub release published, issues #1–#9 closed; all four CI jobs green on `b83173f` |
| 18 Nov 2026 | Removed `homeassistant` from `manifest.json` after reading hassfest's current schema: it is no longer a valid key for a custom integration, and hacs.json already declares the 2025.2.0 minimum |
| 18 Nov 2026 | Built and verified Build 9 (the last register entry); full CI green, `ruff format` included — the four pre-existing failures are fixed |
| 18 Nov 2026 | Opened nine GitHub issues, #1–#9, one per build item, each with what was wrong, what changed, files and verification |
| 18 Nov 2026 | Built and verified Build 8 (register entry 1, reclassified); full CI green apart from the same four pre-existing `ruff format` failures |
| 18 Nov 2026 | Built and verified Build 7 (register entry 5); full CI green apart from the same four pre-existing `ruff format` failures |
| 18 Nov 2026 | Built and verified Build 6 (register entry 9); full CI green apart from the same four pre-existing `ruff format` failures |
| 18 Nov 2026 | Built and verified Build 5; full CI green apart from the same four pre-existing `ruff format` failures |
| 18 Nov 2026 | Built and verified Build 4; full CI green apart from the same four pre-existing `ruff format` failures |
| 9 Nov 2026 | Released 0.9.12 (commit `13cf64a`): runtime, setup and validation hardening |
| 17 Nov 2026 | Built and verified Builds 1–3 above; full CI green apart from four pre-existing `ruff format` failures |
| 19 Aug 2026 | Shipped 0.8.4: one-table plan render, billing cycle day, allowance on rate form, migration removed |
| 19 Aug 2026 | Shipped 0.8.2: DST boundary fixes, slot-scoped allowances, supply-charge accumulator removed |
| Earlier | Shipped 0.8.0: constraints in setup, DST forward intervals, export boundaries, forecast as unrecorded attribute |

## Decisions

| Date | Decision | Why |
| ---- | -------- | --- |
| 18 Nov 2026 | The index column reading "At 0.9.11 RC2" becomes "At 0.9.12 + Builds 1-8" and the header says `check_anchors.py` reports 142 anchors, none missed | The owner has not named a release version, so the conformance line names the build the records were checked against rather than inventing a version |
| 18 Nov 2026 | DR-023 is marked **Partly**, not **Conforms** | The record says one ledger per rate; the flat all-day feed-in declaration is not a rate and now has a ledger under `plan.timetable.export`. Rewriting the frozen Decision is forbidden, so the gap is marked and the successor record is on the fix list |
| 18 Nov 2026 | DR-048 is a new record for the withdrawal, not an edit to DR-028 | Decision, Why, Rejected and Consequences are frozen once accepted. DR-028 keeps its original "or instantaneous" wording and is marked superseded in part; the withdrawal and its evidence live in DR-048 |
| 18 Nov 2026 | An anchor is re-pointed by reading the record line against the candidate source lines, not by taking the nearest match | `check_anchors.py` matches a symbol within ±2 lines of the cited range, so a nearest-match rewrite can pass the check and still point at the wrong occurrence |
| 18 Nov 2026 | The owner named v0.9.13; the assistant did not choose a version | Standing release rule: propose the number, the owner sets it |
| 18 Nov 2026 | The anchor checker went into CI as its own gate | A record whose cited line no longer holds its symbol is a false statement about the code; the 98-miss drift should not be possible again |
| 18 Nov 2026 | The instantaneous demand interval is withdrawn; `DEMAND_INTERVALS` is 15/30/60 | Owner challenge, and it was right: no tariff bills demand from a single sample. Every one bills an average over a metering interval — 30 minutes in Australia, 15 in the US, half-hourly for UK capacity — because a sample of one instant is an artefact of polling and one motor start would set a monthly charge |
| 18 Nov 2026 | A stored `demand_interval: 0` is read as 30 minutes and reported twice: Configure's "Worth checking" and a repair (`instantaneous_demand`) | The model already coerced it; silent coercion changes the meaning of a stored value without telling the user, which is the truth failure the whole project is built against. Saving the rate through Configure rewrites 0 as what the form offers, and the repair clears on the next start |
| 18 Nov 2026 | The repair is cleared unconditionally at setup, not only when one was raised | Nothing else would ever withdraw it: the only opportunity is a later start, and a reload creates a new coordinator with no memory of having raised it |
| 18 Nov 2026 | The startup meter read is one non-blocking attempt; an unreadable meter is retried in a background task, never on the entry-setup path | The plan, its boundaries and its forecasts do not depend on the meter, and on a reload the meter is already publishing; only a cold-start race ever needed the waiting |
| 18 Nov 2026 | The retry only fills an *empty* baseline (`_set_meter_baseline`); a state change that arrives first keeps its reading | A state change can beat the retry, and `_accumulate_energy` records its reading as the baseline; overwriting it would drop the energy drawn in between without crediting it to anything |
| 18 Nov 2026 | Giving up on the last retry still opens the gap, with the side named in the reason | Deferring the wait must not hide a genuine, ongoing unreadable meter |
| 18 Nov 2026 | A flat all-day feed-in declaration is identified by `plan.timetable.export` — three segments, no rate name — and is counted under that key | There is no rate object on that shape, so nothing existed for a ledger to be keyed on; `slug` never leaves a separator inside a segment, so a three-segment key cannot collide with a four-segment rate identifier |
| 18 Nov 2026 | That declaration carries its own period (`export_allowance_period` on the timetable), defaulting to `slot`; the block-plan setup screens declare `month` | Same reason the import cap got one: the household has to be able to say whether the retailer counts it per day or per cycle, and the block screen promises "the rest of the billing period" |
| 18 Nov 2026 | A named `ExportRate` keeps its hard-coded `slot` cap in this build | Not part of the approved scope; offered separately |
| 18 Nov 2026 | The block plan's cap is declared monthly by the setup screens; Configure keeps both choices | The screens promise "the rest of the billing period", setup asks the minimum, and the model's default of `slot` on an all-day period means one occurrence a day |
| 18 Nov 2026 | A reading that straddles a rate boundary is split by real elapsed time, not credited to the rate in force when it arrived | The meter says how much, never when; even attribution is the only estimate available, and the alternative over-prices the evening peak and under-counts a cap |
| 17 Nov 2026 | Meter unit is chosen by the user and checked at read time; a mismatch warns and raises a repair, it does not refuse the meter | Owner instruction; the chosen unit is what the reading means, and the user gets a chance to correct it |
| 0.8.4 | No config entry migration | `manifest.json` version is the build number only |
| 0.8.2 | Allowance belongs to the slot occurrence | Owner rule; prevents cross-slot carry |
| 0.8.0 | Pure / HA layer split | Domain logic must be testable without Home Assistant installed |

## Register

No build is scheduled. Builds 1–9 are done; the items below are the confirmed
defects still open in the code.

Still open in the code, not yet scheduled:

- `intervals.generate` starts the series in the wrong pass of a repeated hour.
- `coordinator.forward_intervals` cannot tell the two passes apart; its cache
  key is wall-clock only.
- `ConstraintBinarySensor._slug` collapses `no_grid_import` and
  `no-grid-import` to one unique id.
- Removing a constraint from every rate orphans its entity in the registry.
- Setup has no way to correct or remove an entry once submitted.
- Every form renders **Submit** because `last_step` is never set.
- GST is stored and displayed but never applied to prices (DR-046).

Findings, not yet proposed:

- DR-016's Origin reads "Standing rule 10" for the four-segment identifier and
  DR-019's reads "Standing rule 9" for constraints. Under the current numbering
  those are 9 and 8. Either a rule was renumbered after those records were
  written, or the two origins are swapped. Not changed: the record's own note
  says the rule numbers are the set kept during development, so the historical
  number may be correct as written.
- `check_anchors.py` is not in CI, so anchors can rot again exactly as they did
  between 0.9.11 RC2 and Build 9.
- Four decisions Builds 3–8 made have no record yet: meter units, boundary
  attribution, the flat all-day feed-in cap, and the startup meter deferral.
  They are listed in `docs/decisions/README.md` under "Not yet recorded".

Deliberate limits of Build 4, so they are not re-filed as defects:

- The split is at rate boundaries only. A stretch spanning several demand
  intervals credits the interval that contains its end.
- `next_boundary` walks at most three days and one reading is split at most 256
  boundaries; a reading older or coarser than that is credited where it
  arrived. A meter reporting hours apart already carries this error.
- The first reading after startup has no earlier reading to split against, so
  its whole delta is credited to the rate in force when it arrives.

Deliberate limits of Build 6, so they are not re-filed as defects:

- A reading that straddles midnight under a daily flat feed-in cap is credited
  wholly to the day it arrives: the flat shape has no midnight boundary to
  split at.
- A named `ExportRate` still has a hard-coded `slot` cap and no
  `allowance_period` of its own.

Closed by Builds 1–6 and no longer in the register:

- A flat all-day feed-in cap was never counted: there was no ledger identity,
  so neither the count nor the fallback price ever moved — on the block plan's
  export side or on any timetable ticking "one price all day" with a cap.

- The last demand interval of a window was discarded when its rate left force.
- Energy was credited to the outgoing slot and then thrown away.
- A reading either side of a boundary was credited wholly to the rate that
  happened to be in force when it arrived (#10).
- A meter reading covering the tail of an interval that had already closed was
  either dropped or added to the interval opening after it.
- A block plan's cap refilled at midnight instead of running for the billing
  cycle (#4).
- `today_schedule` served a stale timetable after a holiday flip.
- A holiday-sensor blip flagged a plan that has no holiday timetable.
- A plan that has not started was reported as expired and priced.
- `supply_charge_today` / `supply_charge_cycle` were `TOTAL_INCREASING`.
- Export demand was gated on the import meter.
- Meter units were never read.

Corrected register entries — these were wrong, not fixed:

- `demand_period` and `demand_rate_per_kw_month` are published.
- Export rates use the same four-segment qualified name as import.
- `Rate.components` and `Rate.export_price` do not exist in the model.
- `PREVIOUS_STEP` and `CONF_GO_BACK` are gone.
- `export_periods_pick` is a live menu entry and step.
- The one-rate fallback case is handled by `custom_value=True`.
- `accounting.py` is an eighth pure module; the docs list seven.
- "Instantaneous demand never produces a peak (#1)" was not a defect in the
  code but in the offered option: no tariff bills demand from a single
  sample. Withdrawn in Build 8 rather than measured. The exported review file
  `docs/claude-source/abode-power-tariffs-export.md:119` still carries a test
  asserting that fiction; it is an archive, not a live test.

## Blockers

None. Push works through `git push https://x-access-token:${GITHUB_TOKEN}@github.com/meremortals70/abode-power-tariffs.git` - the old note claiming a tool-level block was wrong.

## Glossary

| Term | Meaning |
| ---- | ------- |
| Plan | The user's complete tariff description |
| Timetable | A set of day patterns (weekday, weekend, holiday, season) |
| Rate | A price + rules identified by timetable + name (e.g. `weekday.peak`) |
| Period | A time span within a timetable that a rate applies |
| Allowance | A kWh cap within a slot; counted whenever a meter is nominated |
| Constraint | A declaration such as `no_grid_import`; not enforced by this component |
| Pure module | One of `const/plan/validate/intervals/allowance/accounting/strip/serialise`; no HA imports |
