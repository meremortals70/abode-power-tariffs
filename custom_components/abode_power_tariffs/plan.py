"""The tariff plan: rates, day sets, windows, and resolution.

Pure module. Imports nothing from Home Assistant.

Times are held as minutes since local midnight, 0 to 1440 inclusive. 1440 is
"end of day" and is only ever an end. Start is inclusive, end exclusive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .const import (
    ALL_DAY_TOKENS,
    CONF_COASTING_PERMITTED,
    CONF_COMPONENTS,
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
    CONF_IMPORT_CENTS,
    CONF_NAME,
    CONF_PRICES_INCLUDE_GST,
    CONF_RATE,
    CONF_RATES,
    CONF_SEASON_FROM,
    CONF_SEASON_TO,
    CONF_START,
    CONF_SUPPLY_CHARGE_CENTS,
    CONF_VALID_FROM,
    CONF_VALID_TO,
    CONF_WINDOWS,
    DAY_HOLIDAY,
    MINUTES_PER_DAY,
    WEEKDAY_TOKENS,
)


class PlanError(ValueError):
    """Raised when stored configuration cannot be read into a plan."""


def parse_time(value: str) -> int:
    """Parse 'HH:MM' into minutes since midnight. '24:00' is accepted."""
    try:
        raw_hour, raw_minute = value.strip().split(":")
        hour = int(raw_hour)
        minute = int(raw_minute)
    except (AttributeError, ValueError) as err:
        raise PlanError(f"'{value}' is not a time in HH:MM form") from err
    if hour == 24 and minute == 0:
        return MINUTES_PER_DAY
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise PlanError(f"'{value}' is not a valid time of day")
    return hour * 60 + minute


def format_time(minutes: int) -> str:
    """Format minutes since midnight as 'HH:MM'. 1440 renders as '24:00'."""
    if minutes == MINUTES_PER_DAY:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_month_day(value: str) -> tuple[int, int]:
    """Parse 'MM-DD' into a (month, day) pair."""
    try:
        raw_month, raw_day = value.strip().split("-")
        month = int(raw_month)
        day = int(raw_day)
    except (AttributeError, ValueError) as err:
        raise PlanError(f"'{value}' is not a date in MM-DD form") from err
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise PlanError(f"'{value}' is not a valid month and day")
    return month, day


def format_month_day(value: tuple[int, int]) -> str:
    """Format a (month, day) pair as 'MM-DD'."""
    return f"{value[0]:02d}-{value[1]:02d}"


def day_token(day: date, is_holiday: bool) -> str:
    """Return the day type token for a calendar date."""
    if is_holiday:
        return DAY_HOLIDAY
    return WEEKDAY_TOKENS[day.weekday()]


@dataclass(frozen=True, slots=True)
class Rate:
    """One named rate. Prices are dollars per kWh."""

    name: str
    import_price: float
    export_price: float = 0.0
    constraints: frozenset[str] = field(default_factory=frozenset)
    coasting_permitted: bool = True
    daily_allowance_kwh: float | None = None
    export_allowance_kwh: float | None = None
    fallback_rate: str | None = None
    demand_window: bool = False
    components: tuple[tuple[str, float], ...] = ()

    @property
    def has_allowance(self) -> bool:
        """Return whether this rate is capped by a daily energy allowance."""
        return self.daily_allowance_kwh is not None

    def as_dict(self) -> dict[str, Any]:
        """Return the rate as a plain dictionary."""
        return {
            CONF_NAME: self.name,
            CONF_IMPORT_CENTS: round(self.import_price * 100, 4),
            CONF_EXPORT_CENTS: round(self.export_price * 100, 4),
            CONF_CONSTRAINTS: sorted(self.constraints),
            CONF_COASTING_PERMITTED: self.coasting_permitted,
            CONF_DAILY_ALLOWANCE_KWH: self.daily_allowance_kwh,
            CONF_EXPORT_ALLOWANCE_KWH: self.export_allowance_kwh,
            CONF_FALLBACK_RATE: self.fallback_rate,
            CONF_DEMAND_WINDOW: self.demand_window,
            CONF_COMPONENTS: dict(self.components),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Rate:
        """Build a rate from stored configuration."""
        name = str(raw.get(CONF_NAME, "")).strip()
        if not name:
            raise PlanError("A rate must have a name")
        components = raw.get(CONF_COMPONENTS) or {}
        return cls(
            name=name,
            import_price=_cents_to_dollars(raw.get(CONF_IMPORT_CENTS)),
            export_price=_cents_to_dollars(raw.get(CONF_EXPORT_CENTS)),
            constraints=frozenset(
                str(item).strip() for item in raw.get(CONF_CONSTRAINTS) or () if str(item).strip()
            ),
            coasting_permitted=bool(raw.get(CONF_COASTING_PERMITTED, True)),
            daily_allowance_kwh=_optional_float(raw.get(CONF_DAILY_ALLOWANCE_KWH)),
            export_allowance_kwh=_optional_float(raw.get(CONF_EXPORT_ALLOWANCE_KWH)),
            fallback_rate=(str(raw[CONF_FALLBACK_RATE]) if raw.get(CONF_FALLBACK_RATE) else None),
            demand_window=bool(raw.get(CONF_DEMAND_WINDOW, False)),
            components=tuple(
                (str(key), float(value)) for key, value in sorted(components.items())
            ),
        )


def _cents_to_dollars(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return round(float(value) / 100.0, 6)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


@dataclass(frozen=True, slots=True)
class Window:
    """One time window within a day set, naming a rate."""

    start: int
    end: int
    rate: str

    def contains(self, minutes: int) -> bool:
        """Return whether a minute of the day falls inside this window."""
        return self.start <= minutes < self.end

    def as_dict(self) -> dict[str, Any]:
        """Return the window as a plain dictionary."""
        return {
            CONF_START: format_time(self.start),
            CONF_END: format_time(self.end),
            CONF_RATE: self.rate,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Window:
        """Build a window from stored configuration."""
        rate = str(raw.get(CONF_RATE, "")).strip()
        if not rate:
            raise PlanError("A window must name a rate")
        return cls(
            start=parse_time(str(raw.get(CONF_START, ""))),
            end=parse_time(str(raw.get(CONF_END, ""))),
            rate=rate,
        )


@dataclass(frozen=True, slots=True)
class DaySet:
    """A set of day types, optionally limited to a season, and its windows."""

    name: str
    days: frozenset[str]
    windows: tuple[Window, ...] = ()
    season_from: tuple[int, int] | None = None
    season_to: tuple[int, int] | None = None

    @property
    def is_seasonal(self) -> bool:
        """Return whether this day set is limited to a date range."""
        return self.season_from is not None and self.season_to is not None

    def covers_date(self, day: date) -> bool:
        """Return whether the season range contains this date."""
        if not self.is_seasonal:
            return True
        assert self.season_from is not None
        assert self.season_to is not None
        current = (day.month, day.day)
        start = self.season_from
        end = self.season_to
        if start <= end:
            return start <= current <= end
        # Wraps the new year, e.g. 11-01 to 03-31.
        return current >= start or current <= end

    def matches(self, token: str, day: date) -> bool:
        """Return whether this day set applies to a day type on a date."""
        return token in self.days and self.covers_date(day)

    def window_at(self, minutes: int) -> Window | None:
        """Return the window containing a minute of the day, if any."""
        for window in self.windows:
            if window.contains(minutes):
                return window
        return None

    def sorted_windows(self) -> tuple[Window, ...]:
        """Return the windows in start order."""
        return tuple(sorted(self.windows, key=lambda window: window.start))

    def as_dict(self) -> dict[str, Any]:
        """Return the day set as a plain dictionary."""
        return {
            CONF_NAME: self.name,
            CONF_DAYS: [token for token in ALL_DAY_TOKENS if token in self.days],
            CONF_SEASON_FROM: (format_month_day(self.season_from) if self.season_from else None),
            CONF_SEASON_TO: (format_month_day(self.season_to) if self.season_to else None),
            CONF_WINDOWS: [window.as_dict() for window in self.sorted_windows()],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DaySet:
        """Build a day set from stored configuration."""
        name = str(raw.get(CONF_NAME, "")).strip()
        if not name:
            raise PlanError("A day set must have a name")
        days = frozenset(str(token) for token in raw.get(CONF_DAYS) or ())
        unknown = days - set(ALL_DAY_TOKENS)
        if unknown:
            raise PlanError(f"Unknown day types in '{name}': {', '.join(sorted(unknown))}")
        season_from = raw.get(CONF_SEASON_FROM)
        season_to = raw.get(CONF_SEASON_TO)
        return cls(
            name=name,
            days=days,
            windows=tuple(Window.from_dict(item) for item in raw.get(CONF_WINDOWS) or ()),
            season_from=parse_month_day(str(season_from)) if season_from else None,
            season_to=parse_month_day(str(season_to)) if season_to else None,
        )


@dataclass(frozen=True, slots=True)
class Resolution:
    """The plan resolved at one instant."""

    day_set: DaySet
    window: Window
    rate: Rate


@dataclass(frozen=True, slots=True)
class Plan:
    """A complete tariff plan for one metering channel."""

    name: str
    rates: tuple[Rate, ...] = ()
    day_sets: tuple[DaySet, ...] = ()
    daily_supply_charge: float = 0.0
    prices_include_gst: bool = True
    gst_percent: float = 0.0
    valid_from: date | None = None
    valid_to: date | None = None

    def rate_by_name(self, name: str) -> Rate | None:
        """Return a rate by name, or None."""
        for rate in self.rates:
            if rate.name == name:
                return rate
        return None

    @property
    def rate_names(self) -> tuple[str, ...]:
        """Return every rate name, in configured order."""
        return tuple(rate.name for rate in self.rates)

    @property
    def constraints(self) -> tuple[str, ...]:
        """Return every constraint declared anywhere in the plan, sorted."""
        found: set[str] = set()
        for rate in self.rates:
            found |= rate.constraints
        return tuple(sorted(found))

    @property
    def day_set_names(self) -> tuple[str, ...]:
        """Return every day set name, in configured order."""
        return tuple(day_set.name for day_set in self.day_sets)

    def day_set_for(self, day: date, is_holiday: bool) -> DaySet | None:
        """Return the day set that applies on a date, or None."""
        token = day_token(day, is_holiday)
        seasonal: DaySet | None = None
        general: DaySet | None = None
        for day_set in self.day_sets:
            if not day_set.matches(token, day):
                continue
            if day_set.is_seasonal:
                if seasonal is None:
                    seasonal = day_set
            elif general is None:
                general = day_set
        # A seasonal day set is more specific than a year-round one.
        return seasonal or general

    def is_active_on(self, day: date) -> bool:
        """Return whether the plan's validity range contains this date."""
        if self.valid_from is not None and day < self.valid_from:
            return False
        return not (self.valid_to is not None and day > self.valid_to)

    def resolve(self, day: date, minutes: int, is_holiday: bool) -> Resolution | None:
        """Resolve the plan at a local date and minute of the day."""
        day_set = self.day_set_for(day, is_holiday)
        if day_set is None:
            return None
        window = day_set.window_at(minutes)
        if window is None:
            return None
        rate = self.rate_by_name(window.rate)
        if rate is None:
            return None
        return Resolution(day_set=day_set, window=window, rate=rate)

    def boundaries_for(self, day: date, is_holiday: bool) -> tuple[int, ...]:
        """Return the window boundaries in force on a date, in minutes."""
        day_set = self.day_set_for(day, is_holiday)
        if day_set is None:
            return ()
        edges = {0, MINUTES_PER_DAY}
        for window in day_set.windows:
            edges.add(window.start)
            edges.add(window.end)
        return tuple(sorted(edges))

    def as_dict(self) -> dict[str, Any]:
        """Return the plan as a plain dictionary, ready for storage."""
        return {
            CONF_NAME: self.name,
            CONF_RATES: [rate.as_dict() for rate in self.rates],
            CONF_DAY_SETS: [day_set.as_dict() for day_set in self.day_sets],
            CONF_SUPPLY_CHARGE_CENTS: round(self.daily_supply_charge * 100, 4),
            CONF_PRICES_INCLUDE_GST: self.prices_include_gst,
            CONF_GST_PERCENT: self.gst_percent,
            CONF_VALID_FROM: self.valid_from.isoformat() if self.valid_from else None,
            CONF_VALID_TO: self.valid_to.isoformat() if self.valid_to else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Plan:
        """Build a plan from stored configuration."""
        return cls(
            name=str(raw.get(CONF_NAME, "Tariff")),
            rates=tuple(Rate.from_dict(item) for item in raw.get(CONF_RATES) or ()),
            day_sets=tuple(DaySet.from_dict(item) for item in raw.get(CONF_DAY_SETS) or ()),
            daily_supply_charge=_cents_to_dollars(raw.get(CONF_SUPPLY_CHARGE_CENTS)),
            prices_include_gst=bool(raw.get(CONF_PRICES_INCLUDE_GST, True)),
            gst_percent=float(raw.get(CONF_GST_PERCENT) or 0.0),
            valid_from=_optional_date(raw.get(CONF_VALID_FROM)),
            valid_to=_optional_date(raw.get(CONF_VALID_TO)),
        )


def _optional_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
