"""A real-Home-Assistant smoke test, not the hand-written stubs.

Everything else in tests/ runs against tests/_ha_stubs.py, which is fast but
has never been checked against actual Home Assistant behaviour. This uses
pytest-homeassistant-custom-component to set the plan up in a real hass
instance and confirms the config entry loads, entities are created, and the
price sensor holds a real value — not a mock standing in for one.
"""

from __future__ import annotations

import pytest
import voluptuous as vol

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


@pytest.mark.asyncio
async def test_setup_rate_screen_commits_on_continue_when_filled(hass) -> None:
    """Rule under test: a typed rate is committed even when the user clicks
    the 'continue to next section' button, not just 'add another'. Only a
    genuinely blank screen is allowed to move on without committing.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "plan_name": "Real Setup Test",
            "plan_description": "",
            "single_rate_plan": False,
            "has_export": False,
        },
    )
    assert result["step_id"] == "charges"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "daily_supply_charge_cents": 0.0,
            "monthly_charge": 0.0,
            "billing_cycle_day": 0,
            "prices_include_gst": True,
            "gst_percent": 10.0,
            "import_energy_sensor": "sensor.grid_import",
        },
    )
    assert result["step_id"] == "days"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Every day", "same_every_day": True, "days": []},
    )
    assert result["step_id"] == "rates"

    # A realistic browser submission: every field HA's own schema reports as
    # required, including full section defaults for the sections the user
    # never expanded, clicking "Continue" (not "Add another").
    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema: vol.Schema) -> dict:
        submitted: dict = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    payload = _defaults_for(result["data_schema"])
    payload["name"] = "Peak"
    payload["import_cents"] = 45.0
    payload["on_submit"] = "continue"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], payload
    )
    print("STEP AFTER SUBMIT:", result["step_id"], result.get("errors"))
    assert result["step_id"] != "rates", (
        "stayed on rates with no error shown, or moved on without saving"
    )


@pytest.mark.asyncio
async def test_real_two_rates_added_in_a_row(hass) -> None:
    """Add a rate, then immediately add a second one, both through the real
    Configure flow -- closer to reporting back into Configure after setup
    and adding what's missing.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Two Rates Test",
        data={},
        options=_options(),
        entry_id="real_smoke_3",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    async def add_rate(flow_id, name, cents, *, from_init=False):
        result = None
        if from_init:
            result = await hass.config_entries.options.async_configure(
                flow_id, {"next_step_id": "rates_menu"}
            )
        result = await hass.config_entries.options.async_configure(
            flow_id, {"next_step_id": "rate_add"}
        )
        assert result["step_id"] == "rate_add", result
        payload = _defaults_for(result["data_schema"])
        payload["name"] = name
        payload["import_cents"] = cents
        result = await hass.config_entries.options.async_configure(flow_id, payload)
        return result

    started = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = started["flow_id"]

    result = await add_rate(flow_id, "Shoulder", 30.0, from_init=True)
    print("AFTER FIRST ADD:", result["step_id"], result.get("errors"))
    assert "Shoulder" in result["description_placeholders"]["rates"]

    # Already at rates_menu, same as clicking "Add rate" a second time
    # without leaving the screen -- no need to navigate from init again.
    result = await add_rate(flow_id, "Evening", 25.0)
    print("AFTER SECOND ADD:", result["step_id"], result.get("errors"))
    assert "Shoulder" in result["description_placeholders"]["rates"], (
        "first rate lost after adding a second, within the same flow session"
    )
    assert "Evening" in result["description_placeholders"]["rates"], (
        "second rate never committed"
    )

    # Now actually save, and confirm both survive onto the real config entry
    # -- this is the step that actually persists anything. Nothing before
    # this point has touched entry.options at all.
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "init"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "save"}
    )
    print("AFTER SAVE:", result.get("type"), result.get("reason"))
    assert entry.options.get(CONF_DAY_PATTERNS)
    saved_rates = [
        r[CONF_NAME] for r in entry.options[CONF_DAY_PATTERNS][0][CONF_RATES]
    ]
    assert "Shoulder" in saved_rates, saved_rates
    assert "Evening" in saved_rates, saved_rates

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_async_update_entry_persists_mid_flow(hass) -> None:
    """Confirm the fix mechanism itself, isolated: hass.config_entries.
    async_update_entry writes to entry.options immediately, without ending
    the options flow the way async_create_entry does.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Persist Mechanism Test",
        data={},
        options=_options(),
        entry_id="persist_mechanism_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "rates_menu"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "rate_add"}
    )

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    payload = _defaults_for(result["data_schema"])
    payload["name"] = "Shoulder"
    payload["import_cents"] = 30.0
    result = await hass.config_entries.options.async_configure(flow_id, payload)

    # The flow is still alive (still on rates_menu, not finished) -- proving
    # a mid-flow update_entry call, not a flow-ending create_entry, is what
    # has to do the persisting.
    assert result["type"] == "menu"
    assert result["step_id"] == "rates_menu"

    # Simulate the fix directly, without touching config_flow.py yet:
    stored_now = hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            "day_patterns": [
                {
                    **entry.options["day_patterns"][0],
                    "rates": [
                        *entry.options["day_patterns"][0]["rates"],
                        {"name": "Shoulder", "import_cents": 30.0},
                    ],
                }
            ],
        },
    )
    print("update_entry returned:", stored_now)
    print(
        "entry.options rates now:",
        [r["name"] for r in entry.options["day_patterns"][0]["rates"]],
    )
    assert "Shoulder" in [
        r["name"] for r in entry.options["day_patterns"][0]["rates"]
    ]
    # And the flow is STILL alive after that -- config_entries.async_update_entry
    # does not touch or end the options flow at all.
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "init"}
    )
    assert result["type"] == "menu"
    assert result["step_id"] == "init"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_real_rate_survives_without_ever_reaching_save(hass) -> None:
    """The actual reported bug: add a rate, never navigate to and click
    "Save and finish", never even leave the rates_menu screen. The rate
    must still be on the real config entry -- not just in the flow's own
    in-memory copy -- because the user may simply close the dialog here.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Never Saved Test",
        data={},
        options=_options(),
        entry_id="never_saved_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rates_menu"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rate_add"}
    )
    payload = _defaults_for(result["data_schema"])
    payload["name"] = "Shoulder"
    payload["import_cents"] = 30.0
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], payload
    )
    assert result["step_id"] == "rates_menu"

    # No "Save and finish" was ever reached. The dialog is simply abandoned
    # here, the way closing a browser tab would. The real config entry must
    # already have it.
    saved_rates = [
        r["name"] for r in entry.options["day_patterns"][0]["rates"]
    ]
    assert "Shoulder" in saved_rates, (
        f"lost without an explicit save: {saved_rates}"
    )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_setup_rates_defaults_to_continue_once_something_is_entered(
    hass,
) -> None:
    """The exact reported bug: with rates already entered, leaving the next
    rate screen untouched (blank name, 0 price) and hitting Submit must
    move on to periods by default -- not demand a name. Only actually
    typing a name commits a new rate; a genuinely blank screen is ignored,
    per the standing rule, and now the submit default matches that instead
    of silently requiring the user to flip a selector every time.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "plan_name": "Regression Test",
            "plan_description": "",
            "single_rate_plan": False,
            "has_export": False,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "daily_supply_charge_cents": 0.0,
            "monthly_charge": 0.0,
            "billing_cycle_day": 0,
            "prices_include_gst": True,
            "gst_percent": 10.0,
            "import_energy_sensor": "sensor.grid_import",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Every day", "same_every_day": True, "days": []},
    )
    assert result["step_id"] == "rates"

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    # Enter one real rate first -- on_submit still defaults to "add" here,
    # since nothing has been entered for this pattern yet.
    payload = _defaults_for(result["data_schema"])
    assert payload["on_submit"] == "add"
    payload["name"] = "Off Peak"
    payload["import_cents"] = 19.8
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], payload
    )
    assert result["step_id"] == "rates"

    # Now the screen for a would-be second rate. Leave it entirely blank
    # and submit exactly what the frontend would send by default.
    payload = _defaults_for(result["data_schema"])
    assert payload["on_submit"] == "continue", (
        f"on_submit still defaulted to 'add' with a rate already entered: "
        f"{payload['on_submit']}"
    )
    assert payload["name"] == ""
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], payload
    )
    print("STEP AFTER BLANK SUBMIT:", result["step_id"], result.get("errors"))
    assert result["step_id"] == "periods", (
        "a blank screen with rates already entered should move on by "
        "default, not demand a name"
    )


@pytest.mark.asyncio
async def test_setup_last_rate_with_explicit_continue_is_committed(hass) -> None:
    """Type a real rate, explicitly choose 'continue' (not the default),
    submit -- it must commit that rate AND move to periods, not re-show a
    blank rate screen as if nothing happened.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "plan_name": "Last Rate Test",
            "plan_description": "",
            "single_rate_plan": False,
            "has_export": False,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "daily_supply_charge_cents": 0.0,
            "monthly_charge": 0.0,
            "billing_cycle_day": 0,
            "prices_include_gst": True,
            "gst_percent": 10.0,
            "import_energy_sensor": "sensor.grid_import",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Every day", "same_every_day": True, "days": []},
    )
    assert result["step_id"] == "rates"

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    # One rate typed, real name and price, explicit "continue" even though
    # nothing has been entered yet for this pattern (default would be "add").
    payload = _defaults_for(result["data_schema"])
    payload["name"] = "Peak"
    payload["import_cents"] = 45.0
    payload["on_submit"] = "continue"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], payload
    )
    print("STEP AFTER LAST RATE + EXPLICIT CONTINUE:", result["step_id"], result.get("errors"))
    assert result["step_id"] == "periods", (
        f"typed rate with explicit continue was not committed: {result}"
    )


