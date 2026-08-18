# Project notes

**Written:** 18 August 2026, at the end of a review-and-build session.
**State of the tree:** version 0.8.0. Full CI green — ruff, ruff format, mypy
strict on the seven pure modules, 265 tests, 91% line and branch coverage.

The architecture review is **not finished**. P1–P8 below are closed and built;
section 7 is the remaining backlog and is where a new session should pick up.

This exists so the next session can pick up without re-deriving what was already
decided. Read sections 1 and 2 before proposing anything.

---

## 1. What this component is, and what it refuses to be

A canonical source of truth for a household's electricity tariff plan. The user
describes a complex plan once; the component publishes what energy costs right
now, what it will cost over the next N hours, which rate is in force and what
rules the user declared against it.

It was separated out of a control project deliberately so the tariff model is
useful to Home Assistant generally rather than to one automation.

**It reports. It does not command.** The only thing it writes anywhere is a
`utility_meter` tariff select the user has explicitly nominated, and that is
maintaining a projection of state rather than making a decision.

**It is not an accounting system.** See rule 6 below.

---

## 2. Standing rules

These came from the project owner during the session and are not up for
re-litigation. A proposal that breaks one of them is wrong.

**1. Everything is reported in local time.** Always, with the offset, including
the evcc forecast attribute. Nothing is published in UTC. The component may walk
time in UTC internally — it must, to be correct — but nothing leaves it that way.

**2. The plan is defined in local wall-clock time and does not change because
the clocks did.** A peak period declared 16:00–21:00 is 16:00–21:00 on both
sides of a daylight-saving transition. The backend accounts for the transition;
the plan never bends to it.

**3. A day is 23, 24 or 25 hours.** On the day the clocks go forward, a rate
covering 02:00–03:00 is in force for no time at all. On the day they go back it
is in force for two hours. That is the correct answer, not a bug to be smoothed
over. "24 hours from 18:00" means 18:00 tomorrow, whatever that costs in real
time.

**4. Import and export are separate config flows.** Separate rates, separate
time periods, deliberately, so feed-in can have its own time structure. They
must stay separate. The one shortcut is the tickbox on the feed-in screen for a
single all-day export price, which ends the export branch on submission.

**5. Setup asks the minimum.** Everything else has a sensible default and is set
afterwards in Configure. That short flow is also the answer to losing work if
the dialog is closed — see section 5.

**6. Declaring a cap is not counting against it.** The plan always declares the
allowance and what is paid past it, and publishes both, so a consumer can apply
the rule itself. Whether this component keeps a running total is a separate
opt-in, framed to the user as an estimate that will not reconcile with a bill.

**7. Constraints are declarations, not instructions.** An enforceable rule means
the user declared it part of what the rate means, so another system should treat
it as a rule. It does not mean this component enforces anything. It never does.

**8. A rate is identified by its timetable and its name together.** A weekday
Peak and a weekend Peak are two rates, both called Peak. Published as
`weekday.peak`. Always qualified — at the point setup names the first
timetable's rates it cannot know whether a second is coming.

---

## 3. Working agreement

The session ran to rules the owner set after some early mess. Keep to them.

- **One proposal at a time.** Propose, discuss, close it, then open the next.
  Do not have two open.
- **Close cleanly.** Once a proposal is closed, do not bolt a caveat onto it.
  If something new comes up, it is a new numbered proposal.
- **A code issue found mid-conversation becomes a new numbered proposal**, not
  an aside in the current one.
- **Be literal. Do not infer.** UI behaviour and code behaviour are two
  different things and conflating them is where the time goes. If the owner
  makes an observation about a button label, that is what it is — not a request
  to change the commit semantics behind it.
- **Do not re-ask a question already answered.** If a standing rule settles it,
  apply the rule.
- **Plain English.** File and line references are useful; walls of them are not.

---

## 4. What was reviewed, and what came of it

An independent architecture review was commissioned before this session. It is
sound on architecture and should be kept, with one caveat: every citation in it
resolves to the repository README, so it reviewed the design as documented, not
the implementation. Four of its factual claims were inherited from a README that
was ahead of the code. Treat its judgements as good and its facts as unverified.

Its headline recommendation — an information/enforceable split on constraints —
was implemented, with two changes: the storage keeps the flat `constraints` list
as the union so nothing downstream breaks, and the service response gains a
sibling key rather than nesting, because the flat list is a published contract.

### Proposals closed this session

