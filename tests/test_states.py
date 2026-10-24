"""Tests of the decoding of battery states and the power flow string enums."""

from __future__ import annotations

import pytest

from fronius_solarapi import (
    BydBatteryState,
    FroniusSolarApi,
    LgChemBatteryState,
    MeterCategory,
    PowerFlowOhmpilotEcoState,
    PowerFlowOhmpilotState,
    SolarBatteryCellState,
    battery_controller_state,
    solar_battery_cell_states,
)

from .conftest import MockFronius


@pytest.mark.parametrize(
    ("status", "current", "previous"),
    [
        pytest.param(
            0x35,
            SolarBatteryCellState.NORMAL_CHARGE,
            SolarBatteryCellState.NORMAL_DISCHARGE,
            id="charge_after_discharge",
        ),
        pytest.param(
            0xE3,
            SolarBatteryCellState.CHARGE_SUSPEND,
            SolarBatteryCellState.NORMAL_CHARGE,
            id="suspend_after_charge",
        ),
        pytest.param(
            0x1C,
            SolarBatteryCellState.PRE_CHARGE,
            SolarBatteryCellState.OVER_CURRENT_DISCHARGE,
            id="hex_digit_low_nibble",
        ),
        pytest.param(0x08, None, None, id="reserved_both"),
        pytest.param(0xF2, None, SolarBatteryCellState.INITIAL, id="reserved_current"),
        pytest.param(None, None, None, id="missing"),
        pytest.param(0x100, None, None, id="out_of_range"),
        pytest.param(-1, None, None, id="negative"),
    ],
)
def test_solar_battery_cell_states(
    status: int | None,
    current: SolarBatteryCellState | None,
    previous: SolarBatteryCellState | None,
) -> None:
    assert solar_battery_cell_states(status) == (current, previous)


@pytest.mark.parametrize(
    ("manufacturer", "status", "state"),
    [
        pytest.param("LG-Chem", 1, LgChemBatteryState.STANDBY, id="lg_standby"),
        pytest.param("LG-Chem", 3, LgChemBatteryState.ENABLED, id="lg_enabled"),
        pytest.param("LG-Chem", 5, LgChemBatteryState.FAULTED, id="lg_faulted"),
        pytest.param("LG-Chem", 10, LgChemBatteryState.SLEEP, id="lg_sleep"),
        pytest.param("LG-Chem", 2, None, id="lg_undocumented"),
        pytest.param("BYD", 0, BydBatteryState.STANDBY, id="byd_standby"),
        pytest.param("BYD", 2, BydBatteryState.DARKSTART, id="byd_darkstart"),
        pytest.param("BYD", 3, BydBatteryState.ACTIVE, id="byd_active"),
        pytest.param("BYD", 5, BydBatteryState.UPDATING, id="byd_updating"),
        pytest.param("BYD", 6, None, id="byd_undocumented"),
        pytest.param(" byd ", 4, BydBatteryState.FAULT, id="byd_case_and_padding"),
        pytest.param("Fronius", 3, None, id="fronius_undocumented"),
        pytest.param("LG", 3, None, id="lg_resu_flex_undocumented"),
        pytest.param(None, 3, None, id="no_manufacturer"),
        pytest.param("BYD", None, None, id="no_status"),
    ],
)
def test_battery_controller_state(
    manufacturer: str | None,
    status: int | None,
    state: LgChemBatteryState | BydBatteryState | None,
) -> None:
    assert battery_controller_state(manufacturer, status) is state


async def test_storage_states_from_devices(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("gen24_storage")
    byd = (await api.system_storage_data()).data["0"].controller
    assert byd is not None
    assert byd.state is BydBatteryState.STANDBY

    mock_fronius.use_fixture_set("spec_listings")
    lg = (await api.storage_data(0)).data.controller
    assert lg is not None
    assert lg.state is LgChemBatteryState.ENABLED

    solar_battery = (await api.system_storage_data()).data["0"]
    assert solar_battery.controller is not None
    # the controller of a Fronius Solar Battery reports no status
    assert solar_battery.controller.state is None
    module = solar_battery.modules[0]
    assert module.cell_state is SolarBatteryCellState.NORMAL_CHARGE
    assert module.previous_cell_state is SolarBatteryCellState.NORMAL_DISCHARGE


async def test_power_flow_string_enums(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("spec_listings")
    flow = (await api.power_flow()).data
    assert flow.secondary_meters["12"].category == MeterCategory.OTHER_HEATING
    eco = flow.ohmpilot_ecos["0"]
    assert eco.state_heating_rod_1 == PowerFlowOhmpilotEcoState.NORMAL
    assert eco.state_heating_rod_2 is not None
    assert PowerFlowOhmpilotEcoState(eco.state_heating_rod_2) is (
        PowerFlowOhmpilotEcoState.NORMAL
    )

    mock_fronius.use_fixture_set("gen24_storage")
    flow = (await api.power_flow()).data
    state = flow.ohmpilots["0"].state
    assert state is not None
    assert PowerFlowOhmpilotState(state) is PowerFlowOhmpilotState.NORMAL


def test_meter_category_tokens() -> None:
    assert MeterCategory("METER_CAT_ECAR") is MeterCategory.ELECTRIC_VEHICLE
    assert MeterCategory("METER_CAT_BHKW") is MeterCategory.COMBINED_HEAT_AND_POWER
    assert len(MeterCategory) == 13
