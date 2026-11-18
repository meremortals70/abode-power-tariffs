# DR-051: A flat all-day feed-in declaration has its own ledger identity

| | |
|---|---|
| Status | Accepted |
| Since | 0.9.13 (2026-11-18) |
| Origin | Register entry 9 |
| Related | DR-014, DR-016, DR-021, DR-023 |

## Decision

A timetable's flat all-day feed-in declaration, with its cap and fallback
price, is counted under `plan.timetable.export`: three segments, no rate name.
It carries its own declared allowance period, `export_allowance_period`,
defaulting to `slot`; the block-plan setup screens declare `month`. The count
and the effective price are published on the export price sensor.

## Why

The declaration is not a `Rate`. It is three fields on the timetable: the
all-day tickbox, the cap and the fallback price. Every ledger in the model is
keyed on a four-segment rate identifier, so there was nothing to key this one
on. Nothing was counted, the count stayed at zero and the fallback price never
took effect - a household on a capped flat feed-in tariff saw a price that
never dropped.

`slug` never leaves a separator inside a segment, so a three-segment key
cannot collide with a four-segment rate identifier. The missing fourth segment
says this declaration belongs to the timetable itself.

The household also has to say whether the retailer counts the cap per day or
per cycle. An all-day declaration under the model default of `slot` has one
occurrence a day, but the block-plan setup screens promise "the rest of the
billing period", so they declare `month`. Configure keeps both choices.

## Rejected

- **Invent a synthetic rate name for the declaration.** It would appear as a
  period's rate and be published as a rate the plan does not contain, making
  the plan say something false.
- **Key it on the timetable's name alone.** Two timetables can use the same
  name; the plan segment is needed to keep them apart.
- **Give every export rate an allowance period in this build.** A named
  `ExportRate` keeps its hard-coded slot cap. That is a separate change, not
  part of this one.

## Consequences

The declaration now has a count and a fallback price like any other capped
flow. DR-023 is marked **Partly** and superseded in part by this record: it
says one ledger per rate, and this is a second identity that is not a rate.

A reading that straddles midnight under a daily flat cap is credited wholly to
the day it arrives: the flat shape has no midnight boundary to split at
(DR-050's boundary walk has nothing to find).

## In the code

Checked against: 0.9.13 (2026-11-18). **Conforms.**

- `plan.py:144` - `all_day_export_key` - the three-segment ledger identity
- `plan.py:522` - `export_same_all_day` - the declaration's tickbox
- `plan.py:545` - `export_allowance_period` - its declared period, `slot` by default
- `plan.py:763` - `allowance_period` - a flat declaration reads it; a named rate stays slot-scoped
- `coordinator.py:1281` - `resolution.ledger_key` - where the export stretch is credited
- `coordinator.py:1283` - `resolution.allowance_kwh` - the cap, when one is declared
- `config_flow.py:1012` - `CONF_EXPORT_ALLOWANCE_PERIOD` - the block plan declares `month`
- `config_flow.py:1524` - `CONF_EXPORT_ALLOWANCE_PERIOD` - the feed-in screen keeps the choice
- `sensor.py:313` - `allowance_counted` - says whether a meter is counting it
