# Abode Power Tariffs — working notes for Claude

Read this before proposing or changing anything. `docs/PROJECT-NOTES.md` has the
full handover: what was reviewed, what was built, what was deliberately not
done, and the register of known issues not yet addressed.

## What this is

A canonical source of truth for a household's electricity tariff plan. The user
describes the plan once; the component publishes what energy costs now, what it
will cost over the next N hours, which rate is in force, and what rules the user
declared against it.

Original work. The architecture and design are the owner's own, written to solve
something Home Assistant had no clean answer for.

## Standing rules — not up for re-litigation

1. **It reports. It never commands.** The only write is a `utility_meter` tariff
   select the user explicitly nominated.
2. **Everything is published in local time**, with the offset, including the
   evcc forecast attribute. Never UTC. Walk time in UTC internally where
   correctness demands it; nothing leaves that way.
3. **The plan is local wall-clock and does not bend to daylight saving.** A peak
   declared 16:00–21:00 is 16:00–21:00 on both sides of a transition.
4. **A day is 23, 24 or 25 hours.** A rate covering 02:00–03:00 is in force for
   no time on the short day and two hours on the long one. That is the answer,
   not a bug. "24 hours from 18:00" means 18:00 tomorrow.
5. **Import and export are separate flows** — separate rates, separate periods.
   The one shortcut is the all-day-price tickbox on the feed-in screen, which
   ends the export branch.
6. **Setup asks the minimum.** Everything else defaults and lives in Configure.
7. **Declaring a cap is not counting against it.** The plan always declares the
   allowance and fallback and publishes both. Counting is opt-in and is framed
   to the user as an estimate that will not reconcile with a bill.
8. **Constraints declare, they never instruct.** An enforceable rule means the
   user declared it part of what the rate means — not that anything is enforced.
9. **A rate is its timetable plus its name.** Published as `weekday.peak`.
   Always qualified; setup cannot know whether a second timetable is coming.

## How to work with the owner

- **Propose. Wait. Then build.** Answering a question is not agreement, and
  neither is the owner picking between options you offered — get an explicit go
  before writing code. This was the single most repeated failure in the session
  that produced this file, and it wastes his time and your context.
- **One proposal at a time.** Propose, discuss, close, then open the next.
  Never two open at once.
- **Close cleanly.** Do not bolt a caveat onto something already closed. A new
  issue is a new numbered proposal.
- **Be literal. Do not infer.** UI behaviour and code behaviour are different
  things. A remark about a button label is about the label.
- **Do not re-ask a settled question.** If a standing rule answers it, apply it.
- **Plain English.** References are useful; walls of them are not.

## Traps in this codebase

**Same-tzinfo datetime arithmetic.** Python compares and subtracts two aware
datetimes sharing a tzinfo on the *wall clock*, not in real time. This hid a
daylight-saving bug for a year, and a test written the obvious way cannot fail
on it. Normalise to UTC before comparing or subtracting.

**Anything keyed by a bare rate name.** Rates are identified by timetable plus
name. Keying a dict or a lookup by `rate.name` collapses two timetables' rates
together — this broke the strip and the rate plan card. Use `qualified_name`, or
`plan.rate_by_name(name, timetable)`.

**There is no chart in the config flow, and that is settled.** SVG is allowed
but the sanitiser strips everything useful (`rect`, `text`, `fill`), and image
`src` rejects data URIs. A character bar cannot be aligned with a character
ruler because emoji width varies by font. The plan renders as text; the picture
is a built-in `history-graph` card on the enum rate sensor. `docs/PROJECT-NOTES.md`
section 5 has the full evidence — do not re-derive it.

**The pure modules cannot be imported normally without Home Assistant.**
Importing anything from the package runs `__init__.py`, which imports Home
Assistant. `tests/_pure.py` reads the seven files off disk into a synthetic
package instead.

## Running it

```bash
pip install -r requirements_test.txt
ruff check custom_components tests
ruff format --check custom_components tests
mypy --config-file mypy.ini custom_components/abode_power_tariffs/{const,plan,validate,intervals,allowance,strip,serialise}.py
python3 -m unittest discover -s tests -p "test_*.py"
python3 -m coverage run --rcfile=.coveragerc -m unittest discover -s tests -p "test_*.py"
python3 -m coverage report --rcfile=.coveragerc --fail-under=90
```

Keep the tree ruff-formatted. Home Assistant core runs `ruff-format` with no
line-length override, so core is 88 characters, and the eventual submission
should not be one enormous reformat.

Every change needs a test that fails against the code as it was.
