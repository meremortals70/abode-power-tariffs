# Architecture

**Authoritative.** Confirmed by Jason, 23 August 2026, session eleven. This
document says what the plan is. Why each part of it is the way it is, the
options that lost, and whether the code at the current build matches it, are
in the [decision records](decisions/README.md). Two statements were
corrected on 1 October 2026 to match 0.9.11 RC2: the `Rate` sensor's
state, and which flow creates the `utility_meter` helper.

## What this component does

This is a canonical source of truth for a household's electricity tariff
plan. The user describes the plan once; the component publishes what
energy costs now, what it will cost over the next few hours, which rate is
in force, and what rules the user declared against it.

It was separated out of a control project deliberately, so the tariff
model is useful to Home Assistant generally, not just to one automation.

## The fundamental precept

This component is a system of truth. It is not an accounting system. Any
accumulation it does — a demand ledger, an allowance ledger — exists for
one reason only: to let the component report the true cost of electricity
at that point in time. It is not there to keep a running tally for its own
sake, and it is not a bookkeeping system standing in for a bill. Anything
about the design that doesn't serve reporting the true point-in-time cost
is outside what this component is for.

This component calculates on billing cycles, not calendar months. Every
figure that resets monthly — a monthly allowance, the demand cost for the
cycle — resets on the plan's own billing cycle day, whatever that is. It
never resets on the first of the calendar month unless the billing cycle
day happens to be the first.

A plan can never be saved in a state that isn't internally consistent —
every period has to name a rate that actually exists, every day of the year
has to be covered by some day type on some timetable, every declared
allowance has to have a fallback that resolves. This isn't a nicety, it's
the same precept again: a system of truth can't publish a plan that
contradicts itself, because there'd be no true answer for it to report.

A system of truth has to know when it can't tell the truth. If an input
this component depends on — the import or export energy sensor, the
holiday sensor — stops being readable, the component doesn't quietly carry
on as if nothing was missed. It flags itself as incomplete, right away, and
alerts the user the moment it happens — not a fact left to be discovered
by chance later. Recovery clears the immediate flag, but it can't retrieve
what was missed while the input was down — a gap always makes the figures
for that stretch too low, never too high, because a missed peak never
registered and missed energy was never counted. So the cycle itself stays
marked incomplete once a gap has opened in it, even after the input comes
back, until the cycle rolls over and a clean one begins. For as long as
the cycle is marked incomplete, the output card carries a literal red flag
at the top warning that the data is incomplete — not a detail buried
somewhere the user has to go looking for it.

![Plan architecture diagram](images/architecture.png)

---

## What a plan is

A plan is the whole tariff setup for one meter — one household's
electricity connection. Everything the component tells you about cost
comes from a single plan.

In Home Assistant's own terms, this is a service-type integration: each
plan is set up as its own service, tied to its own device. A household
with more than one meter sets up more than one service, one per meter. A
service holds exactly one plan — there's no such thing as one service
managing several plans at once, or a plan existing outside a service.

Archiving works through this, not around it. When the tariff changes, the
old plan's service isn't deleted — its `valid_to` gets set, and it stays
in place, archived. The user sets up a brand new service, under the same
device, for the plan that replaces it. That's how the component keeps a
history of what the tariff used to be, not just what it is now. Nothing
ties the new plan's `valid_from` to the old plan's `valid_to`
automatically, and nothing ties the new service to the old one beyond the
device the user puts it under — making the dates line up, and making sure
the new service belongs to the right device, is on the user.

A plan running past its `valid_to` isn't the same thing as a plan the user
has deliberately archived. Archiving is a decision — the user set the date
themselves, knowing a new plan was ready to take over. A plan simply
reaching its `valid_to` with no successor in place is a different case
entirely: nobody told this service to stop being true, it just ran out.
That's a truth failure the same way a missing input is one, and gets the
same treatment — the user is alerted the moment it happens, and the same
red flag that warns of incomplete data warns of this too, for as long as
the plan sits expired with nothing set up to replace it.