| # | What | Where it landed |
|---|---|---|
| P1 | Constraints could not be set during setup | Two rule lists on the rate form, setup and Configure; one filtered field definition |
| P2 | Forward intervals were wrong across daylight saving | `intervals.py` walks real instants inside a wall-clock horizon |
| P3 | Options flow loses work when the dialog closes | **No change.** Home Assistant gives no pre-close hook; the short setup flow is the mitigation |
| P4 | Rate names were prefixed with the timetable | `Rate.timetable`, identity on the pair, `weekday.peak` computed where uniqueness is needed |
| P5 | Export period boundaries were never scheduled | Split boundaries, `next_export_change` sensor, wake at whichever is first |
| P6 | Forecast rebuilt and written to the database constantly | Unrecorded attribute, series held within a slot, live figure out of the trace |
| P7 | Allowance counting sat inside the core | Opt-in behind its own Configure screen; cap and fallback always published |
| P8 | The test suite existed but was never committed | Committed, plus `mypy.ini`, `ATTRIBUTION.md`, pinned CI |
| P9 | The 24-hour bar could not be aligned with the clock | Removed. Configure shows the plan as text; the picture is a built-in `history-graph` card, documented in the README |

Every one of these has tests that fail against the code as it was before.

---

## 5. Things deliberately not done

**Warning the user before the config dialog closes.** Not possible.
`closeDialog` in the frontend deletes the flow and only then tells the backend;
`FlowHandler.async_remove()` is a notification, not a veto. A draft store was
designed and rejected as more machinery than the problem deserves.

**A back button.** Home Assistant has no back mechanism in `data_entry_flow` and
no back control in the dialog. The only workarounds are a field inside the form
or restructuring around menus. `PREVIOUS_STEP` and `CONF_GO_BACK` are the
remains of an attempt at the first; both are dead code.

**Menu-based setup.** Considered and rejected: menus give nothing on a cancel,
which was the problem being solved. Setup stays a linear flow.

**Any chart inside the config flow.** Settled, with the evidence, so nobody
spends another afternoon on it. `allow-svg` *is* passed on the options-flow menu
and on every form description — but the sanitiser's whitelist is
`svg[xmlns,width,height]`, `path[transform,stroke,d]`, `img[src]` and nothing
else. No `rect`, no `text`, no `fill`, no `stroke-width`, no `viewBox`. And
`img src` goes through the xss library's default check, which permits only
`http(s)://`, `/`, `#`, `mailto:` and `tel:` — so a data URI is stripped. HA had
to add an explicit exception to allow `data:` on links and there is no
equivalent for images.

That leaves three possibilities, all rejected:

- *Characters.* A coloured bar of emoji under a plain-character ruler cannot
  line up. Emoji width is not a fixed multiple of a monospace character and
  varies by font and platform; on Brave/Windows the bar drifted three hours
  against the ruler. No constant fixes it for everyone.
- *Inline SVG.* Achievable — bands as stroked paths scaled vertically, times as
  seven-segment digits drawn as paths, exact to the minute, no font dependency.
  It was built and demonstrated and it worked. Rejected as too much machinery in
  a config screen for what it buys.
- *A served image.* A URL starting with `/` passes the filter, so an HTTP view
  generating the SVG would work. Rejected: real work, and an odd thing for a
  core integration to do for a config screen.

The visual belongs in Lovelace. The rate sensor is an enum, so `history-graph`
draws it natively as a coloured timeline with a real time axis.

**Auto-migrating old rate names.** A plan from before P4 has rates named
`Weekday Peak` with no timetable. They keep those names and keep working.
Converting them would rename entities and break the link to any `utility_meter`
the user built, which lives in a config entry this component does not own.

---

## 6. Architecture a new session needs to know

**Seven pure modules** — `const`, `plan`, `validate`, `intervals`, `allowance`,
`strip`, `serialise` — import nothing from Home Assistant and hold every
decision. `tests/test_attributes.py` fails the build if one of them grows a
`homeassistant` import.

**They cannot be imported normally without Home Assistant installed.** Importing
anything from the package runs `__init__.py` first, and that imports Home
Assistant. `tests/_pure.py` sidesteps it by reading the seven files off disk into
a synthetic package with no `__init__`. Moving them into a subpackage with an
empty `__init__` would let the shim go; it was judged not worth the churn.

**The tests run against hand-written stubs** in `tests/_ha_stubs.py`, not against
Home Assistant. That is why they run in a third of a second with nothing
installed. It is also why they will need rewriting against
`pytest-homeassistant-custom-component` before any core submission — core does
not accept hand-rolled stubs. It is already listed in `requirements_test.txt`.

