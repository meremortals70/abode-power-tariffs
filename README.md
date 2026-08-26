# Abode Power Tariffs

Enter your electricity plan once, in the Home Assistant interface, and stop
building it out of helpers.

If you are on a time-of-use plan, the usual way to get a working price into the
Energy dashboard is an `input_number` for every rate, two time helpers for every
time period, a workday sensor, a Jinja template sensor with a nested `if` chain, a
`utility_meter` with tariffs, and an automation for every time period boundary — then
all of it again for export. Change retailers and you rebuild the lot.

This replaces that. You describe the plan; it publishes the prices, the rate in
force, the rules in force, and the next 24 hours.

**It decides nothing.** No optimiser, no load scheduling, no "cheapest time period"
action. It answers questions and other things decide.

---

## What you get

| Entity | What it is |
|---|---|
| `sensor.<name>_import_price` | Price now, in currency per kWh. Goes straight into the Energy dashboard |
| `sensor.<name>_export_price` | Feed-in price now |
| `sensor.<name>_rate` | The rate in force, as `plan.timetable.import.peak` — always four segments: the plan, the timetable, the side, and the rate's own name |
| `sensor.<name>_next_rate_change` | When the import rate next changes |
| `sensor.<name>_next_export_change` | When the feed-in price next changes, if it moves during the day |
| `sensor.<name>_daily_supply_charge` | Your declared daily supply charge |
| `sensor.<name>_supply_charge_today` | The declared charge accrued so far today |
| `sensor.<name>_supply_charge_energy` | The declared charge accrued so far this billing cycle |
| `sensor.<name>_today_schedule` | Today's full local-midnight-to-midnight schedule — `segments` (for a chart), `periods` (one entry per period as entered), and `table` (the same, already rendered as a markdown table string) — see A daily rate card |
| `sensor.<name>_billing_cycle_progress` | Days elapsed of the cycle, as a percentage. Only when something on the plan accumulates |
| `sensor.<name>_<rate>_allowance_used_kwh` | kWh spent so far in a capped rate's current period, once a meter is nominated. One per capped rate |
| `sensor.<name>_<rate>_allowance_remaining_kwh` | kWh left. One per capped rate |
| `sensor.<name>_<rate>_demand_now_kw` | The average draw over the demand interval in progress, once a meter is nominated. One per demand-charged rate |
| `sensor.<name>_<rate>_demand_peak_kw` | The highest completed interval this billing cycle — the number the bill is built on. One per demand-charged rate |
| `sensor.<name>_<rate>_demand_peak_at` | When that peak was set |
| `sensor.<name>_<rate>_demand_cost_to_date` | What the peak has cost so far, on the declared basis |
| `sensor.<name>_<rate>_demand_cost_projected` | What the bill says if nothing beats the peak |
| `binary_sensor.<name>_<constraint>` | One per rule you declared — see below |
| `binary_sensor.<name>_<rate>_demand_period_active` | On while this rate is in force. One per rate that carries a demand charge |
| `binary_sensor.<name>_data_complete` | Off while an input is unreadable. Only when something on the plan accumulates — see Accumulating figures |

Plus three actions: `abode_power_tariffs.get_intervals`, returning the forward
series; `abode_power_tariffs.export_rates_csv`, returning the plan's
rates, export rates and time periods as CSV text — for a spreadsheet, or an
inverter's own tariff screen; and `abode_power_tariffs.get_day_schedule`,
returning today's full schedule — the same thing
`sensor.<name>_today_schedule` already publishes as an attribute, callable
directly for a script or an automation that does not want to read it off the
entity.

**Everything that accumulates is an estimate this integration measured
itself.** It is taken from a meter you nominate, on a clock this integration
keeps, and it will not reconcile exactly with what your retailer bills. Every
accumulating sensor's attributes say so.

---

## Installing

### HACS

1. HACS → three-dot menu → **Custom repositories**
2. Repository `meremortals70/abode-power-tariffs`, type **Integration**
3. Find **Abode Power Tariffs** in HACS and download it
4. Restart Home Assistant
5. **Settings → Devices & services → Add integration → Abode Power Tariffs**

### By hand

Copy `custom_components/abode_power_tariffs` into your `config/custom_components`
directory and restart, then add the integration as above.

### Setup

One field: a channel name. Use one entry per metering channel — general
consumption, controlled load, a second circuit. They are separate plans with
separate prices.

A working plan is created for you: a single rate at 30 c/kWh covering the whole
day. Nothing is broken while you edit it.

---

