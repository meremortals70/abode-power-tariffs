"""Configuration and options flow.

Setup collects the plan. Nothing is invented and no entity publishes a price
that the user did not enter.

The 24-hour strip is shown before anything is chosen and again on every screen
that touches time periods, so a gap or an overlap is visible the moment it is
made.
"""

from __future__ import annotations

import copy
import functools
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_USER,
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
    CONF_DAY_PATTERNS,
    CONF_DAYS,
    CONF_DEMAND_PERIOD,
    CONF_END,
    CONF_EXPORT_ALLOWANCE_KWH,
    CONF_EXPORT_CENTS,
    CONF_FALLBACK_RATE,
    CONF_GST_PERCENT,
    CONF_HOLIDAY_SENSOR,
    CONF_IMPORT_CENTS,
    CONF_IMPORT_ENERGY_SENSOR,
    CONF_NAME,
    CONF_PERIODS,
    CONF_PLAN_NAME,
    CONF_PRICES_INCLUDE_GST,
    CONF_RATE,
    CONF_RATES,
    CONF_SEASON_FROM,
    CONF_SEASON_TO,
    CONF_SOURCE_ENERGY_SENSOR,
    CONF_START,
    CONF_SUPPLY_CHARGE_CENTS,
    CONF_SUPPLY_CHARGE_ENTITIES,
    CONF_TARIFF_SELECTS,
    CONF_VALID_FROM,
    CONF_VALID_TO,
    DEFAULT_GST_PERCENT,
    DOMAIN,
    MINUTES_PER_DAY,
    UM_CONF_ALWAYS_AVAILABLE,
    UM_CONF_CYCLE,
    UM_CONF_DELTA_VALUES,
    UM_CONF_NAME,
    UM_CONF_NET_CONSUMPTION,
    UM_CONF_OFFSET,
    UM_CONF_PERIODICALLY_RESETTING,
    UM_CONF_SOURCE,
    UM_CONF_TARIFFS,
    UM_CYCLE_MONTHLY,
    UTILITY_METER_DOMAIN,
    WEEKDAY_TOKENS,
)
from .plan import Plan, PlanError, format_time, parse_time
from .strip import render_day_pattern, render_plan, render_rate_plan_card
from .validate import validate_plan

_LOGGER = logging.getLogger(__name__)

EVERY_DAY = "Every day"


