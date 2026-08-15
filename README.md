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
| `sensor.<name>_rate` | The name of the rate in force — `peak`, `free`, whatever you called it |
| `sensor.<name>_next_rate_change` | When it next changes |
| `sensor.<name>_daily_supply_charge` | Your daily supply charge |
| `sensor.<name>_allowance_remaining` | kWh left of a capped free time period, when you have one |
| `binary_sensor.<name>_<constraint>` | One per rule you declared — see below |
| `sensor.<name>_supply_charge_today` and `..._supply_charge_energy` | Optional pair that gets the daily supply charge into the Energy dashboard |

Plus an action, `abode_power_tariffs.get_intervals`, returning the forward
series.

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

## Building your plan

Settings → Devices & services → Abode Power Tariffs → **Configure**.

The 24-hour strip is shown before you choose anything, and again on every screen
that touches time periods, so a gap or an overlap is visible the moment you make it:

```
Every day
        00    03    06    09    12    15    18    21    24
        ████████████░░░░░░░░░░▒▒▒▒▒▒░░░░████████████░░░░░░
        cheap       standard  free  std peak        standard

  Coverage: complete. 6 time periods, no gaps, no overlaps.
```

### Rates first

**A rate is defined once and pointed at by any number of time periods.** Change the
peak price and it changes everywhere.

| Field | Notes |
|---|---|
| Name | Free text. Becomes an option on the rate sensor. Match your `utility_meter` tariff names if you use them |
| Import price | Cents per kWh, as bills quote it. Published in dollars per kWh, as the Energy dashboard wants it |
| Export price | Same |
| Constraints | Comma separated. Each becomes a binary sensor. See below |
| Coasting permitted | For consumers that ask whether this is a good moment to stop drawing power |
| Demand charge time period | A flag only. The $/kW/month arithmetic is out of scope |
| Daily energy allowance | Leave empty for none. Some plans give a time period free only up to a cap |
| Rate beyond the allowance | Required when there is an allowance |

### Then time periods

Three fields: start, end, rate. Start is included, end is not. A time period running
to midnight ends at 00:00.

The time periods in a day pattern must cover 00:00 to 24:00 exactly once. The plan will
not save otherwise, and the strip tells you which hours are missing.

### Day patterns

**"Same every day" is on by default.** Leave it on unless weekends, weekdays or
public holidays are priced differently — then turn it off and pick the days.

For the common Australian shape — weekdays one way, weekends and public holidays
another — build the weekday pattern, then use **Duplicate day pattern** and change the
rates on the time periods that differ.

Public holidays need a holiday sensor nominated under the general settings. Home
Assistant's built-in **Workday** integration provides one; it is off on a public
holiday, and the day option only appears once you have nominated a sensor.

### Seasons

A day pattern can carry a date range, entered as `MM-DD`. A range may wrap the new
year — `11-01` to `03-31` is summer in the southern hemisphere. A seasonal day
set wins over a year-round one on the dates it covers.

### General settings

Daily supply charge, whether prices include tax and at what rate, the plan's
validity dates, the holiday sensor and the import energy sensor.

**Validity dates matter more than they look.** When your retailer reprices, set
`valid to` on the old plan and make a new channel for the new one. Historical
cost figures then stay correct against the price that was actually in force.

Currency comes from your Home Assistant configuration. It is never asked for.

---

## Constraints

A constraint is a rule you declare on a rate. Name it whatever you like —
`no_grid_import`, `grid_charge_battery`, `precool_opportunity`. Each becomes a
binary sensor that is on while a rate carrying it is in force.

This is what battery, hot water and EV automations should trigger on, instead of
a clock comparison. When the plan moves, they move with it and you edit nothing.

Note what they are: **rules you declared**, not decisions the integration made.
It reports that your rule now applies.

---

## Energy dashboard

**Grid consumption cost.** Settings → Dashboards → Energy → your grid
consumption source → **Use an entity with current price** → pick
`sensor.<name>_import_price`. No template sensor.

**Return to grid.** The same, with `sensor.<name>_export_price`.

**Daily supply charge.** The Energy dashboard has no field for a fixed daily
charge — it is one of its longest-running open requests. Turn on **Create the
supply charge pair** under Track usage by rate and you get two entities: an
accumulating cost and a matching token energy sensor. Add
`sensor.<name>_supply_charge_energy` as a second grid consumption source and
choose **use an entity tracking the total costs**, pointing at
`sensor.<name>_supply_charge_today`. The supply charge then appears in the
dashboard's figures.