@pytest.mark.asyncio
async def test_setup_four_rates_then_explicit_continue(hass) -> None:
    """Enter four rates in sequence, explicitly choosing 'add' each time
    except the last, where 'continue' is explicitly chosen -- the exact
    reported sequence: several rates entered, then the last one submitted
    with intent to move on.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "plan_name": "Four Rates Test",
            "plan_description": "",
            "single_rate_plan": False,
            "has_export": False,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "daily_supply_charge_cents": 0.0,
            "monthly_charge": 0.0,
            "billing_cycle_day": 0,
            "prices_include_gst": True,
            "gst_percent": 10.0,
            "import_energy_sensor": "sensor.grid_import",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Every day", "same_every_day": True, "days": []},
    )
    assert result["step_id"] == "rates"

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    names = ["EV Charging", "Shoulder", "Super Off Peak", "Off Peak"]
    for index, name in enumerate(names):
        assert result["step_id"] == "rates", (index, result)
        payload = _defaults_for(result["data_schema"])
        payload["name"] = name
        payload["import_cents"] = 10.0 + index
        payload["on_submit"] = "continue" if index == len(names) - 1 else "add"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], payload
        )
        print(f"AFTER RATE {index} ({name}):", result["step_id"], result.get("errors"))

    assert result["step_id"] == "periods", (
        f"the fourth rate, submitted with explicit continue, did not "
        f"commit and move on: {result}"
    )


@pytest.mark.asyncio
async def test_setup_rate_with_demand_charge_is_accepted(hass) -> None:
    """A rate declaring a genuine demand charge -- demand_period ticked,
    a real demand rate given -- must be accepted, not rejected as if the
    rate were missing.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "plan_name": "Demand Rate Test",
            "plan_description": "",
            "single_rate_plan": False,
            "has_export": False,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "daily_supply_charge_cents": 0.0,
            "monthly_charge": 0.0,
            "billing_cycle_day": 0,
            "prices_include_gst": True,
            "gst_percent": 10.0,
            "import_energy_sensor": "sensor.grid_import",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Every day", "same_every_day": True, "days": []},
    )
    assert result["step_id"] == "rates"

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    payload = _defaults_for(result["data_schema"])
    print("RAW DEFAULT PAYLOAD:", payload)
    payload["name"] = "Peak"
    payload["import_cents"] = 45.0
    payload["on_submit"] = "continue"
    # This is the part that matters: a real browser submission with the
    # demand section actually filled in, not left at its collapsed default.
    payload["demand"] = {
        "demand_period": True,
        "demand_rate_per_kw_month": 18.4,
        "demand_interval": "30",
        "demand_basis": "day",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], payload
    )
    print("STEP AFTER DEMAND RATE:", result["step_id"], result.get("errors"))
    assert result["step_id"] == "periods", (
        f"a rate with a real demand charge was rejected: {result}"
    )