**Same-tzinfo datetime arithmetic is the trap in this codebase.** Python
subtracts and compares two aware datetimes that share a tzinfo object on the
wall clock, not in real time. That is what hid the daylight-saving bug for a
year, and a test written the obvious way cannot fail on it. Normalise to UTC
before comparing or subtracting. There are comments saying so at each site.

### Running it

```bash
pip install -r requirements_test.txt
ruff check custom_components tests
ruff format --check custom_components tests
mypy --config-file mypy.ini custom_components/abode_power_tariffs/{const,plan,validate,intervals,allowance,strip,serialise}.py
python3 -m unittest discover -s tests -p "test_*.py"
python3 -m coverage run --rcfile=.coveragerc -m unittest discover -s tests -p "test_*.py"
python3 -m coverage report --rcfile=.coveragerc --fail-under=90
```

`ruff format` matters because Home Assistant core runs it as a pre-commit hook
with no line-length override, so core is 88 characters. The tree is formatted.
Keep it that way or the eventual core submission is a large reformat.

---

## 7. The register — found, not yet proposed

Roughly in the order they are worth doing. None of these has been designed or
agreed; they are observations from reading the source at v0.7.2.

**Found after the 0.8.0 build, already fixed** — kept as warnings

- `strip.py` keyed colours and lookups by the bare rate name, so under P4's
  scoping two timetables collapsed onto one colour and the rate plan card
  reported every period missing. The lesson generalises: anything keyed by
  `rate.name` is suspect. Use `qualified_name`, or
  `plan.rate_by_name(name, timetable)`.
- The `allowance_counting` menu entry had no label in `menu_options`, so it
  rendered as a blank row. A new menu entry needs both a `step` block and a
  `menu_options` entry.

**Worth doing next**

- `next_boundary` compares wall-clock, not real time. It happens to return
  correct instants for plausible plans because of how ZoneInfo maps a
  nonexistent local time — it works by accident, and its docstring describes a
  mechanism that is not in the loop. Separately, `datetime.combine` always
  produces fold 0, so on the day the clocks go back the second pass through a
  repeated hour is never scheduled and a rate can be stale for up to an hour,
  once a year.
- `supply_charge_today` is 0 until the first midnight and `SupplyChargeCostSensor`
  never restores, so a mid-day restart reads as a meter reset to the Energy
  dashboard.
- Allowance restore has no date guard and does not refresh state. Restarting the
  morning after carries yesterday's usage until midnight.
- `demand_period` and `demand_rate_per_kw_month` are collected from the user and
  published nowhere. `demand_period` belongs on the interval and as a binary
  sensor. Calculating the charge is out of scope and should stay out.

**Smaller**

- Export rates are still prefixed with the timetable name, the way import rates
  were before P4. Now inconsistent with the import side. Probably the next
  thing worth doing.
- `Rate.components` is stored, never written, never read.
- `Rate.export_price` is vestigial — export is fully modelled by `ExportRate`.
  Still round-trips through storage and is still printed by
  `serialise.rates_to_csv`, always as zero.
- `PREVIOUS_STEP` and `CONF_GO_BACK` are dead.
- Every form renders **Submit** because `last_step` is never set on any
  `async_show_form` call. Passing `last_step=False` renders **Next**, which is
  what most of these screens actually mean.
- The setup flow has no way to correct or remove an entry once submitted. A
  mistyped price can only be fixed after setup completes, via Configure.
- `ConstraintBinarySensor._slug` maps `no grid import` and `no_grid_import` to
  the same unique id. Constraints are free text, so this is reachable.
- Removing a constraint from every rate orphans its entity in the registry.
- `fallback_rate` is not offered when a timetable has only one rate, so a
  single-rate capped plan cannot be made valid — the save is refused pointing at
  a field that is not on screen.
- `strings.json` carries two step keys nothing uses: `export_periods_pick`,
  `init`.
- `prices_include_gst` and `gst_percent` are stored and displayed but never
  applied to any published price.

---

## 8. Where this was heading

HACS first, Home Assistant core eventually. For core:

- The test suite needs rewriting against `pytest-homeassistant-custom-component`.
- `version` must come out of `manifest.json` — that key is custom-integration only.
- Brands must be submitted to `home-assistant/brands`; the local `brand/`
  directory does not satisfy it, which is why `brands` is the one Bronze rule
  still marked `todo`.
- `quality_scale.yaml` tracks all 54 rules and is honest as of this session.
  Keep it that way; it was not, and that is how the architecture review came to
  report a test suite that was not in the repository.
