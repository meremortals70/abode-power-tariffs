> OpenCode project instructions for Abode Power Tariffs.
> These replace the previous `CLAUDE.md` working notes. They live in the repo so every session starts from the same place.

# Abode Power Tariffs — working notes for agents

Home Assistant custom integration. It is a canonical source of truth for a household's electricity tariff plan: the user describes the plan once, and the component publishes what energy costs now, what it will cost over the next N hours, which rate is in force, and what rules the user declared against it.

Python 3.13, Home Assistant custom component. Read `ARCHITECTURE.md` and `.opencode/memory/project.md` before proposing or changing anything. The detailed design document is `docs/architecture.md`; read the relevant section when changing control behaviour.

## How to work with the owner

- **Be patient and kind.** Do not assume prior knowledge of git, GitHub, Python or Home Assistant internals.
- **Always tell the truth.** If something is wrong, say so plainly.
- **Propose. Wait for an explicit go. Then build.** A question answered is not a go. Choosing between options you offered is not a go. Enthusiasm is not a go. The go is the owner saying build it.
- **One proposal open at a time.** Close it before opening the next.
- **Closed means closed.** Do not append a caveat, a related thought, or a "one more thing" to something already agreed. Anything new is a new proposal.
- **A finding is not a proposal.** Findings are bullets in `.opencode/memory/project.md`. Proposals are numbered in order.
- **Say what a proposal costs** before asking for a decision: files touched, rough size, what breaks, what has to migrate.
- **Show it, do not describe it.** If it renders, render it. If it is a change, show the diff. If it is output, run it and paste the output.
- **Never call something impossible without having tried it.** Say what you tried, what stopped you, and what you have not yet tried.
- **Be literal. Do not infer intent.** A remark about what a button says is a remark about what the button says. A question is a question, not a request.
- **Never re-ask what has been settled.** If a standing rule below answers it, apply the rule and say you applied it.
- **Keep it short.** Plain English. One screen unless depth is asked for.
- **When told you are wrong, correct it.** One sentence naming what was wrong, then the fix. Do not defend the reasoning that produced the error.

## Standing design rules

A proposal that breaks one of these is wrong.

1. **It reports. It never commands.** The only write is a `utility_meter` tariff select the user explicitly nominated.
2. **Everything is published in local time**, with the offset, including the evcc forecast attribute. Never UTC. Walk time in UTC internally where correctness demands it; nothing leaves that way.
3. **The plan is local wall-clock and does not bend to daylight saving.** A peak declared 16:00–21:00 is 16:00–21:00 on both sides of a transition.
4. **A day is 23, 24 or 25 hours.** A rate covering 02:00–03:00 is in force for no time on the short day and two hours on the long one. That is the answer, not a bug. "24 hours from 18:00" means 18:00 tomorrow.
5. **Import and export are separate flows** — separate rates, separate periods. The one shortcut is the all-day-price tickbox on the feed-in screen.
6. **Setup asks the minimum.** Everything else defaults and lives in Configure.
7. **Declaring a cap is not counting against it.** The plan always declares the allowance and fallback and publishes both. Counting is opt-in and is an estimate that will not reconcile with a bill.
8. **Constraints declare, they never instruct.** An enforceable rule means the user declared it part of what the rate means — not that anything is enforced.
9. **A rate is its timetable plus its name.** Published as `weekday.peak`. Always qualified; setup cannot know whether a second timetable is coming.
10. **Fixed charges are declared, never accumulated.** Supply charge, monthly charge and billing cycle day are published exactly as entered. No totals, no cycle computed, no days remaining. The cycle starts on the same day every month, so the day must be 1 to 28.
11. **The allowance belongs to the time slot, not the day.** Each occurrence of a capped slot has its own count. Nothing carries between slots, days or billing cycles.
12. **The plan renders as one table.** Time span, name as typed, published identifier, price. No second block restating what the first already said.
13. **There is no config entry migration and no config entry version.** The version in `manifest.json` is the build number and nothing else. Do not reintroduce either.