---

## The plan

Two things get decided at the plan level, before anything else:

- Is this a flat rate plan?
- Do you export power to the grid?

A plan has a name and a description. The name is what identifies it —
`Electricity` by default, but a household with more than one plan over
time needs its own names to tell them apart, especially once archiving is
in the picture. The description is free text, entirely optional, for
whatever the user wants to note about the plan.

Beyond that, a plan holds a handful of its own values, not tied to any
timetable:

- **`daily_supply_charge`** — what you pay per day just for being
  connected, no matter which rate is running. Entered in cents, held and
  used everywhere internally in dollars, same as every other price in the
  plan. It accrues as the whole day's amount at the start of the day, not
  prorated across it — the full charge lands the moment the day begins.
- **`billing_cycle_day`** — the day of the month your billing cycle
  starts, from 1 to 28. Every monthly reset in the plan — an allowance
  starting over, demand accounting rolling — happens on this day.
- **`prices_include_tax`** — are the prices you've entered already
  tax-inclusive?
- **`tax_percent`** — what tax rate you're declaring. This is just for the
  record — it's never actually applied to any published price.
- **`valid_from`, `valid_to`** — the date range the plan covers.
  `valid_from` always gets filled in once a plan is completed — there's no
  such thing as a plan with an unset start date. `valid_to` can be left
  open, meaning still in force with no end in sight. Archiving a plan is
  done through this field: when a user archives a plan, `valid_to` gets
  set to the date they archived it. A plan with `valid_to` set to a past
  date is archived; a plan with no `valid_to`, or one in the future, is in
  force.
- **`monthly_charge`** — a flat monthly fee from the supplier. Some
  suppliers charge this on top of the daily supply charge, some use it
  instead of one — the plan doesn't force either shape, both fields are
  just there to be filled in as the actual tariff requires.

---

## What a timetable is

A timetable is one chunk of a plan's life — a set of days (weekdays,
weekends, holidays, maybe a season) during which one particular set of
rates and periods applies. You'd have more than one timetable when the
tariff itself is different on different days — a weekday timetable and a
weekend one, or summer and winter — not just as a way of tidying rates
into groups.

![Timetable diagram](images/timetable-diagram.png)

A timetable belongs to a plan, but it's its own thing. It's stored inside
the plan, but everything about it is declared on the timetable itself.

A timetable has some fields of its own, before you even get to its rates
and periods:

- **`name`** — what the timetable's called.
- **`days`** — which day types it covers.
- **`season_from`, `season_to`** — an optional date range if this
  timetable only applies for part of the year. Leave it blank and it
  applies all year round.
- **`export_same_all_day`** — is export on this timetable one flat price
  all day, or does it change through the day like import can? This is
  what decides whether export periods are even in play.
- **`export_flat_price`** — the single feed-in price, when export is flat
  all day. If export isn't flat, this doesn't mean anything.
- **`export_allowance_kwh`, `export_fallback_price`** — the cap on that
  flat feed-in price, and what you're paid past it. These sit right next
  to the flat price they cap — on the timetable, not on a rate — because a
  flat export price can still have a cap and a fallback, same as a flat
  import plan can.

---

## Every timetable has four things inside it

- Import rates
- Import periods
- Export rates
- Export periods

A plan itself doesn't have rates — its timetables do. A rate belongs to
one timetable and is nested inside it, not sitting in one big list for the
whole plan with a field saying which timetable it's meant for.

---

## What a rate is

A rate is one named price, in force whenever a period on its timetable
says so. A period points at a rate — the period itself has no price, just
a name. An import rate is what you pay for power you draw; an export rate
is what you're paid for power you send back. They're the same kind of
thing on both sides.

![Rate diagram](images/rate-diagram.png)

A rate, import or export, is:

- a name
- a price
- a demand declaration
- an allowance declaration
- constraints, and which of them are enforceable

