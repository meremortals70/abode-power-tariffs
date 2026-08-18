# Architecture review — status

**As at:** 19 August 2026, end of session two.
**Tree:** 0.8.2, config entry version 3.

Everything agreed across both sessions, and everything still open. Proposals are
numbered in the order they were discussed and never share a number space with
findings.

---

## Complete

### Session one — shipped as 0.8.0

| # | Decision | Outcome |
|---|---|---|
| P1 | Constraints could not be set during setup | Two rule lists on the rate form, setup and Configure; one filtered field definition |
| P2 | Forward intervals were wrong across daylight saving | `intervals.generate` walks real instants inside a wall-clock horizon |
| P3 | The options flow loses work when the dialog closes | **No change.** Home Assistant gives no pre-close hook; the short setup flow is the mitigation |
| P4 | Rate names were prefixed with the timetable | `Rate.timetable`, identity on the pair, `weekday.peak` computed where uniqueness is needed |
| P5 | Export period boundaries were never scheduled | Split boundaries, `next_export_change` sensor, wake at whichever is first |
| P6 | The forecast was rebuilt and written to the database constantly | Unrecorded attribute, series held within a slot, live figure out of the trace |
| P7 | Allowance counting sat inside the core | Opt-in behind its own Configure screen; cap and fallback always published |
| P8 | The test suite existed but was never committed | Committed, plus `mypy.ini`, `ATTRIBUTION.md`, pinned CI |

### Session two — shipped as 0.8.2

| # | Decision | Outcome |
|---|---|---|
| P9 | `next_boundary` returned an instant already in the past on the fall-back morning | `instants_at()` builds every real instant a wall-clock time names on a date; the choice between candidates is made in UTC rather than on clock digits |
| P10 | One scheduled wake was load-bearing — a wrong instant left the sensors stale for hours with no backstop | `async_track_time_change(second=0)` recomputes every minute. Boundaries are whole minutes, so a tick lands on each one exactly; `resolve_at` works forward from the current instant and is already correct inside a repeated hour |
| P11 | The supply charge accumulator was an accounting function, and read as a meter reset to the Energy dashboard on any mid-day restart | `SupplyChargeCostSensor`, `SupplyChargeEnergySensor`, the `supply_charge_today` state field, the Configure tickbox and its strings all removed. `SupplyChargeSensor` stays — the charge as a declared figure |
| P13 | The allowance zeroed on the calendar but counted per rate, so a rate occurring twice in a day inherited the first occurrence's usage | Scoped to the slot occurrence: reset on entry, restore qualified by the slot it was recorded in, midnight handler deleted entirely. `daily_allowance_kwh` renamed `rate_allowance_kwh` with a config entry version 3 migration |

### Design rules settled or added

- **The allowance belongs to the time slot, not the day.** Each occurrence of a
  capped slot has its own count. Nothing carries between slots, days or billing
  cycles — that arithmetic is the consumer's.
- **The supply charge is declared, never accumulated.** The Energy dashboard's
  missing daily-charge field is not this component's problem to solve. A user
  wanting a total builds a `utility_meter` in their own config entry.
- **Counting stays opt-in** (P7 reaffirmed, not reopened). An allowance changes
  which rate applies, so counting it feeds a decision; a supply charge total
  feeds nothing.

---

## To do

### Agreed in principle, not designed

| # | Item | State |
|---|---|---|
| P12 | Billing cycle as a declared fact — publish cycle start and end so a user can build a reminder card, compute nothing | **Parked pending owner research.** Likely a day-of-month anchor, giving cycles of 28–31 days. Open questions: how the cycle is expressed, and whether days-remaining is published or left to the consumer |

### Register — found, not yet proposed

- `demand_period` and `demand_rate_per_kw_month` are collected from the user and
  published nowhere. `demand_period` belongs on the interval and as a binary
  sensor. Calculating the charge is out of scope and should stay out.
- Export rates are still prefixed with the timetable name, the way import rates
  were before P4. Now inconsistent with the import side.
- `Rate.components` is stored, never written, never read.
- `Rate.export_price` is vestigial — export is fully modelled by `ExportRate`.
  Still round-trips through storage and is printed in two places.
- `PREVIOUS_STEP` and `CONF_GO_BACK` are dead.
- Every form renders **Submit** because `last_step` is never set on any
  `async_show_form` call. Passing `last_step=False` renders **Next**.
- The setup flow has no way to correct or remove an entry once submitted.
- `ConstraintBinarySensor._slug` maps `no grid import` and `no_grid_import` to
  the same unique id. Constraints are free text, so this is reachable.
- Removing a constraint from every rate orphans its entity in the registry.
- `fallback_rate` is not offered when a timetable has only one rate, so a
  single-rate capped plan cannot be made valid.
- `strings.json` carries two step keys nothing uses: `export_periods_pick`,
  `init`.
- `prices_include_gst` and `gst_percent` are stored and displayed but never
  applied to any published price.

### New findings from session two — three fixed while packaging

- **The tree was not CI-green at `de0cce4`.** Pinned ruff 0.16.3 reported one
  RUF100 (`intervals.py`, an unused `noqa: PLR0913`) and two RUF012 in
  `tests/test_runtime.py`, against the untouched commit, despite the previous
  notes claiming full CI green. **Fixed** — `ruff check` now passes.
- **`.coveragerc` did not exist.** The documented coverage command passes
  `--rcfile=.coveragerc`; coverage silently ignores a missing rcfile, so the
  gate was measuring the test files as well as the component and reporting an
  inflated 96%. **Fixed** — the file now exists, scoped to the component with
  branch coverage on. The real figure is 91% line and branch.
- **There was no CI workflow.** P8 recorded "pinned CI" but `.github/` was
  absent, so nothing ever ran the gates automatically. **Fixed** —
  `.github/workflows/ci.yml` runs the five documented commands plus hassfest
  and the HACS action.
- **`__pycache__` was committed to the repository**, for both the component and
  the tests. **Fixed** — untracked, and a `.gitignore` added.
- **A period cannot wrap past midnight.** `Period.contains` is
  `start <= minutes < end`, so a slot running 22:00–02:00 must be expressed as
  two periods. Under the slot rule those are two slots with an allowance each.
  Noted as a consequence, not a defect — changing it would be a change to the
  period model.
- **The two removed supply charge entities will linger in the entity registry**
  as unavailable. Deliberately not cleaned up: writing to the registry sits
  close to rule 1, and the owner will delete them by hand.

### Before Home Assistant core

- The test suite needs rewriting against `pytest-homeassistant-custom-component`;
  core does not accept hand-rolled stubs.
- `version` must come out of `manifest.json` — custom-integration only.
- Brands must be submitted to `home-assistant/brands`; the local `brand/`
  directory does not satisfy it, which is why `brands` is the one Bronze rule
  still marked `todo`.
- `quality_scale.yaml` tracks all 54 rules and must stay honest.
