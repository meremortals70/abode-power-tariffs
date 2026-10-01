# DR-018: A price that does not resolve is absent, never zero

| | |
|---|---|
| Status | Accepted |
| Since | 0.8.10 (P36 Part B, 2026-08-23) |
| Origin | Finding A4 |
| Related | DR-004, DR-014 |

## Decision

When no price resolves (no timetable matched, no period covers the minute, or
the period names a rate that does not exist), the price is `None` and the
sensor is unavailable. In the forecast series, an interval with no resolved
price is left out entirely, never sent as zero or null.

## Why

Zero is a legitimate price. `Plan.export_at` returned `0.0` for all three
failures, so a genuine zero feed-in price was indistinguishable from a broken
plan. While building the fix, `ExportPriceSensor` was found to be inheriting
the import sensor's attributes wholesale, so its `forecast` had never shown
export prices.

## Rejected

- **Send `null` in the forecast.** evcc's `Rate.Price` is a plain `float64`;
  a null either fails to parse or is coerced back to `0.0`, the same
  fabricated zero relocated. A missing entry is a known, tolerated case on
  evcc's side (evcc-io/evcc issue #24914).
- **Keep `0.0` and add a flag.** Every consumer that reads only the price
  still gets the wrong answer.

## Consequences

The export side mirrors the import side's `Resolution | None` shape, and has
its own resolution, `ExportResolution`, so its attributes are genuinely its
own.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `plan.py:830` - `export_resolve` - None when nothing resolves
- `plan.py:675` - `ExportResolution` - the export side's own context
- `sensor.py:249` - `native_value` - None, not $0.00
- `intervals.py:103` - `as_evcc_entry` - None, filtered out by the caller