Constraints let the user tell other components, consuming this
component's output, how they should act on it — things like "no grid
import", "battery charging allowed", "precooling opportunity". This
component never enforces any of it itself, only declares it. Marking a
constraint enforceable is the user saying a consuming component should
treat it as a rule rather than just a hint.

Import and export are two separate flows — a rate belongs to one or the
other, never both, and they're never mixed together. What they share is
shape: an import rate and an export rate are the same shape as each
other, so nothing about being on the export side means a rate is allowed
fewer of the things that shape defines.

---

## What a period is

A period is a slice of the day on one timetable — a start time, an end
time, and the name of whichever rate is running during that slice. It
doesn't carry a price itself. Working out what something costs at a given
moment means: find the timetable that's in force, then the period on it,
then the rate that period names.

![Period diagram](images/period-diagram.png)

A period, import or export, works the same way — it names one of that
timetable's own rates. Import periods name import rates, export periods
name export rates, nothing more.

The periods on one side of one timetable have to cover the whole day, with
no gaps. Every minute of the 24 hours belongs to some period naming some
rate — there's no such thing as a moment nothing applies to.

---

## What a ledger is

A ledger only exists for allowances and demand charges. Its purpose is
narrow: to let the component know the true point-in-time cost for a rate
that has one of these declared. For an allowance, that means knowing the
moment the allowance has been used up, so the component can switch to
reporting the fallback price for the rest of that period. An allowance is
only ever counted for the time period it applies to — the ledger is
cleared once that period ends, not carried forward. For a demand charge,
the same idea applies to the peak reached so far. Either way, the rate's
own fields are the fixed setup; the ledger is the number that moves
against them.

![Ledger diagram](images/ledger-diagram.png)

A demand charge is worked out from the highest reading in the declared
interval, during the rate's demand-metered window, across the whole
billing cycle — not per day, per cycle. That means the figure the ledger
holds partway through a cycle is only ever what's been reached so far. It
can still go up before the cycle ends. The true, final demand cost for the
cycle is only ever knowable in retrospect, once the cycle has actually
closed — anything reported before that is correctly the truth of what's
happened up to now, not a claim about what the final cost will be.

A ledger isn't part of the plan — it's not something the user configures,
and it's not stored alongside the rates and timetables that make up the
tariff. But within the time period it belongs to, it does have to survive
a restart: if the component restarted partway through an allowance period
and lost the count, it could wrongly keep reporting the pre-allowance
price after the cap had actually been reached, or wrongly apply the
fallback before it should. So a ledger's own numbers are written to
storage separately from the plan, kept only for the period they apply to
and cleared once it ends.

A ledger only gets created for a rate that actually declares demand or an
allowance. If a rate has neither, there's no ledger for it — nothing gets
created, nothing sits around empty.

Where a ledger does exist, there's exactly one per rate, keyed on that
rate's own identifier. Two rates never share one, and nothing that happens
on one rate ever touches another rate's ledger — import or export, same
timetable or different.

---

## External inputs and external outputs

**External inputs** are what the component uses to calculate the true cost
of electricity. Two energy sensors are inputs — the household's actual
import and export energy. They're what allowance and demand calculations
are measured against; without them, a ledger has nothing to accumulate.

A third input is a holiday sensor, nominated by the user. It's what the
component checks to know whether today counts as a holiday for the
purposes of resolving which timetable is in force, on top of the ordinary
weekday tokens.

The import energy sensor is mandatory. Every plan requires one, whether or
not any rate in it declares a demand charge or an allowance.

**External outputs** are the sensors and entities the component publishes,
each holding one true fact about cost or state right now:

- **Import price**, **export price** — the price in force this instant.
  Each also carries a forecast: a forward-looking series of the prices
  still to come. This is what lets other components forecast against —
  an EV charger deciding when to charge, a battery deciding when to
  discharge, anything that needs to plan ahead rather than only ever react
  to what's true right now. An interval the component can't resolve a
  price for is left out of the forecast entirely, never sent as a zero or
  a placeholder — the same true-or-absent rule as everywhere else in this
  document, just applied to the future instead of the present.