**Usage split by rate.** Create a `utility_meter` helper with your rate names as
its tariffs. It makes one meter per rate plus a select naming which is in force.
Nominate that select under Track usage by rate and the integration sets it at each
time period boundary — the automation people normally write for this disappears.

That select is the only thing this integration ever writes, it is off by
default, and it writes only to selects you nominated.

---

## evcc

Both price sensors carry a `forecast` attribute holding the next 24 hours as
`{start, end, value}` with UTC timestamps, which is the shape evcc reads:

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

## Batteries and inverters

Posture control stays outside this integration: a backup reserve percentage
depends on state of charge and intent, which the plan knows nothing about, and
the primitives differ by vendor.

A blueprint is provided instead. Import it by pasting this URL into
**Settings → Automations & scenes → Blueprints → Import blueprint**:

```
https://github.com/meremortals70/abode-power-tariffs/blob/main/blueprints/automation/abode_power_tariffs/inverter_posture.yaml
```

One instance per posture. It triggers on a constraint sensor and sets backup
reserve, operation mode, grid charging and the export rule — each optional, each
targeted at your own entities.

> **Do not run a blueprint instance and the automation it replaces at the same
> time.** Two writers on a backup reserve produces no error, only odd
> behaviour. Import, configure, disable the original, watch a full day, then
> delete it.

**Read the options off the entity before typing them.** An operation mode option
that does not exist raises an error and stops the sequence where it stands, with
the earlier steps applied and the later ones not.

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
    rate: peak
    constraints: [no_grid_import]
    coasting_permitted: true
    allowance_kwh: null
    day_set: Every day
    forecast: false
```

`per_kwh` is in dollars and the field names match the core Amber Electric
integration, so anything already written against that shape works here.

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
    entity_id: sensor.electricity_allowance_remaining
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

The next time period boundary is computed and scheduled; when it fires, every entity
updates and the following boundary is scheduled. There is also a midnight
trigger that resets the daily allowance and the supply-charge accumulator, and
an update whenever the nominated holiday or import energy sensor changes.

Time periods are wall-clock times, which is what you want: a peak time period is 16:00
local on both sides of a daylight-saving transition. The forward series is
generated in real instants, so a 23-hour day is an hour short and a 25-hour day
repeats one, with no gap, no overlap and no duplicated interval either way.

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

**The allowance reads high after a restart.** It should not — it is restored. If
it does, the import energy sensor was unavailable at the moment of restore. It
corrects itself at midnight.

**You want to see the whole state.** The entry's three-dot menu → **Download
diagnostics**. It contains the plan, the strip, every validation problem, what
is resolved right now with a trace of why, and the next 24 hours.

---

## Known limitations

- **Tiered and block rates are not supported.** First N kWh at one rate and the
  remainder at another. The rate model has room for it; it is not built.
- **Demand charges are a flag only.** A time period can be marked as one so a
  controller can avoid a coincident peak, but the $/kW/month is not computed.
  `perosb/power_max_tracker` already tracks the monthly maximum.
- **Dynamic tariffs are not connected yet.** The interface is shaped for it —
  the action's response matches Amber's — but no adapter is written. A static
  plan is the only price source today.
- **Public holidays are resolved for today only**, because a workday binary
  sensor reports one day at a time. Holidays inside the forward series are
  treated as ordinary days.
- **There is no dashboard card.** The strip lives in the configuration screens,
  where the question it answers is asked. On a dashboard, the rate and
  next-rate-change sensors already say what is in force.
- **No text or CSV import.** With rates defined once, a time period is three fields.
  Diagnostics renders the plan as CSV for backup and for support.
- **No bill reconciliation.** It reports the rate in force; it does not
  reproduce an invoice.

---

## Supported plans

Anything expressible as named rates over non-overlapping time periods:

- Flat rate
- Time of use, any number of rates
- Weekday, weekend and public holiday variation
- Seasonal variation, including ranges wrapping the new year
- Free or discounted time periods, with or without a daily energy cap
- Separate import and export prices per rate
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
The rules themselves are summarised in `docs/HA-DEVELOPER-RULES.md`.

---

## Licence

Apache 2.0. See `LICENSE` and `ATTRIBUTION.md`.
