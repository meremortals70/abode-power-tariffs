# DR-040: Setup is a linear flow; Configure is menus

| | |
|---|---|
| Status | Accepted |
| Since | Settled before 0.8.4 |
| Origin | Settled |
| Related | DR-033, DR-041, DR-042 |

## Decision

Setup is a linear sequence of screens. Configure, used after the plan
exists, is menu-driven.

## Why

Menus give nothing on a cancel. A setup cancelled partway through a menu
leaves the user with nothing created and no trace of what they entered,
which was the problem being solved. A short linear setup is the mitigation
for a dialog that cannot warn before it closes (DR-042).

## Rejected

- **Menu-based setup.** Above.

## Consequences

Setup asks for a working plan and defers the rest to Configure, where each
step commits as it leaves (DR-033).

## In the code

Checked against: 0.9.11 RC2 (2026-10-01). **Conforms.**

- `config_flow.py:762` - `async_step_user` - the first of a linear sequence
- `config_flow.py:1805` - `async_show_menu` - Configure's menus
