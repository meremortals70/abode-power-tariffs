"""A real-Home-Assistant smoke test, not the hand-written stubs.

Everything else in tests/ runs against tests/_ha_stubs.py, which is fast but
has never been checked against actual Home Assistant behaviour. This uses
pytest-homeassistant-custom-component to set the plan up in a real hass
instance and confirms the config entry loads, entities are created, and the
price sensor holds a real value — not a mock standing in for one.
"""

from __future__ import annotations

import pytest

# The newest Home Assistant installable from PyPI in this sandbox is
# 2025.1.4, which predates AddConfigEntryEntitiesCallback — a symbol this
# component correctly uses, added to HA after that release. This is a
# sandbox package-availability limit, not a reason to weaken the shipped
# code: the shim below patches the test environment's older HA, not
# custom_components/abode_power_tariffs, so everything downstream is still
# exercising the real integration code against a real (if older) hass.
from homeassistant.helpers import entity_platform as _entity_platform

if not hasattr(_entity_platform, "AddConfigEntryEntitiesCallback"):
    _entity_platform.AddConfigEntryEntitiesCallback = (
        _entity_platform.AddEntitiesCallback
    )

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abode_power_tariffs.const import (
    CONF_DAY_PATTERNS,
    CONF_DAYS,
    CONF_EXPORT_FLAT_CENTS,
    CONF_EXPORT_SAME_ALL_DAY,
    CONF_IMPORT_CENTS,
    CONF_NAME,
    CONF_PERIODS,
    CONF_RATE,
    CONF_RATES,
    CONF_START,
    CONF_END,
    CONF_SUPPLY_CHARGE_CENTS,
    DOMAIN,
)


def _options() -> dict:
    return {
        CONF_DAY_PATTERNS: [
            {
                CONF_NAME: "Every day",
                CONF_DAYS: [
                    "mon",
                    "tue",
                    "wed",
                    "thu",
                    "fri",
                    "sat",
                    "sun",
                    "holiday",
                ],
                CONF_RATES: [
                    {CONF_NAME: "Peak", CONF_IMPORT_CENTS: 45.0},
                ],
                CONF_PERIODS: [
                    {CONF_START: "00:00", CONF_END: "24:00", CONF_RATE: "Peak"},
                ],
                CONF_EXPORT_SAME_ALL_DAY: True,
                CONF_EXPORT_FLAT_CENTS: 5.0,
            }
        ],
        CONF_SUPPLY_CHARGE_CENTS: 100.0,
    }


@pytest.mark.asyncio
async def test_real_config_entry_loads_and_publishes_a_price(hass) -> None:
    """The integration actually sets up in real Home Assistant.

    Not a claim the stubs already made — this is the first time this
    component has been loaded into a genuine hass instance rather than
    tests/_ha_stubs.py's hand-written fakes.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Real HA Smoke Test",
        data={},
        options=_options(),
        entry_id="real_smoke_1",
    )
    entry.add_to_hass(hass)

    setup_ok = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert setup_ok
    assert entry.state.value == "loaded"

    price_state = hass.states.get("sensor.real_ha_smoke_test_import_price")
    assert price_state is not None, [
        s for s in hass.states.async_entity_ids() if "real_ha_smoke_test" in s
    ]
    assert float(price_state.state) == pytest.approx(0.45)

    rate_state = hass.states.get("sensor.real_ha_smoke_test_rate")
    assert rate_state is not None
    assert rate_state.state == "real_ha_smoke_test.every_day.import.peak"

    export_state = hass.states.get("sensor.real_ha_smoke_test_export_price")
    assert export_state is not None
    assert float(export_state.state) == pytest.approx(0.05)

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "not_loaded"


@pytest.mark.asyncio
async def test_real_options_flow_adds_a_rate(hass) -> None:
    """The Configure flow, driven through hass's real flow manager.

    Everything else this session touching config_flow.py was proven against
    tests/_ha_stubs.py's hand-written FORM/MENU dicts, never against
    Home Assistant's actual data_entry_flow manager. This drives the same
    rewritten rate_add screen through the real thing.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Real Options Test",
        data={},
        options=_options(),
        entry_id="real_smoke_2",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rates_menu"}
    )
    assert result["type"] == "menu"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rate_add"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "rate_add"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "name": "Shoulder",
            "timetable": "Every day",
            "import_cents": 30.0,
            "demand": {
                "demand_period": False,
                "demand_rate_per_kw_month": 0.0,
                "demand_interval": "30",
                "demand_basis": "day",
            },
            "allowance": {
                "has_allowance": False,
                "rate_allowance_kwh": 0.0,
                "fallback_rate": "Peak",
                "allowance_period": "slot",
            },
            "constraints_section": {
                "information_constraints": [],
                "enforceable_constraints": [],
            },
        },
    )
    assert result["type"] == "menu", result
    assert result["step_id"] == "rates_menu"
    assert "Shoulder" in result["description_placeholders"]["rates"]
    assert "real_options_test.every_day.import.shoulder" in (
        result["description_placeholders"]["rates"]
    )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