def _time_to_minutes(value: str, *, is_end: bool) -> int:
    """Convert a time selector value to minutes since midnight.

    A period ending at midnight is the end of the day, not the start of it, so
    an end of 00:00 becomes 24:00. There is no other way to say it with a time
    picker.
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


def _rate_record(user_input: dict[str, Any]) -> dict[str, Any]:
    """Build a stored rate from a submitted form."""
    return {
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_IMPORT_CENTS: user_input[CONF_IMPORT_CENTS],
        CONF_EXPORT_CENTS: user_input.get(CONF_EXPORT_CENTS, 0.0),
        CONF_CONSTRAINTS: [
            item.strip()
            for item in str(user_input.get(CONF_CONSTRAINTS) or "").split(",")
            if item.strip()
        ],
        CONF_COASTING_PERMITTED: bool(user_input.get(CONF_COASTING_PERMITTED, True)),
        CONF_DEMAND_PERIOD: bool(user_input.get(CONF_DEMAND_PERIOD, False)),
        CONF_DAILY_ALLOWANCE_KWH: user_input.get(CONF_DAILY_ALLOWANCE_KWH) or None,
        CONF_EXPORT_ALLOWANCE_KWH: user_input.get(CONF_EXPORT_ALLOWANCE_KWH) or None,
        CONF_FALLBACK_RATE: user_input.get(CONF_FALLBACK_RATE) or None,
    }


def _rate_schema(
    existing: dict[str, Any], fallback_options: list[str], *, minimal: bool
) -> vol.Schema:
    """Return the rate form. The setup form asks only what a plan cannot do without."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=existing.get(CONF_NAME, "")): selector.TextSelector(),
        vol.Required(
            CONF_IMPORT_CENTS, default=float(existing.get(CONF_IMPORT_CENTS) or 0.0)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=1000, step=0.01, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_EXPORT_CENTS, default=float(existing.get(CONF_EXPORT_CENTS) or 0.0)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=1000, step=0.01, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
    if minimal:
        return vol.Schema(schema)

    schema[
        vol.Required(
            CONF_CONSTRAINTS, default=", ".join(existing.get(CONF_CONSTRAINTS) or [])
        )
    ] = selector.TextSelector()
    schema[
        vol.Required(
            CONF_COASTING_PERMITTED, default=bool(existing.get(CONF_COASTING_PERMITTED, True))
        )
    ] = selector.BooleanSelector()
    schema[
        vol.Required(
            CONF_DEMAND_PERIOD, default=bool(existing.get(CONF_DEMAND_PERIOD, False))
        )
    ] = selector.BooleanSelector()
    schema[
        vol.Required(
            CONF_DAILY_ALLOWANCE_KWH,
            default=float(existing.get(CONF_DAILY_ALLOWANCE_KWH) or 0.0),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=1000, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    schema[
        vol.Required(
            CONF_EXPORT_ALLOWANCE_KWH,
            default=float(existing.get(CONF_EXPORT_ALLOWANCE_KWH) or 0.0),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=1000, step=0.1, mode=selector.NumberSelectorMode.BOX
        )
    )
    if fallback_options:
        schema[
            vol.Required(
                CONF_FALLBACK_RATE,
                default=existing.get(CONF_FALLBACK_RATE) or fallback_options[0],
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=fallback_options)
        )
    return vol.Schema(schema)


class AbodePowerTariffsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Collect the plan, then create the entry."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Start with nothing."""
        self._name: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the channel name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input[CONF_PLAN_NAME]).strip()
            if not name:
                errors[CONF_PLAN_NAME] = "name_required"
            else:
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                self._name = name
                return await self.async_step_first_rate()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PLAN_NAME, default="Electricity"): selector.TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_first_rate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the first rate, and build the plan from it.

        Nothing is invented. The whole day is priced at this rate until time
        periods are added, so the first price published is one the user typed.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            rate = _rate_record(user_input)
            if not rate[CONF_NAME]:
                errors[CONF_NAME] = "name_required"
            else:
                options = {
                    CONF_RATES: [rate],
                    CONF_DAY_PATTERNS: [
                        {
                            CONF_NAME: EVERY_DAY,
                            CONF_DAYS: list(ALL_DAY_TOKENS),
                            CONF_PERIODS: [
                                {
                                    CONF_START: "00:00",
                                    CONF_END: "24:00",
                                    CONF_RATE: rate[CONF_NAME],
                                }
                            ],
                        }
                    ],
                    CONF_SUPPLY_CHARGE_CENTS: user_input[CONF_SUPPLY_CHARGE_CENTS],
                    CONF_PRICES_INCLUDE_GST: True,
                    CONF_GST_PERCENT: DEFAULT_GST_PERCENT,
                }
                return self.async_create_entry(
                    title=self._name,
                    data={CONF_PLAN_NAME: self._name},
                    options=options,
                )

        schema = dict(_rate_schema({}, [], minimal=True).schema)
        schema[vol.Required(CONF_SUPPLY_CHARGE_CENTS, default=0.0)] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=1000, step=0.01, mode=selector.NumberSelectorMode.BOX
            )
        )

        return self.async_show_form(
            step_id="first_rate",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"name": self._name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AbodePowerTariffsOptionsFlow:
        """Return the options flow."""
        return AbodePowerTariffsOptionsFlow()


type StepHandler = Callable[
    ["AbodePowerTariffsOptionsFlow", dict[str, Any] | None], Awaitable[ConfigFlowResult]
]


def guarded(func: StepHandler) -> StepHandler:
    """Show the failure instead of an empty dialog.

    Without this, an exception anywhere in a step gives the user a dialog with
    the word Error and nothing else, and the detail is only in the full log.
    """

    @functools.wraps(func)
    async def wrapper(
        self: AbodePowerTariffsOptionsFlow, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        try:
            return await func(self, user_input)
        except Exception:  # Deliberate: nothing may escape into an empty dialog
            _LOGGER.exception("Configuration step %s failed", func.__name__)
            self._failure = traceback.format_exc()
            return await self.async_step_failure()

    return wrapper


MENU = [
    "rates_menu",
    "day_patterns_menu",
    "periods_pick_day_pattern",
    "general",
    "usage_tracking",
    "rate_plan_card",
    "save",
]


class AbodePowerTariffsOptionsFlow(OptionsFlow):
    """Edit the plan."""

    def __init__(self) -> None:
        """Initialise the working copy lazily, on first step."""
        self._working: dict[str, Any] | None = None
        self._day_pattern_index: int | None = None
        self._period_index: int | None = None
        self._rate_index: int | None = None
        self._failure: str = ""

    # ------------------------------------------------------------- utilities

    @property
    def working(self) -> dict[str, Any]:
        """Return the in-progress copy of the options."""
        if self._working is None:
            self._working = copy.deepcopy(dict(self.config_entry.options))
            self._working.setdefault(CONF_RATES, [])
            self._working.setdefault(CONF_DAY_PATTERNS, [])
        return self._working

    def _plan(self) -> Plan | None:
        try:
            return Plan.from_dict({**self.working, CONF_NAME: self.config_entry.title})
        except PlanError:
            return None

    def _plan_text(self) -> str:
        plan = self._plan()
        if plan is None:
            return "The stored plan cannot be read. Edit a rate to rebuild it."
        summary = render_plan(plan)
        problems = validate_plan(plan)
        if problems:
            summary += "\n\nNot ready to save:\n" + "\n".join(f"  {p}" for p in problems)
        return summary

    def _placeholders(self) -> dict[str, str]:
        return {"plan": self._plan_text()}

    def _rates(self) -> list[dict[str, Any]]:
        rates: list[dict[str, Any]] = self.working[CONF_RATES]
        return rates

    def _day_patterns(self) -> list[dict[str, Any]]:
        patterns: list[dict[str, Any]] = self.working[CONF_DAY_PATTERNS]
        return patterns

    def _rate_names(self) -> list[str]:
        return [str(rate.get(CONF_NAME, "")) for rate in self._rates()]

    def _day_pattern_names(self) -> list[str]:
        return [str(pattern.get(CONF_NAME, "")) for pattern in self._day_patterns()]

    def _menu(self, step_id: str) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id=step_id,
            menu_options=MENU,
            description_placeholders=self._placeholders(),
        )

    # ------------------------------------------------------------------ menu

    @guarded
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the plan and the menu."""
        return self._menu("init")

    @guarded
    async def async_step_failure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what went wrong, in full, where it can be copied."""
        if user_input is not None:
            return self._menu("init")
        return self.async_show_form(
            step_id="failure",
            data_schema=vol.Schema({}),
            description_placeholders={"detail": self._failure or "No detail captured."},
        )

    @guarded
    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store the plan."""
        plan = self._plan()
        if plan is None or validate_plan(plan):
            return self._menu("init")
        return self.async_create_entry(title="", data=self.working)

    @guarded
    async def async_step_rate_plan_card(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the plan in the shape an inverter's tariff screen asks for."""
        if user_input is not None:
            return self._menu("init")
        plan = self._plan()
        card = render_rate_plan_card(plan) if plan else "The plan cannot be read."
        return self.async_show_form(
            step_id="rate_plan_card",
            data_schema=vol.Schema({}),
            description_placeholders={"card": card},
        )

    # ----------------------------------------------------------------- rates

    @guarded
    async def async_step_rates_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, edit or remove a rate."""
        listing = "\n".join(
            f"  {rate.get(CONF_NAME)}   "
            f"{float(rate.get(CONF_IMPORT_CENTS) or 0):.2f} c/kWh in, "
            f"{float(rate.get(CONF_EXPORT_CENTS) or 0):.2f} c/kWh out"
            for rate in self._rates()
        )
        return self.async_show_menu(
            step_id="rates_menu",
            menu_options=["rate_add", "rate_pick", "rate_remove", "init"],
            description_placeholders={"rates": listing or "  none yet"},
        )

    @guarded
    async def async_step_rate_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a rate to edit."""
        names = self._rate_names()
        if not names:
            self._rate_index = None
            return await self.async_step_rate_add()
        if user_input is not None:
            self._rate_index = names.index(str(user_input[CONF_NAME]))
            return await self.async_step_rate_add()
        return self.async_show_form(
            step_id="rate_pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=names[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    )
                }
            ),
        )

    @guarded
    async def async_step_rate_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a rate, or edit the one chosen."""
        errors: dict[str, str] = {}
        index = self._rate_index
        existing: dict[str, Any] = self._rates()[index] if index is not None else {}

        if user_input is not None:
            record = _rate_record(user_input)
            name = record[CONF_NAME]
            clash = any(
                rate.get(CONF_NAME) == name
                for position, rate in enumerate(self._rates())
                if position != index
            )
            if not name:
                errors[CONF_NAME] = "name_required"
            elif clash:
                errors[CONF_NAME] = "rate_exists"
            else:
                if index is None:
                    self._rates().append(record)
                else:
                    previous = str(self._rates()[index].get(CONF_NAME, ""))
                    self._rates()[index] = record
                    if previous and previous != name:
                        self._rename_rate(previous, name)
                self._rate_index = None
                return await self.async_step_rates_menu()

        fallback_options = [
            name for name in self._rate_names() if name != existing.get(CONF_NAME)
        ]
        return self.async_show_form(
            step_id="rate_add",
            data_schema=_rate_schema(existing, fallback_options, minimal=False),
            errors=errors,
        )

    def _rename_rate(self, previous: str, current: str) -> None:
        """Follow a rate rename into every period that names it."""
        for pattern in self._day_patterns():
            for period in pattern.get(CONF_PERIODS, []):
                if period.get(CONF_RATE) == previous:
                    period[CONF_RATE] = current
        for rate in self._rates():
            if rate.get(CONF_FALLBACK_RATE) == previous:
                rate[CONF_FALLBACK_RATE] = current

    @guarded
    async def async_step_rate_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a rate that no time period uses."""
        errors: dict[str, str] = {}
        names = self._rate_names()
        if not names:
            return await self.async_step_rates_menu()

        if user_input is not None:
            name = str(user_input[CONF_NAME])
            in_use = any(
                period.get(CONF_RATE) == name
                for pattern in self._day_patterns()
                for period in pattern.get(CONF_PERIODS, [])
            )
            if in_use:
                errors[CONF_NAME] = "rate_in_use"
            else:
                self.working[CONF_RATES] = [
                    rate for rate in self._rates() if rate.get(CONF_NAME) != name
                ]
                return await self.async_step_rates_menu()

        return self.async_show_form(
            step_id="rate_remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=names[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    )
                }
            ),
            errors=errors,
        )

    # ---------------------------------------------------------- day patterns

    @guarded
    async def async_step_day_patterns_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, edit, duplicate or remove a day pattern."""
        return self.async_show_menu(
            step_id="day_patterns_menu",
            menu_options=[
                "day_pattern_add",
                "day_pattern_pick",
                "day_pattern_duplicate",
                "day_pattern_remove",
                "init",
            ],
            description_placeholders=self._placeholders(),
        )

    @guarded
    async def async_step_day_pattern_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a day pattern to edit."""
        names = self._day_pattern_names()
        if not names:
            self._day_pattern_index = None
            return await self.async_step_day_pattern_add()
        if user_input is not None:
            self._day_pattern_index = names.index(str(user_input[CONF_NAME]))
            return await self.async_step_day_pattern_add()
        return self.async_show_form(
            step_id="day_pattern_pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=names[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    )
                }
            ),
        )

    @guarded
    async def async_step_day_pattern_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a day pattern, or edit the one chosen."""
        errors: dict[str, str] = {}
        index = self._day_pattern_index
        existing: dict[str, Any] = self._day_patterns()[index] if index is not None else {}
        current_days = list(existing.get(CONF_DAYS) or ALL_DAY_TOKENS)
        same_every_day = set(current_days) == set(ALL_DAY_TOKENS)

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            days = (
                list(ALL_DAY_TOKENS)
                if user_input["same_every_day"]
                else list(user_input.get(CONF_DAYS) or [])
            )
            if not name:
                errors[CONF_NAME] = "name_required"
            elif not days:
                errors[CONF_DAYS] = "days_required"
            else:
                record = {
                    CONF_NAME: name,
                    CONF_DAYS: days,
                    CONF_SEASON_FROM: str(user_input.get(CONF_SEASON_FROM) or "").strip()
                    or None,
                    CONF_SEASON_TO: str(user_input.get(CONF_SEASON_TO) or "").strip() or None,
                    CONF_PERIODS: existing.get(CONF_PERIODS, []),
                }
                if index is None:
                    self._day_patterns().append(record)
                else:
                    self._day_patterns()[index] = record
                self._day_pattern_index = None
                return await self.async_step_day_patterns_menu()

        return self.async_show_form(
            step_id="day_pattern_add",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=str(existing.get(CONF_NAME) or EVERY_DAY)
                    ): selector.TextSelector(),
                    vol.Required(
                        "same_every_day", default=same_every_day
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_DAYS,
                        default=current_days
                        if not same_every_day
                        else list(WEEKDAY_TOKENS),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(ALL_DAY_TOKENS),
                            multiple=True,
                            translation_key="day_tokens",
                        )
                    ),
                    vol.Required(
                        CONF_SEASON_FROM, default=str(existing.get(CONF_SEASON_FROM) or "")
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_SEASON_TO, default=str(existing.get(CONF_SEASON_TO) or "")
                    ): selector.TextSelector(),
                }
            ),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    @guarded
    async def async_step_day_pattern_duplicate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Copy a day pattern and its periods, then open it for editing."""
        names = self._day_pattern_names()
        if not names:
            self._day_pattern_index = None
            return await self.async_step_day_pattern_add()
        if user_input is not None:
            source = self._day_patterns()[names.index(str(user_input["source"]))]
            copied = copy.deepcopy(source)
            copied[CONF_NAME] = (
                str(user_input[CONF_NAME]).strip() or f"{source.get(CONF_NAME)} copy"
            )
            self._day_patterns().append(copied)
            self._day_pattern_index = len(self._day_patterns()) - 1
            return await self.async_step_day_pattern_add()
        return self.async_show_form(
            step_id="day_pattern_duplicate",
            data_schema=vol.Schema(
                {
                    vol.Required("source", default=names[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    ),
                    vol.Required(CONF_NAME, default="Weekend"): selector.TextSelector(),
                }
            ),
        )

    @guarded
    async def async_step_day_pattern_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a day pattern."""
        names = self._day_pattern_names()
        if not names:
            return await self.async_step_day_patterns_menu()
        if user_input is not None:
            name = str(user_input[CONF_NAME])
            self.working[CONF_DAY_PATTERNS] = [
                pattern for pattern in self._day_patterns() if pattern.get(CONF_NAME) != name
            ]
            self._day_pattern_index = None
            return await self.async_step_day_patterns_menu()
        return self.async_show_form(
            step_id="day_pattern_remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=names[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    )
                }
            ),
        )

    # --------------------------------------------------------- time  periods

    @guarded
    async def async_step_periods_pick_day_pattern(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose whose time periods to edit."""
        names = self._day_pattern_names()
        if not names:
            self._day_pattern_index = None
            return await self.async_step_day_pattern_add()
        if len(names) == 1:
            self._day_pattern_index = 0
            return await self.async_step_periods_menu()
        if user_input is not None:
            self._day_pattern_index = names.index(str(user_input[CONF_NAME]))
            return await self.async_step_periods_menu()
        return self.async_show_form(
            step_id="periods_pick_day_pattern",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=names[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    )
                }
            ),
            description_placeholders=self._placeholders(),
        )

    def _current_day_pattern(self) -> dict[str, Any]:
        patterns = self._day_patterns()
        if not patterns:
            raise PlanError("There are no day patterns to hold a time period")
        index = self._day_pattern_index or 0
        if index >= len(patterns):
            index = 0
            self._day_pattern_index = 0
        return patterns[index]

    def _periods(self) -> list[dict[str, Any]]:
        periods: list[dict[str, Any]] = self._current_day_pattern().setdefault(
            CONF_PERIODS, []
        )
        return periods

    def _period_labels(self) -> list[str]:
        return [
            f"{period.get(CONF_START)} to {period.get(CONF_END)}  {period.get(CONF_RATE)}"
            for period in self._periods()
        ]

    def _period_placeholders(self) -> dict[str, str]:
        """Return the strip for the chosen day pattern only."""
        pattern_name = str(self._current_day_pattern().get(CONF_NAME, ""))
        plan = self._plan()
        if plan is not None:
            for pattern in plan.day_patterns:
                if pattern.name == pattern_name:
                    text = render_day_pattern(plan, pattern)
                    break
            else:
                text = self._plan_text()
        else:
            text = self._plan_text()
        return {"day_pattern": pattern_name, "plan": text}

    @guarded
    async def async_step_periods_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add, edit or remove a time period in the chosen day pattern."""
        return self.async_show_menu(
            step_id="periods_menu",
            menu_options=["period_add", "period_pick", "period_remove", "init"],
            description_placeholders=self._period_placeholders(),
        )

    @guarded
    async def async_step_period_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a time period to edit."""
        labels = self._period_labels()
        if not labels:
            self._period_index = None
            return await self.async_step_period_add()
        if user_input is not None:
            self._period_index = labels.index(str(user_input["period"]))
            return await self.async_step_period_add()
        return self.async_show_form(
            step_id="period_pick",
            data_schema=vol.Schema(
                {
                    vol.Required("period", default=labels[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=labels)
                    )
                }
            ),
            description_placeholders=self._period_placeholders(),
        )

    @guarded
    async def async_step_period_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a time period, or edit the one chosen. Three fields, nothing else."""
        errors: dict[str, str] = {}
        names = self._rate_names()
        if not names:
            self._rate_index = None
            return await self.async_step_rate_add()

        index = self._period_index
        existing: dict[str, Any] = self._periods()[index] if index is not None else {}

        if user_input is not None:
            try:
                start = _time_to_minutes(str(user_input[CONF_START]), is_end=False)
                end = _time_to_minutes(str(user_input[CONF_END]), is_end=True)
            except PlanError:
                errors["base"] = "bad_time"
            else:
                if end <= start:
                    errors[CONF_END] = "end_before_start"
                else:
                    record = {
                        CONF_START: format_time(start),
                        CONF_END: format_time(end),
                        CONF_RATE: str(user_input[CONF_RATE]),
                    }
                    if index is None:
                        self._periods().append(record)
                    else:
                        self._periods()[index] = record
                    self._period_index = None
                    return await self.async_step_periods_menu()

        default_start = parse_time(str(existing[CONF_START])) if existing else 0
        default_end = parse_time(str(existing[CONF_END])) if existing else MINUTES_PER_DAY
        default_rate = str(existing.get(CONF_RATE) or names[0])
        if default_rate not in names:
            default_rate = names[0]

        return self.async_show_form(
            step_id="period_add",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_START, default=_minutes_to_selector(default_start)
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_END, default=_minutes_to_selector(default_end)
                    ): selector.TimeSelector(),
                    vol.Required(CONF_RATE, default=default_rate): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names)
                    ),
                }
            ),
            errors=errors,
            description_placeholders=self._period_placeholders(),
        )

    @guarded
    async def async_step_period_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a time period."""
        labels = self._period_labels()
        if not labels:
            return await self.async_step_periods_menu()
        if user_input is not None:
            self._periods().pop(labels.index(str(user_input["period"])))
            self._period_index = None
            return await self.async_step_periods_menu()
        return self.async_show_form(
            step_id="period_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("period", default=labels[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=labels)
                    )
                }
            ),
            description_placeholders=self._period_placeholders(),
        )

    # --------------------------------------------------------------- general

    @guarded
    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Supply charge, tax, validity and the two optional sensors."""
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
                return self._menu("init")

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
                        description={
                            "suggested_value": options.get(CONF_IMPORT_ENERGY_SENSOR)
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
                }
            ),
            errors=errors,
        )

    # -------------------------------------------------------- usage tracking

    @guarded
    async def async_step_usage_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Split kWh by rate, and keep the split pointed at the right rate."""
        return self.async_show_menu(
            step_id="usage_tracking",
            menu_options=["meter_create", "meter_link", "init"],
            description_placeholders={
                "rates": ", ".join(self._rate_names()) or "none",
                "linked": ", ".join(self.working.get(CONF_TARIFF_SELECTS) or [])
                or "none",
            },
        )

    @guarded
    async def async_step_meter_create(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a utility meter with this plan's rates as its tariffs.

        Creates a config entry belonging to the utility_meter integration. It is
        not owned here: renaming a rate afterwards does not rename its tariff,
        and deleting this channel does not delete the meter.
        """
        errors: dict[str, str] = {}
        names = self._rate_names()
        if not names:
            self._rate_index = None
            return await self.async_step_rate_add()

        if user_input is not None:
            result = await self.hass.config_entries.flow.async_init(
                UTILITY_METER_DOMAIN,
                context={"source": SOURCE_USER},
                data={
                    UM_CONF_NAME: str(user_input[CONF_NAME]).strip(),
                    UM_CONF_SOURCE: user_input[CONF_SOURCE_ENERGY_SENSOR],
                    UM_CONF_CYCLE: UM_CYCLE_MONTHLY,
                    UM_CONF_OFFSET: 0,
                    UM_CONF_TARIFFS: names,
                    UM_CONF_NET_CONSUMPTION: False,
                    UM_CONF_DELTA_VALUES: False,
                    UM_CONF_PERIODICALLY_RESETTING: True,
                    UM_CONF_ALWAYS_AVAILABLE: False,
                },
            )
            if result.get("type") != "create_entry":
                errors["base"] = "meter_not_created"
                _LOGGER.error("Utility meter was not created: %s", result)
            else:
                return await self.async_step_meter_link()

        return self.async_show_form(
            step_id="meter_create",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=f"{self.config_entry.title} by rate"
                    ): selector.TextSelector(),
                    vol.Required(CONF_SOURCE_ENERGY_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"rates": ", ".join(names)},
        )

    @guarded
    async def async_step_meter_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Nominate which tariff dropdowns to keep pointed at the current rate."""
        if user_input is not None:
            self.working[CONF_TARIFF_SELECTS] = user_input.get(CONF_TARIFF_SELECTS) or []
            self.working[CONF_SUPPLY_CHARGE_ENTITIES] = user_input[
                CONF_SUPPLY_CHARGE_ENTITIES
            ]
            return self._menu("init")

        options = self.working
        return self.async_show_form(
            step_id="meter_link",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TARIFF_SELECTS,
                        description={
                            "suggested_value": options.get(CONF_TARIFF_SELECTS) or []
                        },
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="select", multiple=True)
                    ),
                    vol.Required(
                        CONF_SUPPLY_CHARGE_ENTITIES,
                        default=bool(options.get(CONF_SUPPLY_CHARGE_ENTITIES, False)),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={"rates": ", ".join(self._rate_names()) or "none"},
        )