## Removing

Settings → Devices & services → Abode Power Tariffs → the three-dot menu on the
entry → **Delete**. Entities and the device go with it.

If you installed through HACS, remove it there as well, then restart.

Anything you pointed at it — Energy dashboard sources, automations triggering on
the constraint sensors, `utility_meter` selects it was driving — needs its own
tidying up. Nothing outside the integration is changed on removal.

---

## How a plan is put together

Four things, and the order matters:

| | |
|---|---|
| **The plan** | One meter or one circuit. Its name, and the charges that apply no matter what you use — daily supply charge, monthly fee, tax |
| **A timetable** | A set of days that share the same prices. "Every day", or "Weekday" and "Weekend" and "Public holidays" |
| **A rate** | A named price, nested inside the timetable it belongs to. It is identified by the plan, the timetable, the side and its own name — always four segments — so a Peak on the Weekday timetable and a Peak on the Weekend one are two rates at two prices, published as `electricity.weekday.import.peak` and `electricity.weekend.import.peak` |
| **A time period** | A span of the day, priced at one of that timetable's rates. Together they must cover the day exactly once |

Feed-in works the same way, per timetable: either one price all day, or its own
rates and its own time periods.

**A plan can have as many timetables as it needs.** Weekends priced differently
is not a second plan — it is a second timetable inside the same one.

---

## Setting it up

Settings → Devices & services → Add integration → Abode Power Tariffs.

**1. Plan name**, an optional description, and two questions that decide the
shape of everything that follows:

- **Is this power plan based on a single rate?** — for a plan with no clock
  in it at all: an amount for the first part of your usage, then a different
  price for the rest of the billing period. Tick this and setup skips
  straight to step 3 below; there are no timetables, rates or time periods
  to enter.
- **You export power to the grid** — turns the feed-in screens on. Leave it
  off and nothing about export is asked, on this plan or any timetable in it.

Leave both off for an ordinary time-of-use or flat-rate plan and the rest of
setup runs as before.

**2. Fixed charges** — daily supply charge, monthly fee, whether prices
include tax and at what rate, the day of the month your billing cycle
starts, and your grid import energy sensor. The import sensor is mandatory
for every plan, asked here once — not re-asked per rate, whatever any
individual rate does or does not declare.

**If "Is this power plan based on a single rate?" was ticked**, this is
followed by one more screen instead of the timetable loop below:

**3. Prices** — the price for the first part of your usage, the allowance in
kWh, and the price for the rest. If export was also switched on, the same
three questions for export. This is declared exactly like an allowance on any
other rate: nothing is counted against it yet. Submitting this screen finishes
setup.

**Otherwise, the timetable loop runs**, the same screens in the same order for
every timetable:

**3. Timetable** — its name, and which days it covers. Leave "Every day is the
same" on unless weekends or public holidays are priced differently.

**4. Rates** — the prices on this timetable, and any rules that apply during
them. Call it `Peak` and it stays `Peak`: it belongs to the timetable you are
entering, so a weekday Peak and a weekend Peak can both be called Peak at
different prices. It is published as `electricity.weekday.import.peak`.

The screen opens on the two things every rate has — its name and its price.
Everything else is in a section you open only if it applies:

- **Demand charging** — whether a demand charge applies while this rate is in
  force, and what it is
- **Allowance** — whether the rate is capped, and what energy costs past the
  cap
- **Constraints** — the rules you are declaring about this rate

All three start closed, so a rate with none of these things is a name and a
price. Nothing inside them is required.

Enter a rate and the screen returns for the next. Choose **Continue to the
time periods** when they are all in — anything filled in on the screen is
checked and kept on the way out, so a rate typed in and then continued from
is not lost. Continue from a blank screen and nothing is added.

**5. Time periods** — start, end, and which rate. Only the rates belonging to
this timetable are offered, shown by their published identifier, so
`electricity.weekday.import.peak` cannot be allocated on the weekend. If the
timetable has no rates yet the rate screen opens first.

The start is included and the end is not, so one period can end at 16:00 and
the next begin at 16:00. A period running to midnight ends at 00:00.

**Continue to feed-in** is a gate, not a preference: it moves on only once
every minute of the day is accounted for. Until then the screen says how much
is still uncovered and stays where it is. A plan with a gap in it is not a
valid plan.

**6. Feed-in** — shown only if "You export power to the grid" was ticked on
step 1. One price all day, or not. Leave the switch on and enter the price,
the export allowance if there is one, and what you are paid past it; this
timetable is then done. Turn it off and you get:

