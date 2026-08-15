"""Configuration and options flow.

The plan is always on screen: the Configure menu shows the 24-hour strip for
every day set before anything is chosen, and every screen that touches windows
shows it again, so a gap or an overlap is visible at the moment it is made.
"""

from __future__ import annotations

import copy
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    ALL_DAY_TOKENS,
    CONF_COASTING_PERMITTED,
    CONF_CONSTRAINTS,
    CONF_DAILY_ALLOWANCE_KWH,
    CONF_DAY_SETS,
    CONF_DAYS,
    CONF_DEMAND_WINDOW,
    CONF_END,
    CONF_EXPORT_ALLOWANCE_KWH,
    CONF_EXPORT_CENTS,
    CONF_FALLBACK_RATE,
    CONF_GST_PERCENT,
    CONF_HOLIDAY_SENSOR,
    CONF_IMPORT_CENTS,
    CONF_IMPORT_ENERGY_SENSOR,
    CONF_NAME,
    CONF_PLAN_NAME,
    CONF_PRICES_INCLUDE_GST,
    CONF_RATE,
    CONF_RATES,
    CONF_SEASON_FROM,
    CONF_SEASON_TO,
    CONF_START,
    CONF_SUPPLY_CHARGE_CENTS,
    CONF_SUPPLY_CHARGE_ENTITIES,
    CONF_TARIFF_SELECTS,
    CONF_VALID_FROM,
    CONF_VALID_TO,
    CONF_WINDOWS,
    DEFAULT_GST_PERCENT,
    DOMAIN,
    MINUTES_PER_DAY,
    WEEKDAY_TOKENS,
)
from .plan import Plan, PlanError, format_time, parse_time
from .strip import render_day_set, render_plan, render_rate_plan_card
from .validate import validate_plan

SEEDED_OPTIONS: dict[str, Any] = {
    CONF_RATES: [
        {
            CONF_NAME: "standard",
            CONF_IMPORT_CENTS: 30.0,
            CONF_EXPORT_CENTS: 0.0,
            CONF_CONSTRAINTS: [],
            CONF_COASTING_PERMITTED: True,
        }
    ],
    CONF_DAY_SETS: [
        {
            CONF_NAME: "Every day",
            CONF_DAYS: list(ALL_DAY_TOKENS),
            CONF_WINDOWS: [{CONF_START: "00:00", CONF_END: "24:00", CONF_RATE: "standard"}],
        }
    ],
    CONF_SUPPLY_CHARGE_CENTS: 0.0,
    CONF_PRICES_INCLUDE_GST: True,
    CONF_GST_PERCENT: DEFAULT_GST_PERCENT,
}


def _time_to_minutes(value: str, *, is_end: bool) -> int:
    """Convert a time selector value to minutes since midnight.

    A window ending at midnight is the end of the day, not the start of it, so
    an end of 00:00 becomes 24:00. There is no other way to express it with a
    time picker.
    """
    trimmed = ":".join(str(value).split(":")[:2])
    minutes = parse_time(trimmed)
    if is_end and minutes == 0:
        return MINUTES_PER_DAY
    return minutes


def _minutes_to_selector(minutes: int) -> str:
    """Convert minutes since midnight to a time selector value."""
    if minutes >= MINUTES_PER_DAY:
        return "00:00:00"
    return f"{format_time(minutes)}:00"


def _plan_from_options(options: dict[str, Any], name: str) -> Plan:
    return Plan.from_dict({**options, CONF_NAME: name})


class AbodePowerTariffsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one metering channel."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the channel name and seed a plan that already validates."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_PLAN_NAME].strip()
            if not name:
                errors[CONF_PLAN_NAME] = "name_required"
            else:
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                options = copy.deepcopy(SEEDED_OPTIONS)
                # Seeded so the integration is valid and useful before anything
                # is configured; every figure is then the user's to change.
                return self.async_create_entry(
                    title=name,
                    data={CONF_PLAN_NAME: name},
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PLAN_NAME, default="Electricity"): selector.TextSelector()}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AbodePowerTariffsOptionsFlow:
        """Return the options flow."""
        return AbodePowerTariffsOptionsFlow()