## Engineering rules

- **Before changing the shape or identity of anything, find everything that depends on it.** Grep for it, list what you found, and put that list in the proposal.
- **Every change ships with a test that fails against the previous code.** Prove it — stash the change, run the new tests, show the failures.
- **Verify against source, never memory.** Read the Home Assistant code, the frontend, the sanitiser, whatever governs the question. Say what you read.
- **Run the full CI before handing anything over.** ruff, ruff format, mypy strict on the eight pure modules, the whole suite, coverage at or above 90%.
- **Keep the eight pure modules free of Home Assistant imports:** `const`, `plan`, `validate`, `intervals`, `allowance`, `accounting`, `strip`, `serialise`. `tests/test_attributes.py` fails if one of them imports `homeassistant`.

## Releasing

- **Every build handed over is a release and gets its own version.** If the owner has installed the previous one, the next is a bump.
- **Say what changed since the build the owner is running**, not since the last thing you did.
- **Do not set the version yourself.** Propose the number; the owner sets it.
- `git push` is blocked at the OpenCode tool level. Ask the owner to push or approve it.

## Traps in this codebase

- **Same-tzinfo datetime arithmetic.** Python compares and subtracts two aware datetimes sharing a tzinfo on the *wall clock*, not in real time. Normalise to UTC before comparing or subtracting. Wall-clock arithmetic also always produces `fold=0`, so it silently picks the first pass of a repeated hour.
- **Anything keyed by a bare rate name.** Rates are identified by timetable plus name. Keying a dict or lookup by `rate.name` collapses two timetables' rates together. Use `qualified_name`, or `plan.rate_by_name(name, timetable)`.
- **There is no chart in the config flow, and that is settled.** SVG is allowed but the sanitiser strips `rect`, `text` and `fill`, and image `src` rejects data URIs. The plan renders as text; the picture is a built-in `history-graph` card on the enum rate sensor.
- **A new menu entry needs two things.** A `step` block *and* a `menu_options` entry, or it renders as a blank row.
- **The pure modules cannot be imported normally without Home Assistant.** Importing anything from the package runs `__init__.py`, which imports Home Assistant. `tests/_pure.py` reads the eight files off disk into a synthetic package instead.
- **`__pycache__` was tracked in git until 0.8.4.** If a `git stash` or `git checkout` fights you over `.pyc` files, that is why. It is gitignored now.

## Commands

Run from the repository root:

```powershell
# One-time setup
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements_test.txt

# Fast checks (pure tests need nothing installed)
.\.venv\Scripts\ruff check custom_components tests
.\.venv\Scripts\ruff format --check custom_components tests
.\.venv\Scripts\python -m mypy --config-file mypy.ini custom_components/abode_power_tariffs/const.py custom_components/abode_power_tariffs/plan.py custom_components/abode_power_tariffs/validate.py custom_components/abode_power_tariffs/intervals.py custom_components/abode_power_tariffs/allowance.py custom_components/abode_power_tariffs/accounting.py custom_components/abode_power_tariffs/strip.py custom_components/abode_power_tariffs/serialise.py
.\.venv\Scripts\python -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python -m coverage run --rcfile=.coveragerc -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python -m coverage report --rcfile=.coveragerc --fail-under=90
```

This machine's `python` is shadowed by the Microsoft Store alias, so use `py -3` outside the venv.

Keep the tree ruff-formatted. Home Assistant core runs `ruff-format` with no line-length override, so core is 88 characters.

## OpenCode workflow

- Load `architecture-review` before any change that crosses a layer boundary or adds a dependency.
- Load `memory-keeper` at the end of a session to update `.opencode/memory/`.
- Use `/vibe <request>` for small, well-scoped tasks.
- Use `/plan <request>` for exploration and design work.
- Use `/arch` to review current changes against `ARCHITECTURE.md`.
- Use `/mem` to update memory files after a session.