- **Rate** — the rate in force, shown as its timetable and its own name,
  e.g. `Every day Peak`. The full four-segment identifier, e.g.
  `electricity.every_day.import.peak`, is in its `scheduled_rate`
  attribute.
- **Next rate change** — when the rate in force is next going to change.
- **Daily supply charge** — the declared rate itself, as configured, in
  dollars per day. Not the same thing as "supply charge today" below —
  this is the fixed setting; that's what it has accrued to.
- **Supply charge today**, **supply charge this cycle** — the daily supply
  charge accumulated so far today, and for the billing cycle. Both are the
  true figure of what's accumulated up to this instant — not a projection
  of the final total, which for the billing cycle figure only exists once
  the cycle actually closes.
- **Demand period active** — per rate, whether a demand-metered window is
  in force right now.
- **Allowance used**, **allowance remaining** — per rate that declares an
  allowance, how much of it has been spent and how much is left, for
  whichever period the allowance runs against — each occurrence of the
  rate's slot, or the whole billing cycle, as that rate declared.
- **Demand now** — per rate that declares a demand charge, the average
  draw over the demand interval currently in progress. Reads low until the
  interval actually completes, which is exactly why an interval still in
  progress is never treated as a new peak.
- **Demand peak** — per rate, the highest completed interval so far this
  billing cycle. This is the number the demand charge is built on — the
  true figure only exists once the cycle closes, the same true-so-far
  distinction the ledger section makes. **Demand peak at** is the timestamp
  of the interval that set it.
- **Demand cost to date**, **demand cost projected** — per rate, what the
  peak reached so far has cost over the days elapsed in the cycle, and
  what it would cost if nothing higher is reached before the cycle ends.
  The projected figure is a "what if nothing changes" statement, not a
  claim about what the final cost will actually be.
- **Billing cycle progress** — how far through the current billing cycle
  this is, as a percentage of calendar days elapsed against calendar days
  in the cycle.
- **Data complete** — whether every input the component depends on has
  been readable throughout the current billing cycle. Goes false the
  moment an input becomes unreadable, and stays false for the rest of the
  cycle even after the input recovers, because what was missed during the
  gap can't be retrieved. This is what an alert to the user and the red
  flag on the output card are both driven from — the same one fact,
  surfaced two ways. A plan that has run past its `valid_to` with no
  successor set up drives the same alert and the same red flag, for the
  same reason: the component can no longer stand behind what it's
  reporting as true.
- **One binary sensor per constraint declared anywhere in the plan** — not
  per rate. `no_grid_import` is one entity, on whenever the rate currently
  in force happens to carry it, off otherwise — `coasting_permitted`,
  `precool_opportunity`, `grid_charge_battery` are further examples seen in
  practice. This is how a constraint actually reaches a consuming
  automation, not just something recorded in the plan. Each one also
  carries whether it's enforceable, and which rate and period it's
  currently attached to.
- The **tariff select write-back** — an output too, just written to an
  entity the user nominates rather than one this component creates itself.
  It exists for a different reason than `Rate` above: `Rate` is a
  real-time value, for anything that needs to know the current rate right
  now. Home Assistant's energy management needs something that
  accumulates over time, split out by tariff — that's what a
  `utility_meter` helper does, and the only way to tell it which tariff is
  current is by writing to a select entity, which is what this output is
  for.

This list is drawn from what the running component actually publishes and
may not be complete or final — check it against the device card, not
against this document, if the two ever disagree.

Configure can also create a separate Home Assistant `utility_meter` helper on
request, using the plan's rates as its tariffs. This is a one-time
convenience action, not something the plan owns afterward — renaming a
rate doesn't rename the meter's tariff, and removing the plan doesn't
remove the meter.