@pytest.mark.asyncio
async def test_real_export_rates_csv_service(hass) -> None:
    """The new export_rates_csv service, called for real."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CSV Export Test",
        data={},
        options=_options(),
        entry_id="csv_export_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "export_rates_csv",
        {"config_entry_id": entry.entry_id},
        blocking=True,
        return_response=True,
    )
    print("SERVICE RESPONSE:", response)
    assert "rates_csv" in response
    assert "Peak" in response["rates_csv"]
    assert "rate_id" in response["rates_csv"]
    assert "periods_csv" in response
    assert "export_rates_csv" in response

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_real_get_day_schedule_service(hass) -> None:
    """The new get_day_schedule service, called for real."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Day Schedule Test",
        data={},
        options=_options(),
        entry_id="day_schedule_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "get_day_schedule",
        {"config_entry_id": entry.entry_id, "resolution_minutes": 15},
        blocking=True,
        return_response=True,
    )
    segments = response["segments"]
    print("SEGMENT COUNT:", len(segments))
    print("FIRST:", segments[0])
    print("NOW:", response["now"])
    # 24 hours at 15-minute resolution is 96 segments on an ordinary day.
    assert len(segments) == 96
    assert segments[0]["per_kwh"] == 0.45
    assert response["now"]
    # Every segment covers the same single day, so it belongs to the same
    # timetable throughout — the field is dropped rather than repeated 96
    # times as if it varied. get_intervals, which can span several days,
    # keeps it.
    assert "day_pattern" not in segments[0]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_real_today_schedule_sensor(hass) -> None:
    """The new today_schedule sensor, read as a real entity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Today Schedule Test",
        data={},
        options=_options(),
        entry_id="today_schedule_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.today_schedule_test_today_s_schedule")
    print("STATE:", state)
    assert state is not None
    assert len(state.attributes["segments"]) == 96
    assert state.attributes["now"]
    assert "day_pattern" not in state.attributes["segments"][0]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_real_demand_rate_is_entered_in_cents(hass) -> None:
    """The reported bug: demand charge was in dollars, not cents like every
    other price on the form. A rate submitted with demand_rate_per_kw_month
    = 1840 (cents, matching the form's own convention) must be read back as
    $18.40, not $1840.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Demand Cents Test",
        data={},
        options=_options(),
        entry_id="demand_cents_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.data_entry_flow import section as _section_type

    def _defaults_for(schema):
        submitted = {}
        for key, value in schema.schema.items():
            name = getattr(key, "schema", key)
            if isinstance(value, _section_type):
                submitted[name] = _defaults_for(value.schema)
                continue
            default = getattr(key, "default", vol.UNDEFINED)
            if default is not vol.UNDEFINED and default is not None:
                submitted[name] = default() if callable(default) else default
        return submitted

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rates_menu"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "rate_add"}
    )
    payload = _defaults_for(result["data_schema"])
    payload["name"] = "Demand Rate"
    payload["import_cents"] = 30.0
    payload["demand"]["demand_period"] = True
    payload["demand"]["demand_rate_per_kw_month"] = 1840.0
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], payload
    )
    assert result["step_id"] == "rates_menu", result

    coordinator = entry.runtime_data
    added_pattern = coordinator.plan.day_pattern_by_name("Every day")
    added_rate = added_pattern.rate_by_name("Demand Rate")
    print("DEMAND RATE ON THE REAL OBJECT:", added_rate.demand_rate_per_kw_month)
    assert added_rate.demand_rate_per_kw_month == pytest.approx(18.40)

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_real_today_periods_attribute(hass) -> None:
    """The new 'periods' attribute -- exact period boundaries, resolved to
    their rates, for a table card. Not merged from segments client-side;
    read directly off the day pattern's own periods.
    """
    options = {
        CONF_DAY_PATTERNS: [
            {
                CONF_NAME: "Every day",
                CONF_DAYS: [
                    "mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday",
                ],
                CONF_RATES: [
                    {CONF_NAME: "Off Peak", CONF_IMPORT_CENTS: 19.8},
                    {CONF_NAME: "Peak", CONF_IMPORT_CENTS: 56.88},
                ],
                CONF_PERIODS: [
                    {CONF_START: "00:00", CONF_END: "16:00", CONF_RATE: "Off Peak"},
                    {CONF_START: "16:00", CONF_END: "24:00", CONF_RATE: "Peak"},
                ],
                CONF_EXPORT_SAME_ALL_DAY: True,
                CONF_EXPORT_FLAT_CENTS: 5.0,
            }
        ],
        CONF_SUPPLY_CHARGE_CENTS: 100.0,
        "import_energy_sensor": "sensor.grid_import",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Periods Test",
        data={},
        options=options,
        entry_id="periods_test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.periods_test_today_s_schedule")
    periods = state.attributes["periods"]
    print("PERIODS:", periods)
    assert len(periods) == 2
    assert periods[0]["start"] == "00:00"
    assert periods[0]["end"] == "16:00"
    assert periods[0]["rate_name"] == "Off Peak"
    assert periods[0]["per_kwh"] == pytest.approx(0.198)
    assert periods[1]["rate_name"] == "Peak"
    assert periods[1]["per_kwh"] == pytest.approx(0.5688)
    assert "day_pattern" not in periods[0]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
