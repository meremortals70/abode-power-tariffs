# DR-052: Startup does not wait for a meter

| | |
|---|---|
| Status | Accepted |
| Since | 0.9.13 (2026-11-18) |
| Origin | Register entry 5 |
| Related | DR-003, DR-006, DR-021 |

## Decision

Entry setup reads each counted meter once, without waiting. A meter that is
not readable at that moment is retried in a background task: the same three
attempts, five seconds apart, but behind the entry instead of in front of it.
The retry fills only an empty baseline. If all attempts fail, a data gap is
opened naming the side that could not be read. The tasks are cancelled on
unload.

## Why

Setup used to wait on each counted meter to publish a first state, retrying in
front of the entry. A slow or absent meter held up the entire integration: the
plan, its boundaries, its prices and its forecasts all waited on something
none of them depend on. On a reload the meter is already publishing, so this
only ever cost a cold start - which is exactly when the user is watching.

Home Assistant does not guarantee load order, so a first-state race is real
and must still be handled. It does not follow that the entry must wait for it.
Moving the wait behind the entry keeps the recovery and removes the stall.

The retry must not overwrite a baseline a state change has already filled.
`_accumulate_energy` records the reading from a state change as the baseline;
replacing it would drop the energy drawn between the two readings without
crediting it to anything.

## Rejected

- **Keep the wait in setup, with a shorter timeout.** Still puts the plan at
  the mercy of an unrelated integration, and a timeout would either guess too
  short and open a false gap or too long and keep the stall.
- **Open the gap immediately when the first read fails.** That reports a data
  gap for a startup race that is about to resolve, and marks the cycle
  incomplete for no reason. Deferring the wait must not hide a genuine failure,
  so the gap still opens when the retries are spent.
- **Let the retry overwrite the baseline unconditionally.** It would throw
  away energy already credited, as described above.

## Consequences

The plan, its prices and its forecasts are available as soon as the entry sets
up, whether or not a meter is publishing. A genuinely unreadable meter is still
reported after the retries, with the import or export side named. A reload
cancels any pending task, so no retry runs against an unloaded coordinator.

## In the code

Checked against: 0.9.13 (2026-11-18). **Conforms.**

- `coordinator.py:815` - `_seed_energy_total` - one read per counted meter, no waiting
- `coordinator.py:847` - `_retry_meter_later` - creates the background task
- `coordinator.py:853` - `_retry_meter` - three attempts, then opens the named gap
- `coordinator.py:881` - `_set_meter_baseline` - fills only an empty baseline
- `coordinator.py:257` - `_meter_tasks` - the tasks held for cancellation
- `coordinator.py:295` - `async_shutdown` - cancels them on unload