class AbodePowerTariffsOptionsFlow(OptionsFlow):
    """Edit the plan."""

    def __init__(self) -> None:
        """Initialise the working copy lazily, on first step."""
        self._working: dict[str, Any] | None = None
        self._day_set_index: int | None = None
        self._window_index: int | None = None
        self._rate_index: int | None = None

    # ------------------------------------------------------------- utilities

    @property
    def working(self) -> dict[str, Any]:
        """Return the in-progress copy of the options."""
        if self._working is None:
            self._working = copy.deepcopy(dict(self.config_entry.options))
            self._working.setdefault(CONF_RATES, [])
            self._working.setdefault(CONF_DAY_SETS, [])
        return self._working

    def _plan(self) -> Plan | None:
        try:
            return _plan_from_options(self.working, self.config_entry.title)
        except PlanError:
            return None

    def _placeholders(self) -> dict[str, str]:
        plan = self._plan()
        if plan is None:
            return {"plan": "The stored plan cannot be read. Edit a rate to rebuild it."}
        problems = validate_plan(plan)
        summary = render_plan(plan)
        if problems:
            summary += "\n\nProblems:\n" + "\n".join(f"  {p}" for p in problems)
        return {"plan": summary}

    def _rates(self) -> list[dict[str, Any]]:
        return self.working[CONF_RATES]

    def _day_sets(self) -> list[dict[str, Any]]:
        return self.working[CONF_DAY_SETS]

    def _rate_names(self) -> list[str]:
        return [str(rate.get(CONF_NAME, "")) for rate in self._rates()]

    # ------------------------------------------------------------------ menu

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the plan and the menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "rates_menu",
                "day_sets_menu",
                "windows_pick_day_set",
                "general",
                "meters",
                "rate_plan_card",
                "save",
            ],
            description_placeholders=self._placeholders(),
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store the plan."""
        plan = self._plan()
        if plan is None or validate_plan(plan):
            return self.async_show_menu(
                step_id="init",
                menu_options=[
                    "rates_menu",
                    "day_sets_menu",
                    "windows_pick_day_set",
                    "general",
                    "meters",
                    "rate_plan_card",
                    "save",
                ],
                description_placeholders=self._placeholders(),
            )
        return self.async_create_entry(title="", data=self.working)

    async def async_step_rate_plan_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the plan in the shape an inverter's tariff screen asks for."""
        if user_input is not None:
            return await self.async_step_init()
        plan = self._plan()
        card = render_rate_plan_card(plan) if plan else "The plan cannot be read."
        return self.async_show_form(
            step_id="rate_plan_card",
            data_schema=vol.Schema({}),
            description_placeholders={"card": card},
        )

    # ----------------------------------------------------------------- rates

    async def async_step_rates_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, edit or remove a rate."""
        return self.async_show_menu(
            step_id="rates_menu",
            menu_options=["rate_add", "rate_pick", "rate_remove", "init"],
            description_placeholders={
                "rates": "\n".join(
                    f"  {rate[CONF_NAME]}  "
                    f"{float(rate.get(CONF_IMPORT_CENTS) or 0):.2f} c/kWh import, "
                    f"{float(rate.get(CONF_EXPORT_CENTS) or 0):.2f} c/kWh export"
                    for rate in self._rates()
                )
                or "  none yet"
            },
        )

    async def async_step_rate_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a rate to edit."""
        if not self._rates():
            return await self.async_step_rate_add()
        if user_input is not None:
            self._rate_index = self._rate_names().index(user_input[CONF_NAME])
            return await self.async_step_rate_add()
        return self.async_show_form(
            step_id="rate_pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._rate_names())
                    )
                }
            ),
        )

    async def async_step_rate_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a rate, or edit the one chosen."""
        errors: dict[str, str] = {}
        existing: dict[str, Any] = (
            self._rates()[self._rate_index] if self._rate_index is not None else {}
        )

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            clashes = [
                index
                for index, rate in enumerate(self._rates())
                if rate[CONF_NAME] == name and index != self._rate_index
            ]
            if not name:
                errors[CONF_NAME] = "name_required"
            elif clashes:
                errors[CONF_NAME] = "rate_exists"
            else:
                record = {
                    CONF_NAME: name,
                    CONF_IMPORT_CENTS: user_input[CONF_IMPORT_CENTS],
                    CONF_EXPORT_CENTS: user_input.get(CONF_EXPORT_CENTS, 0.0),
                    CONF_CONSTRAINTS: [
                        item.strip()
                        for item in str(user_input.get(CONF_CONSTRAINTS, "")).split(",")
                        if item.strip()
                    ],
                    CONF_COASTING_PERMITTED: user_input[CONF_COASTING_PERMITTED],
                    CONF_DEMAND_WINDOW: user_input[CONF_DEMAND_WINDOW],
                    CONF_DAILY_ALLOWANCE_KWH: user_input.get(CONF_DAILY_ALLOWANCE_KWH) or None,
                    CONF_EXPORT_ALLOWANCE_KWH: user_input.get(CONF_EXPORT_ALLOWANCE_KWH) or None,
                    CONF_FALLBACK_RATE: user_input.get(CONF_FALLBACK_RATE) or None,
                }
                if self._rate_index is None:
                    self._rates().append(record)
                else:
                    previous = self._rates()[self._rate_index][CONF_NAME]
                    self._rates()[self._rate_index] = record
                    if previous != name:
                        self._rename_rate(previous, name)
                self._rate_index = None
                return await self.async_step_rates_menu()

        fallback_options = [name for name in self._rate_names() if name != existing.get(CONF_NAME)]

        schema: dict[Any, Any] = {
            vol.Required(CONF_NAME, default=existing.get(CONF_NAME, "")): selector.TextSelector(),
            vol.Required(
                CONF_IMPORT_CENTS, default=float(existing.get(CONF_IMPORT_CENTS) or 0.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1000, step=0.0001, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_EXPORT_CENTS, default=float(existing.get(CONF_EXPORT_CENTS) or 0.0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1000, step=0.0001, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_CONSTRAINTS,
                default=", ".join(existing.get(CONF_CONSTRAINTS) or []),
            ): selector.TextSelector(),
            vol.Required(
                CONF_COASTING_PERMITTED,
                default=bool(existing.get(CONF_COASTING_PERMITTED, True)),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_DEMAND_WINDOW, default=bool(existing.get(CONF_DEMAND_WINDOW, False))
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_DAILY_ALLOWANCE_KWH,
                description={"suggested_value": existing.get(CONF_DAILY_ALLOWANCE_KWH)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1000, step=0.1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_EXPORT_ALLOWANCE_KWH,
                description={"suggested_value": existing.get(CONF_EXPORT_ALLOWANCE_KWH)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1000, step=0.1, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
        if fallback_options:
            schema[
                vol.Optional(
                    CONF_FALLBACK_RATE,
                    description={"suggested_value": existing.get(CONF_FALLBACK_RATE)},
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=fallback_options)
            )

        return self.async_show_form(
            step_id="rate_add",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    def _rename_rate(self, previous: str, current: str) -> None:
        """Follow a rate rename through into every window that names it."""
        for day_set in self._day_sets():
            for window in day_set.get(CONF_WINDOWS, []):
                if window.get(CONF_RATE) == previous:
                    window[CONF_RATE] = current
        for rate in self._rates():
            if rate.get(CONF_FALLBACK_RATE) == previous:
                rate[CONF_FALLBACK_RATE] = current

    async def async_step_rate_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a rate that no window uses."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME]
            in_use = any(
                window.get(CONF_RATE) == name
                for day_set in self._day_sets()
                for window in day_set.get(CONF_WINDOWS, [])
            )
            if in_use:
                errors[CONF_NAME] = "rate_in_use"
            else:
                self.working[CONF_RATES] = [
                    rate for rate in self._rates() if rate[CONF_NAME] != name
                ]
                return await self.async_step_rates_menu()

        if not self._rate_names():
            return await self.async_step_rates_menu()

        return self.async_show_form(
            step_id="rate_remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._rate_names())
                    )
                }
            ),
            errors=errors,
        )

    # -------------------------------------------------------------- day sets

    async def async_step_day_sets_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, edit, duplicate or remove a day set."""
        return self.async_show_menu(
            step_id="day_sets_menu",
            menu_options=[
                "day_set_add",
                "day_set_pick",
                "day_set_duplicate",
                "day_set_remove",
                "init",
            ],
            description_placeholders=self._placeholders(),
        )

    def _day_set_names(self) -> list[str]:
        return [str(day_set.get(CONF_NAME, "")) for day_set in self._day_sets()]

    async def async_step_day_set_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a day set to edit."""
        if not self._day_sets():
            return await self.async_step_day_set_add()
        if user_input is not None:
            self._day_set_index = self._day_set_names().index(user_input[CONF_NAME])
            return await self.async_step_day_set_add()
        return self.async_show_form(
            step_id="day_set_pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._day_set_names())
                    )
                }
            ),
        )

    async def async_step_day_set_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a day set, or edit the one chosen."""
        errors: dict[str, str] = {}
        existing: dict[str, Any] = (
            self._day_sets()[self._day_set_index] if self._day_set_index is not None else {}
        )
        same_every_day = set(existing.get(CONF_DAYS) or ALL_DAY_TOKENS) == set(ALL_DAY_TOKENS)

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                if user_input["same_every_day"]:
                    days = list(ALL_DAY_TOKENS)
                else:
                    days = list(user_input.get(CONF_DAYS) or [])
                if not days:
                    errors[CONF_DAYS] = "days_required"
                else:
                    record = {
                        CONF_NAME: name,
                        CONF_DAYS: days,
                        CONF_SEASON_FROM: user_input.get(CONF_SEASON_FROM) or None,
                        CONF_SEASON_TO: user_input.get(CONF_SEASON_TO) or None,
                        CONF_WINDOWS: existing.get(CONF_WINDOWS, []),
                    }
                    if self._day_set_index is None:
                        self._day_sets().append(record)
                    else:
                        self._day_sets()[self._day_set_index] = record
                    self._day_set_index = None
                    return await self.async_step_day_sets_menu()

        return self.async_show_form(
            step_id="day_set_add",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=existing.get(CONF_NAME, "Every day")
                    ): selector.TextSelector(),
                    vol.Required(
                        "same_every_day", default=same_every_day
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_DAYS,
                        description={
                            "suggested_value": existing.get(CONF_DAYS) or list(WEEKDAY_TOKENS)
                        },
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(ALL_DAY_TOKENS),
                            multiple=True,
                            translation_key="day_tokens",
                        )
                    ),
                    vol.Optional(
                        CONF_SEASON_FROM,
                        description={"suggested_value": existing.get(CONF_SEASON_FROM)},
                    ): selector.TextSelector(),
                    vol.Optional(
                        CONF_SEASON_TO,
                        description={"suggested_value": existing.get(CONF_SEASON_TO)},
                    ): selector.TextSelector(),
                }
            ),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_day_set_duplicate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Copy a day set and its windows, then open it for editing.

        This is the bulk path: a weekend or a season is usually the same shape
        as an existing day set with different rates on some windows.
        """
        if not self._day_sets():
            return await self.async_step_day_set_add()
        if user_input is not None:
            source = self._day_sets()[self._day_set_names().index(user_input["source"])]
            copied = copy.deepcopy(source)
            copied[CONF_NAME] = str(user_input[CONF_NAME]).strip() or f"{source[CONF_NAME]} copy"
            self._day_sets().append(copied)
            self._day_set_index = len(self._day_sets()) - 1
            return await self.async_step_day_set_add()
        return self.async_show_form(
            step_id="day_set_duplicate",
            data_schema=vol.Schema(
                {
                    vol.Required("source"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._day_set_names())
                    ),
                    vol.Required(CONF_NAME, default="Weekend"): selector.TextSelector(),
                }
            ),
        )

    async def async_step_day_set_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a day set."""
        if not self._day_sets():
            return await self.async_step_day_sets_menu()
        if user_input is not None:
            name = user_input[CONF_NAME]
            self.working[CONF_DAY_SETS] = [
                day_set for day_set in self._day_sets() if day_set[CONF_NAME] != name
            ]
            return await self.async_step_day_sets_menu()
        return self.async_show_form(
            step_id="day_set_remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._day_set_names())
                    )
                }
            ),
        )

    # --------------------------------------------------------------- windows

    async def async_step_windows_pick_day_set(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which day set's windows to edit."""
        if not self._day_sets():
            return await self.async_step_day_set_add()
        if len(self._day_sets()) == 1:
            self._day_set_index = 0
            return await self.async_step_windows_menu()
        if user_input is not None:
            self._day_set_index = self._day_set_names().index(user_input[CONF_NAME])
            return await self.async_step_windows_menu()
        return self.async_show_form(
            step_id="windows_pick_day_set",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._day_set_names())
                    )
                }
            ),
            description_placeholders=self._placeholders(),
        )

    def _current_day_set(self) -> dict[str, Any]:
        index = self._day_set_index or 0
        return self._day_sets()[index]

    def _windows(self) -> list[dict[str, Any]]:
        return self._current_day_set().setdefault(CONF_WINDOWS, [])

    def _window_labels(self) -> list[str]:
        return [
            f"{window.get(CONF_START)}-{window.get(CONF_END)}  {window.get(CONF_RATE)}"
            for window in self._windows()
        ]

    async def async_step_windows_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, edit or remove a window in the chosen day set."""
        return self.async_show_menu(
            step_id="windows_menu",
            menu_options=["window_add", "window_pick", "window_remove", "init"],
            description_placeholders=self._window_placeholders(),
        )

    def _window_placeholders(self) -> dict[str, str]:
        plan = self._plan()
        day_set_name = self._current_day_set().get(CONF_NAME, "")
        if plan is None:
            return {"day_set": day_set_name, "plan": "The plan cannot be read."}
        for day_set in plan.day_sets:
            if day_set.name == day_set_name:
                return {"day_set": day_set_name, "plan": render_day_set(plan, day_set)}
        return {"day_set": day_set_name, "plan": render_plan(plan)}

    async def async_step_window_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a window to edit."""
        if not self._windows():
            return await self.async_step_window_add()
        if user_input is not None:
            self._window_index = self._window_labels().index(user_input["window"])
            return await self.async_step_window_add()
        return self.async_show_form(
            step_id="window_pick",
            data_schema=vol.Schema(
                {
                    vol.Required("window"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._window_labels())
                    )
                }
            ),
            description_placeholders=self._window_placeholders(),
        )

    async def async_step_window_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a window, or edit the one chosen. Three fields, nothing else."""
        errors: dict[str, str] = {}
        existing: dict[str, Any] = (
            self._windows()[self._window_index] if self._window_index is not None else {}
        )

        if not self._rate_names():
            return await self.async_step_rate_add()

        if user_input is not None:
            try:
                start = _time_to_minutes(user_input[CONF_START], is_end=False)
                end = _time_to_minutes(user_input[CONF_END], is_end=True)
            except PlanError:
                errors["base"] = "bad_time"
            else:
                if end <= start:
                    errors[CONF_END] = "end_before_start"
                else:
                    record = {
                        CONF_START: format_time(start),
                        CONF_END: format_time(end),
                        CONF_RATE: user_input[CONF_RATE],
                    }
                    if self._window_index is None:
                        self._windows().append(record)
                    else:
                        self._windows()[self._window_index] = record
                    self._window_index = None
                    return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="window_add",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_START,
                        default=_minutes_to_selector(
                            parse_time(existing[CONF_START]) if existing else 0
                        ),
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_END,
                        default=_minutes_to_selector(
                            parse_time(existing[CONF_END]) if existing else MINUTES_PER_DAY
                        ),
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_RATE,
                        default=existing.get(CONF_RATE, self._rate_names()[0]),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._rate_names())
                    ),
                }
            ),
            errors=errors,
            description_placeholders=self._window_placeholders(),
        )

    async def async_step_window_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a window."""
        if not self._windows():
            return await self.async_step_windows_menu()
        if user_input is not None:
            index = self._window_labels().index(user_input["window"])
            self._windows().pop(index)
            return await self.async_step_windows_menu()
        return self.async_show_form(
            step_id="window_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("window"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._window_labels())
                    )
                }
            ),
            description_placeholders=self._window_placeholders(),
        )

    # --------------------------------------------------------------- general

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Supply charge, tax, validity and the holiday sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.working[CONF_SUPPLY_CHARGE_CENTS] = user_input[CONF_SUPPLY_CHARGE_CENTS]
            self.working[CONF_PRICES_INCLUDE_GST] = user_input[CONF_PRICES_INCLUDE_GST]
            self.working[CONF_GST_PERCENT] = user_input[CONF_GST_PERCENT]
            self.working[CONF_VALID_FROM] = user_input.get(CONF_VALID_FROM) or None
            self.working[CONF_VALID_TO] = user_input.get(CONF_VALID_TO) or None
            self.working[CONF_HOLIDAY_SENSOR] = user_input.get(CONF_HOLIDAY_SENSOR) or None
            self.working[CONF_IMPORT_ENERGY_SENSOR] = (
                user_input.get(CONF_IMPORT_ENERGY_SENSOR) or None
            )
            plan = self._plan()
            if plan is not None and any(
                "validity" in str(problem) for problem in validate_plan(plan)
            ):
                errors[CONF_VALID_TO] = "validity_backwards"
            else:
                return await self.async_step_init()

        options = self.working
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SUPPLY_CHARGE_CENTS,
                        default=float(options.get(CONF_SUPPLY_CHARGE_CENTS) or 0.0),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=1000, step=0.01, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_PRICES_INCLUDE_GST,
                        default=bool(options.get(CONF_PRICES_INCLUDE_GST, True)),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_GST_PERCENT,
                        default=float(options.get(CONF_GST_PERCENT) or DEFAULT_GST_PERCENT),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=100, step=0.1, mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_VALID_FROM,
                        description={"suggested_value": options.get(CONF_VALID_FROM)},
                    ): selector.DateSelector(),
                    vol.Optional(
                        CONF_VALID_TO,
                        description={"suggested_value": options.get(CONF_VALID_TO)},
                    ): selector.DateSelector(),
                    vol.Optional(
                        CONF_HOLIDAY_SENSOR,
                        description={"suggested_value": options.get(CONF_HOLIDAY_SENSOR)},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    ),
                    vol.Optional(
                        CONF_IMPORT_ENERGY_SENSOR,
                        description={"suggested_value": options.get(CONF_IMPORT_ENERGY_SENSOR)},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
                }
            ),
            errors=errors,
        )

    # ---------------------------------------------------------------- meters

    async def async_step_meters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Nominate utility meter tariff selects, and the supply-charge pair.

        Driving a select is the only write this integration performs, and only
        to selects nominated here.
        """
        if user_input is not None:
            self.working[CONF_TARIFF_SELECTS] = user_input.get(CONF_TARIFF_SELECTS) or []
            self.working[CONF_SUPPLY_CHARGE_ENTITIES] = user_input[CONF_SUPPLY_CHARGE_ENTITIES]
            return await self.async_step_init()

        options = self.working
        return self.async_show_form(
            step_id="meters",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TARIFF_SELECTS,
                        description={"suggested_value": options.get(CONF_TARIFF_SELECTS) or []},
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="select", multiple=True)
                    ),
                    vol.Required(
                        CONF_SUPPLY_CHARGE_ENTITIES,
                        default=bool(options.get(CONF_SUPPLY_CHARGE_ENTITIES, False)),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "rates": ", ".join(self._rate_names()) or "none",
            },
        )
