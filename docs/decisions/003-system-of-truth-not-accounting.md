# DR-003: A system of truth, not an accounting system

| | |
|---|---|
| Status | Accepted |
| Since | First release; restated in `ARCHITECTURE.md`, session eleven (2026-08-23) |
| Origin | The fundamental precept |
| Related | DR-021, DR-023, DR-026 |

## Decision

The integration reports the true cost of electricity at a point in time. Any
accumulation it does, a demand ledger or an allowance ledger, exists only so
it can report that point-in-time cost truthfully. It does not keep a running
tally for its own sake, and it is not a bookkeeping system standing in for a
bill. Every accumulating entity says that what it publishes is an estimate
measured here, which will not reconcile with a bill.

## Why

Session seven revoked the two rules that kept the integration a pure reporter
(DR-021, DR-026). A source of truth that declares a cap cannot state the
current price without knowing whether the cap is spent, so it has to count.
Without a precept saying why it counts, every accumulated figure invites the
next one, and the integration drifts into a billing system it can never be
right about: it reads a household meter, not the retailer's.

## Rejected

- **Pure reporter, no accumulation (the original rules 7 and 11).** Cannot
  report the price past an allowance, or what a demand window has cost.
- **A full accounting system.** It will not reconcile with a bill, and
  pretending otherwise is a confident wrong answer.

## Consequences

A proposed figure has to say what point-in-time cost it lets the integration
report truthfully. A figure that only exists to be summed later belongs to a
consumer.

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `sensor.py:51` - `ESTIMATE_NOTE` - the statement every accumulating entity carries
- `sensor.py:479` - `_AccumulatingSensor` - the base that attaches it
