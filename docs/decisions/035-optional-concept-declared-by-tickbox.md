# DR-035: An optional concept is declared by a tickbox, never by a value

| | |
|---|---|
| Status | Accepted |
| Since | Demand at 0.8.5 (P27); allowance at 0.8.10 (P36 Part A) |
| Origin | P36 Part A |
| Related | DR-021, DR-023 |

## Decision

Whether a rate has a demand charge or an allowance is declared by a tickbox.
The tickbox gates the fields that describe it. Ticked is what makes it a
demand rate or a capped rate, not the size of a number; unticked clears it,
whatever the number box still holds.

## Why

The rate form's fallback select always carried a value, so every uncapped
rate was stored with a fallback the user never chose, and a fallback was
asked of every rate with a sibling while never offered on a single-rate
timetable. A required control on an optional concept invents data. And zero
is a legitimate declaration: a demand window can be declared before the
household knows its price.

## Rejected

- **Infer the declaration from a non-zero value.** Zero is a real value.
- **Always show the fallback select.** Writes a choice nobody made.

## Consequences

A ticked box with zero typed is a declared-zero cap or demand price. The
fallback select accepts a custom value, so a single-rate timetable can still
declare what it falls back to.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `config_flow.py:200-201` - `CONF_HAS_ALLOWANCE` - the tickbox decides
- `plan.py:218` - `has_demand_charge` - the period declaration, not the price
