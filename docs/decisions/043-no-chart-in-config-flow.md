# DR-043: There is no chart in the config flow

| | |
|---|---|
| Status | Accepted |
| Since | Settled |
| Origin | Settled |
| Related | DR-044 |

## Decision

The config flow shows no chart of the plan. The visual belongs in Lovelace:
the rate sensor is an enum, so a built-in history-graph card draws it as a
coloured timeline with a real time axis.

## Why

The config dialog's sanitiser allows only `svg[xmlns,width,height]`,
`path[transform,stroke,d]` and `img[src]`: no `rect`, no `text`, no `fill`,
no `stroke-width`, no `viewBox`. An `img` source goes through the xss
library's default check, which permits only `http(s)://`, `/`, `#`,
`mailto:` and `tel:`, so a data URI is stripped.

## Rejected

- **Characters.** Emoji width is not a fixed multiple of a monospace
  character and varies by font and platform; the bar drifted three hours
  against the ruler on Brave on Windows, and no constant fixes it for
  everyone.
- **Inline SVG.** Built and demonstrated, exact to the minute, with bands as
  stroked paths and times as seven-segment digits. Rejected as too much
  machinery in a config screen.
- **A served image.** A URL starting with `/` passes the filter, so an HTTP
  view generating the SVG would work. Rejected as real work, and an odd thing
  for a core integration to do.

## Consequences

The dashboard examples in `examples/` draw the day; the config flow shows the
plan as a table (DR-044).

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `strip.py:3` - `There used to be a coloured` - the removed bar, and why