- **6a. Feed-in rates** — a name and a price, and the same shape an import
  rate has: the allowance on that feed-in price and what is paid once it is
  spent, a demand charge if one applies, and any rules you want to declare.
  Import and export are separate flows, never mixed, but nothing about being
  on the export side means a rate is offered fewer of these things
- **6b. Feed-in time periods** — same as step 5, independent of the import
  ones, and gated the same way

**7. Timetable complete** — two buttons. **Add a timetable for other days**
takes you back to step 3 for the next one. **Finish and create the plan** ends
setup.

### A worked example

A plan where weekends are cheaper and the weekend feed-in is better:

| Screen | Weekday pass | Weekend pass |
|---|---|---|
| Timetable | `Weekday`, Mon–Fri | `Weekend`, Sat, Sun, public holidays |
| Rates | Off Peak, Shoulder, Peak → `electricity.weekday.import.off_peak`, `electricity.weekday.import.shoulder`, `electricity.weekday.import.peak` | Off Peak, Peak → `electricity.weekend.import.off_peak`, `electricity.weekend.import.peak` |
| Time periods | 00:00–06:00 Off Peak, 06:00–16:00 Shoulder, 16:00–21:00 Peak, 21:00–00:00 Shoulder | 00:00–16:00 Off Peak, 16:00–00:00 Peak |
| Feed-in | One price all day, 2.7 c | Switch off → `Daytime` 2.7 c, `Evening` 12 c → 00:00–16:00 Daytime, 16:00–00:00 Evening → `electricity.weekend.export.daytime`, `electricity.weekend.export.evening`. Feed-in rates are scoped to their timetable the same way import rates are, so a Weekday Evening and a Weekend Evening can both just be called Evening |
| Timetable complete | Add a timetable for other days | Finish |

Five rates, two timetables, one plan.

---

## Changing it afterwards

Settings → Devices & services → Abode Power Tariffs → **Configure**. Everything
entered at setup can be changed there; nothing requires deleting the plan.

The plan is shown before you choose anything and again on every screen that
touches time periods, so a gap or an overlap is visible the moment you make
one. It is one table per timetable — the time span, the name as you typed it,
the identifier it is published under, and the price:

```
Weekday
  00:00-06:00  Off Peak  electricity.weekday.import.off_peak    19.80 c/kWh
  06:00-16:00  Shoulder  electricity.weekday.import.shoulder    32.10 c/kWh
  16:00-21:00  Peak      electricity.weekday.import.peak        56.88 c/kWh
    demand: $18.40/kW/day, 30 min interval
  21:00-24:00  Shoulder  electricity.weekday.import.shoulder    32.10 c/kWh
  Coverage: complete. 4 periods, no gaps, no overlaps.
  Feed-in: 2.70 c/kWh all day
```

A demand charge or an allowance on a rate gets its own line underneath the
row it belongs to, so it is visible without opening the rate again to check.

There is no chart and no colour bar in Configure itself. A configuration
dialog renders markdown, and a bar drawn from characters cannot be made to
line up with a clock across every font and platform. For a coloured picture
on your dashboard, see **A daily rate card**, below.

The Configure menu:

| | |
|---|---|
| **Rates** | Add, edit, remove. Renaming follows through into every time period that uses it |
| **Day patterns** | The timetables. Add, edit, duplicate or remove one, including its feed-in mode and its season dates. Renaming a timetable takes its rates with it — a rename is only a rename |
| **Time periods** | Per timetable, and offering only that timetable's rates |
| **Feed-in** | Feed-in rates with their allowances, and their time periods per timetable |
| **Supply charge, tax, plan dates, sensors** | The plan-wide settings |
| **Track usage by rate** | Utility meters — see below |
| **Rate plan card** | The plan laid out for transcribing into an inverter |

### The rate fields in full

Beyond the name and the price, a rate carries the following. Everything here
sits in one of the three sections on the rate screen, all of which start
closed. Export rates have the same shape — a demand charge and constraints
sections exactly like an import rate's, alongside the allowance they already
had:

| Field | Section | Notes |
|---|---|---|
| Demand charge period | Demand charging | Marks this rate as carrying a demand charge, and turns on `binary_sensor.<name>_<rate>_demand_period_active` while it is in force |
| Demand charge (c/kW/month) | Demand charging | Cents, like every other price on the form. Declared alongside the flag. The number the demand cost sensors are built on |
| Meter averaging interval | Demand charging | 15, 30 or 60 minutes, or instantaneous. Defaults to 30 minutes, what Australian distributors meter on |
| How the peak is charged | Demand charging | Once for the billing cycle, or once for every day of it. The same peak can be a very different bill either way |
| Energy allowance for this rate | Allowance | Some plans give a period free only up to a cap. Zero for none. Counted against the plan's nominated meter |
| Rate beyond the allowance | Allowance | Required when there is an allowance |
| What the allowance covers | Allowance | Each occurrence of this rate's time period, or the whole billing cycle. Defaults to the time period, which is the tighter and more common cap |
| Information only rules | Constraints | Your own words. Each becomes a binary sensor. See below |
| Enforceable rules | Constraints | The same, but declared as part of what the rate means. See below |

**The grid import meter is not on the rate form.** It is mandatory for every
plan and asked once, on the Fixed charges screen during setup and on
Supply charge, tax, plan dates, sensors in Configure — not re-declared per
rate. A grid export meter can also be nominated there, optional, needed only
if an export rate declares a demand charge or an allowance.

**Coasting permitted is a rule, not a field of its own.** It says the same
kind of thing the other rules say — something another system may act on while
this rate is in force — so it is declared in the two rule lists like any
other, and `coasting_permitted` is published as true only where you declared
it.

**The export allowance is not on an import rate.** Import and export are
separate flows with separate rates and separate periods, so the cap on a
feed-in price and what is paid past it are declared beside that feed-in
price: on the feed-in rate where export is priced by period, and on the
timetable where it is one price all day.

### Rate names

A rate is identified by its plan, its timetable, its side (import or export)
and its own name — always four segments. Type `Peak` on the Weekday timetable
and on the Weekend one and you have two rates, both called Peak, at whatever
prices you gave them. They are published as `electricity.weekday.import.peak`
and `electricity.weekend.import.peak`, and that is what the rate sensor
reports and what a `utility_meter` tariff should be called.

### Seasons

A timetable can carry a date range, entered as `MM-DD`. It may cross the new
year — `11-01` to `03-31` is summer in the southern hemisphere. A seasonal
timetable wins over a year-round one on the dates it covers.

### Validity dates

When your retailer reprices, set **Plan valid to** on the old plan and add a new
plan for the new prices. Historical cost figures then stay correct against the
price that was actually in force.

---

## Constraints

A constraint is a rule you declare on a rate. Name it whatever you like —
`no_grid_import`, `grid_charge_battery`, `precool_opportunity`. Each becomes a
binary sensor that is on while a rate carrying it is in force.

This is what battery, hot water and EV automations should trigger on, instead of
a clock comparison. When the plan moves, they move with it and you edit nothing.

Note what they are: **rules you declared**, not decisions the integration made.

### Information only, or enforceable

Rules go in one of two lists on the rate.

**Information only** is a useful fact about the rate. A consuming system can
look at it and decide it does not care.

**Enforceable** says you are declaring the rule to be part of what the rate
means, so another system should treat it as a rule rather than a hint.

The difference is a declaration about your tariff, not an instruction. This
integration enforces nothing either way — it says which rules you meant as
rules, and the consuming system decides what to do about them.

Every rule appears in the `constraints` list as it always has. The enforceable
ones also appear in `enforceable_constraints`, and each binary sensor carries an
`enforceable` attribute. Rules on a plan created before this are all information
only until you say otherwise.

---

## Energy dashboard

**Grid consumption cost.** Settings → Dashboards → Energy → your grid
consumption source → **Use an entity with current price** → pick
`sensor.<name>_import_price`. No template sensor.

**Return to grid.** The same, with `sensor.<name>_export_price`.

**Daily supply charge.** The Energy dashboard has no field for a fixed daily
charge — it is one of its longest-running open requests. `sensor.<name>_daily_supply_charge`
states what the charge is; `sensor.<name>_supply_charge_today` and
`sensor.<name>_supply_charge_energy` accrue it, on this integration's own
clock, against the billing cycle day you declared.

**Usage split by rate.** Create a `utility_meter` helper with your rate names as
its tariffs. It makes one meter per rate plus a select naming which is in force.
Nominate that select under Track usage by rate and the integration sets it at each
time period boundary — the automation people normally write for this disappears.

---

## A daily rate card

`sensor.<name>_today_schedule` holds today's full local-midnight-to-midnight
schedule two ways: `segments`, fixed-width slices (15 minutes by default)
each carrying the price, the rate, and whether a demand charge applies, and
`periods`, the same day resolved to its actual periods as entered — one row
per period, not per slice. Both cover the whole day, not just what is still
ahead. It exists for exactly this: a coloured picture on a dashboard, which
nothing built into Home Assistant draws on its own — a `history-graph` card
only shows what has already happened, and has no way to colour by price
rank rather than by which rate was in force.

[ApexCharts Card](https://github.com/RomRider/apexcharts-card), installed
through HACS, can. This reads the same sensor and draws a coloured bar for
the whole day, cheapest to most expensive, with a line at the current time:

```yaml
type: custom:apexcharts-card
graph_span: 24h
span:
  start: day
now:
  show: true
  label: Now
header:
  show: true
  title: Today's rates
apex_config:
  chart:
    toolbar:
      show: false
  plotOptions:
    bar:
      columnWidth: 100%
  dataLabels:
    enabled: false
  yaxis:
    show: false
  tooltip:
    enabled: true
series:
  - entity: sensor.electricity_today_schedule
    type: column
    name: Rate
    data_generator: |
      const segs = entity.attributes.segments || [];
      if (segs.length === 0) return [];
      // Ranked by price plus the demand rate declared on it.
      const scores = segs.map(s => s.per_kwh + (s.demand_rate_per_kw_month || 0));
      const min = Math.min(...scores);
      const max = Math.max(...scores);
      const range = (max - min) || 1;
      // The colour is set directly on each point (fillColor), rather than
      // through plotOptions.bar.colors.ranges with distributed: true --
      // that combination, on a datetime x-axis, coloured bars wrong in
      // practice, confirmed against a real dashboard and not explained by
      // anything wrong in this ranking (proven correct against real data
      // before this was changed). Setting fillColor directly on each
      // point is a plain, standard ApexCharts feature and does not depend
      // on distributed mode or a ranges lookup at all.
      const colourFor = (rank) => {
        if (rank < 20) return '#2e7d32';
        if (rank < 40) return '#8bc34a';
        if (rank < 60) return '#fdd835';
        if (rank < 80) return '#fb8c00';
        return '#e53935';
      };
      return segs.map((s, i) => {
        const rank = Math.round(((scores[i] - min) / range) * 100);
        return {
          x: new Date(s.start_time).getTime(),
          y: rank,
          fillColor: colourFor(rank),
        };
      });
```

Change `sensor.electricity_today_schedule` to your own channel's entity id.
The bar's height and colour both track the ranking above, cheapest at 0,
most expensive at 100 — not the literal price, which is why the y-axis is
hidden. What each slice actually costs belongs in a table underneath, not
squeezed onto a bar with 96 slices in it.

The same sensor also carries a `table` attribute — the periods already
rendered into a markdown table string, server-side, so the card reading it
has nothing to get wrong: no template loop, no third-party card behaviour
to depend on, one line:

```yaml
type: markdown
content: "{{ state_attr('sensor.electricity_today_schedule', 'table') }}"
```

Change the entity id to your own. `periods` (the same data, unrendered —
one dict per period, each with `start`, `end`, `rate_name`, `per_kwh`,
`demand_period` and `demand_rate_per_kw_month`) is also there if you want
to build your own table with a card that reads a list attribute directly,
but the plain string above is the one actually verified against a real
Home Assistant template render before being put in this document.

Put the two in a `vertical-stack` and you have the coloured picture with the
current time marked, and the numbers it is drawn from, in one card:

```yaml
type: vertical-stack
cards:
  - type: custom:apexcharts-card
    # ... the chart config above
  - type: markdown
    content: "{{ state_attr('sensor.electricity_today_schedule', 'table') }}"
```

---

## Accumulating figures

Declare an allowance or a demand charge on a rate, nominate the grid import
meter, and this integration starts counting: what has been used against a
cap, and the highest completed interval of a demand charge, per rate.

**It is an estimate this integration measured itself.** It is not what your
retailer measures, and it will not reconcile with a bill to the cent. Every
accumulating sensor's attributes say so, alongside the billing cycle the
figure belongs to.

**A cap switches the effective rate once it is spent.** `sensor.<name>_rate`
reports the fallback and `sensor.<name>_import_price` reports its price; the
declared cap and fallback are still published on the scheduled rate's own
attributes for a consumer that wants to apply the rule itself instead.

**A capped rate declares which period the allowance covers**: each occurrence
of its own time period, or the whole billing cycle. A period cap resets on
entry to every occurrence — nothing carries from yesterday's peak period into
today's. A monthly cap accumulates across every slot and day and resets on
the billing cycle day.

**A demand charge is measured on a clock, not on the price schedule.** Declare
the averaging interval — 15, 30 or 60 minutes, or instantaneous — and the
integration finds the highest *completed* interval while the rate is in
force. A half-finished interval is never a candidate, so the figure reads low
until each interval closes. `sensor.<name>_<rate>_demand_cost_to_date` and
`..._demand_cost_projected` apply the declared basis: once for the billing
cycle, or once for every day of it.

**A gap in the meter makes the cycle's figures read low, never high.**
`binary_sensor.<name>_data_complete` goes off the moment the nominated meter
becomes unreadable, and a Home Assistant repair notice appears at the same
time. The binary sensor clears when the meter comes back; its `cycle_complete`
attribute does not, because reconnecting does not recover what was missed —
it stays down for the rest of the cycle and clears when the cycle rolls.

**Restarting Home Assistant does not lose a count.** A period allowance
restores only if the integration comes back inside the same occurrence of the
period; a monthly one, only inside the same billing cycle; a demand peak,
only inside the same billing cycle. Coming back into a different one starts
from zero rather than keeping a stale figure.

That select is the only thing this integration ever writes, it is off by
default, and it writes only to selects you nominated.

---

## evcc

Both price sensors carry a `forecast` attribute holding the next 24 hours as
`{start, end, value}`, which is the shape evcc reads. The timestamps are local
with the offset, like everything else this integration publishes — the offset
is what makes an instant unambiguous on the morning the clocks go back:

```yaml
tariffs:
  grid:
    type: custom
    forecast:
      source: homeassistant
      uri: http://homeassistant.local:8123
      token: your-long-lived-token
      entity: sensor.electricity_import_price
      attribute: forecast
```

---

### Seeing the plan as a picture

Configure shows the plan as text — every period, what it costs, and whether the
day is covered. There is deliberately no chart in there: a config dialog renders
markdown, and a bar drawn from characters cannot be made to line up with a clock
across every font and platform.

Home Assistant already draws it properly. `sensor.<name>_rate` is an enum, so a
built-in **history-graph** card renders it as a coloured timeline with a real
time axis, one band per rate:

```yaml
type: vertical-stack
cards:
  - type: history-graph
    title: Tariff
    hours_to_show: 24
    entities:
      - entity: sensor.<name>_rate
        name: Rate

  - type: history-graph
    hours_to_show: 24
    entities:
      - entity: sensor.<name>_import_price
        name: Import
      - entity: sensor.<name>_export_price
        name: Feed-in

  - type: entities
    entities:
      - sensor.<name>_import_price
      - sensor.<name>_export_price
      - sensor.<name>_rate
      - sensor.<name>_next_rate_change
      - sensor.<name>_daily_supply_charge
```

Replace `<name>` with your plan's slug. The first card is the coloured bar; the
second plots the two prices over the same period. History is the last 24 hours,
so a plan set up today fills in as the day goes.

---

## Rate plan card

Under Configure there is a **Rate plan card**: the plan laid out with buy and
sell prices per period, weekday and weekend separately, in the order an
inverter's own tariff screen asks for them.

Tesla, Sungrow, Fronius and GoodWe all have that screen, and the plan usually
gets typed into it a second time from a bill. This renders it from the same
source of truth. Transcription is manual — the integration makes no vendor calls
and holds no vendor credentials.

---

## The action

```yaml
action: abode_power_tariffs.get_intervals
data:
  config_entry_id: 01JABCDEF...
  hours: 12
  resolution_minutes: 30
response_variable: tariff
```

Returns:

```yaml
intervals:
  - start_time: "2026-08-14T16:00:00+10:00"
    end_time: "2026-08-14T16:30:00+10:00"
    duration: 30
    per_kwh: 0.584
    export_per_kwh: 0.043
    rate: electricity.weekday.import.peak
    constraints: [coasting_permitted, no_grid_import, precool_opportunity]
    enforceable_constraints: [no_grid_import]
    coasting_permitted: true
    allowance_kwh: null
    fallback_rate: null
    fallback_per_kwh: null
    day_pattern: Weekday
    demand_period: false
    demand_rate_per_kw_month: 0.0
    export_allowance_kwh: null
    export_fallback_price: null
    forecast: false
```

`per_kwh` is in dollars and the field names match the core Amber Electric
integration, so anything already written against that shape works here.

Times are local, with the offset. On the day the clocks go back a wall-clock
time appears twice and the offsets tell the two apart; `duration` is always the
real length of the interval.

`rate` is the identifier — the plan, the timetable, the side and the name,
always four segments. `constraints` is every
rule as it always was; `enforceable_constraints` is the subset declared as part
of what the rate means. `coasting_permitted` is one of those rules, published
as its own field for the consumers that already read it, and true only where
you declared it.

`demand_period` and `demand_rate_per_kw_month` are declared, not applied —
`per_kwh` is always just the energy rate. A consumer wanting the real cost of
drawing power in this interval applies its own assumption about kW draw to
the demand rate itself. `export_allowance_kwh` and `export_fallback_price` are
the same idea for feed-in: declared facts about an allowance and what follows
it, never blended into `export_per_kwh`. They follow the feed-in price in
force at that moment, not the import rate running alongside it, so on a
timetable with feed-in periods they change when the feed-in rate changes.

`allowance_kwh`, `fallback_rate` and `fallback_per_kwh` are the cap and what is
paid past it, published whether or not this integration is counting, so a
consumer can apply the rule itself.

`forecast` marks a value that was predicted rather than contracted. A static
plan is always `false`.

---

## Examples

**Charge the battery while energy is free**

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.electricity_precool_opportunity
    to: "on"
actions:
  - action: script.battery_grid_charge
```

**Run the house off the battery through the peak**

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.electricity_no_grid_import
    to: "on"
actions:
  - action: script.battery_self_powered
```

**Warn when the free allowance is nearly spent**

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.electricity_weekday_peak_allowance_remaining_kwh
    below: 3
actions:
  - action: notify.persistent_notification
    data:
      message: "Under 3 kWh of the free allowance left."
```

**Delay the dishwasher until the cheapest rate**

```yaml
triggers:
  - trigger: state
    entity_id: sensor.electricity_rate
    to: cheap
conditions:
  - condition: state
    entity_id: input_boolean.dishwasher_waiting
    state: "on"
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.dishwasher
```

---

## How the data updates

Nothing is polled and nothing is fetched. The plan is stored in the config entry
and resolved locally.

The next boundary is computed and scheduled; when it fires, every entity updates
and the following one is scheduled. Both sides count: the import rate changing
and the feed-in price changing are separate boundaries and separate sensors, and
whichever comes first is what wakes the integration.

Everything is also recomputed on the zero second of every minute. Time periods
are whole minutes, so that tick lands on each boundary exactly, and no single
scheduled instant is load-bearing — a mistake costs a minute rather than hours.
A recompute that changes nothing writes nothing. There is also an update
whenever the nominated holiday or import energy sensor changes.

### Daylight saving

Time periods are wall-clock times, which is what you want: a peak period is
16:00 local on both sides of a transition, and your plan does not change because
the clocks did.

The horizon is wall clock too. Twenty-four hours from 18:00 means 18:00
tomorrow, which is 23 real hours on the day the clocks go forward and 25 on the
day they go back. Inside that, the series is walked in real instants, so every
interval is genuinely the length it says it is. The hour that does not exist is
not emitted; the hour that happens twice is emitted twice, with its two
different offsets. A rate covering 02:00 to 03:00 is in force for no time at all
on the short day and for two hours on the long one, because that is what
happened.

The same applies to the sensors, not just the forecast. On the morning the
clocks go back, a plan with a boundary inside the repeated hour changes rate,
changes back, and changes again — because that hour genuinely happens twice.
A boundary is stored as minutes past midnight, which on that one morning names
two real instants an hour apart, so both are built and the nearer one ahead is
taken.

Everything is reported in local time, with the offset. Nothing is published in
UTC.

---

## Troubleshooting

**The price sensor is unavailable.** No time period resolves at this moment. Open
Configure and read the strip — there is a gap, or a day type that no day pattern
covers.

**A repair issue says the plan is not valid.** The plan was saved by an older
version and no longer passes validation. The issue lists every problem; open
Configure and fix them.

**Prices are held after the plan expired.** Deliberate. Removing the price
entity would stop Energy dashboard cost tracking without saying so, and you
would find it weeks later as a gap in a graph. Set up the new plan and the
repair issue clears.

**The utility meter select is not changing.** Three things to check: the select
is nominated under Track usage by rate; the tariff names on the meter exactly match
your rate names; and the log — a mismatch is logged along with the options the
select actually offers.

**Public holidays are being priced as ordinary days.** Nominate a holiday sensor
under the general settings. Without one the day option is not offered, and
holidays follow the calendar weekday.

**Nothing is counting my allowance or my demand charge.** Check that a rate
declares one and that the plan's grid import meter is nominated — mandatory
for every plan, asked once on the Fixed charges screen (setup) or Supply
charge, tax, plan dates, sensors (Configure), not per rate. Without it the
scheduled price and the declared cap or rate are still published, for a
consumer to apply the rule itself. An export rate additionally needs the
export meter nominated in the same place — optional, since a plan can export
without any export rate declaring a demand charge or an allowance.

**The count does not match my bill.** It will not exactly. It counts the
meter you nominated, on this integration's own clock, and a period allowance
belongs to the time slot — each occurrence of a capped period has its own,
and nothing carries between periods, days or billing cycles unless you
declared it as a monthly allowance. Your retailer meters and resets on their
own terms.

**A capped rate runs through midnight.** Configure will say so. A period cannot
cross midnight here, so a capped stretch from 22:00 to 02:00 is two periods
naming the same rate, and the count resets between them — that one stretch gets
its full allowance twice. Whether that is right depends on how your retailer
counts it, so it warns rather than refusing to save.

**The allowance reads high after a restart.** It should not — it is restored. If
it does, the import energy sensor was unavailable at the moment of restore. It
corrects itself at midnight.

**You want to see the whole state.** The entry's three-dot menu → **Download
diagnostics**. It contains the plan, the strip, every validation problem, what
is resolved right now with a trace of why, and the next 24 hours. For just
the rates, export rates and time periods as plain CSV — for a spreadsheet, or
an inverter's own tariff screen — call the
`abode_power_tariffs.export_rates_csv` action instead.

---

## Known limitations

- **Tiered and block rates are supported only without a timetable.** A plan
  with "Is this power plan based on a single rate?" ticked gets a price for
  the first part of usage and a different price for the rest, on both import
  and export. A timetabled rate does not yet support a second tier.
- **There is no demand ratchet.** A declared demand rate is charged on this
  cycle's measured peak alone; some commercial and overseas tariffs bill on
  the higher of that and a floor derived from past cycles. Researched and not
  built — it earns nothing on an Australian residential tariff.
- **Dynamic tariffs are not connected yet.** The interface is shaped for it —
  the action's response matches Amber's — but no adapter is written. A static
  plan is the only price source today.
- **Public holidays are resolved for today only**, because a workday binary
  sensor reports one day at a time. Holidays inside the forward series are
  treated as ordinary days.
- **No custom card ships with the integration.** The daily rate card is a
  worked example (see A daily rate card, above) built on
  [ApexCharts Card](https://github.com/RomRider/apexcharts-card), a separate
  HACS install, and `sensor.<name>_today_schedule`, which the integration
  does publish — there is no bundled Lovelace card of its own.
- **No text import.** With rates defined once, a time period is three fields.
  `abode_power_tariffs.export_rates_csv` exports the plan as CSV, and
  Diagnostics still bundles the same CSV alongside the full state for backup
  and support — but there is no import back the other way.
- **No bill reconciliation.** Accumulating figures are this integration's own
  estimate, measured on its own clock; they will not reproduce an invoice.

---

## Supported plans

Anything expressible as named rates over non-overlapping time periods:

- Flat rate
- Time of use, any number of rates
- Weekday, weekend and public holiday variation, as separate timetables in one plan
- Seasonal variation, including ranges wrapping the new year
- Free or discounted time periods, with or without an energy cap on the slot
- Separate import and feed-in prices, each with their own timetable and
  periods, and each with their own cap and price past it
- A no-timetable plan: one price for the first part of usage, another for the
  rest of the billing period, for import and export alike
- Controlled load and second circuits, as additional channels
- Plans with a validity period, so past costs stay right after a reprice

---

## Development

```bash
python3 -m unittest discover -s tests -p "test_*.py"
ruff check custom_components tests
mypy --config-file mypy.ini custom_components/abode_power_tariffs/plan.py
```

Seven modules import nothing from Home Assistant — `const`, `plan`, `validate`,
`intervals`, `allowance`, `strip`, `serialise` — and they hold every decision.
They are tested without Home Assistant installed, and a test fails the build if
one of them grows a `homeassistant` import.

`tests/test_attributes.py` parses the source and fails when an attribute is read
and never assigned, following base classes within the package. It exists because
exactly that bug shipped once, past both ruff and mypy, because the file cannot
be imported without Home Assistant.

Quality scale progress is tracked in
`custom_components/abode_power_tariffs/quality_scale.yaml` against all 54 rules.

---

## Licence

Apache 2.0. See `LICENSE` and `ATTRIBUTION.md`.
