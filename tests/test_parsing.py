"""Tests of the Fronius specific quirks the parsers handle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from fronius_solarapi import (
    ApiVersion,
    FroniusSolarApi,
    InverterModel,
    InverterState,
    MeterLocation,
    OhmpilotState,
    inverter_model,
    inverter_state,
    meter_location,
)
from fronius_solarapi.parsers import (
    body_data,
    parse_head,
    parse_inverter_info,
    parse_meter_data,
    parse_power_flow,
    parse_storage_data,
)

from .conftest import MockFronius, load_fixture

SCOPE_SYSTEM = {"Scope": "System"}


def _body(fixture: str) -> dict[str, Any]:
    return body_data(json.loads(load_fixture(fixture)))


async def test_custom_name_html_escaped(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    """Datamanagers HTML-escape the custom name, GEN24 devices don't."""
    mock_fronius.use_fixture_set("primo_s0")
    inverters = (await api.inverter_info()).data
    assert inverters["1"].custom_name == "Primo 5.0-1"
    assert inverters["2"].custom_name == "Primo 3.0-1"
    assert inverters["2"].model == InverterModel("Fronius", "Primo 3.0-1")

    mock_fronius.use_fixture_set("gen24")
    inverters = (await api.inverter_info()).data
    assert inverters["1"].custom_name == "Inverter name"
    assert inverters["1"].model == InverterModel("Fronius", "GEN24/Tauro/Verto")


def test_inverter_info_status_string() -> None:
    """Old GEN24 firmware reports the state string instead of a status code."""
    inverters = parse_inverter_info(_body("datamanager_v1/GetInverterInfo.json"))
    gen24 = inverters["240"]
    assert gen24.status_code is None
    assert gen24.state is None
    assert gen24.inverter_state == "Running"
    assert gen24.error_code is None
    symo = inverters["1"]
    assert symo.status_code == 7
    assert symo.state is InverterState.RUNNING
    assert symo.error_code == 0


def test_inverter_info_error_code_minus_one() -> None:
    """-1 means that no valid error code is present."""
    raw = {"1": {"DT": 76, "UniqueID": "1", "ErrorCode": -1, "StatusCode": 7}}
    assert parse_inverter_info(raw)["1"].error_code is None


async def test_device_status_key_with_colon(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    """A GEN24 Primo reports `DeviceStatus:` in the cumulation collection."""
    mock_fronius.use_fixture_set("spec_listings")
    data = (await api.inverter_cumulation_data(1)).data
    assert data.device_status is not None
    assert data.device_status.inverter_state == "Running"
    assert data.device_status.status_code is None


def test_v0_device_state_key() -> None:
    """Early API v0 firmware named the status code `DeviceState`."""
    from fronius_solarapi.parsers import parse_common_inverter_data

    raw = {"DeviceStatus": {"DeviceState": 7, "ErrorCode": 0}}
    status = parse_common_inverter_data(raw).device_status
    assert status is not None
    assert status.status_code == 7
    assert status.state is InverterState.RUNNING


async def test_system_inverter_data_value_key(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    """GEN24 devices name the per-device object `Value` instead of `Values`."""
    mock_fronius.use_fixture_set("spec_listings")
    data = (await api.system_inverter_data()).data
    assert set(data) == {"1"}
    assert data["1"].power_ac == 271.0
    assert data["1"].energy_total is None
    assert data["1"].device_status is None


async def test_system_inverter_data_datamanager(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("datamanager_v0")
    data = (await api.system_inverter_data()).data
    assert data["1"].power_ac == 1764
    assert data["1"].energy_day == 6000
    assert data["1"].energy_year == 3310000
    assert data["1"].energy_total == 35611000


async def test_active_device_info_gen24_top_level_inverters(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    """GEN24 devices list inverters next to the device classes."""
    mock_fronius.use_fixture_set("spec_listings")
    info = (await api.active_device_info()).data
    assert set(info.inverters) == {"1"}
    assert info.inverters["1"].device_type == 1
    assert info.inverters["1"].serial == "29091000975090007"
    assert info.meters["0"].device_type is None
    assert info.meters["0"].serial == "18142251"
    assert info.ohmpilots["0"].serial == "28136344"
    assert info.storages == {}
    assert info.sensor_cards == {}


async def test_active_device_info_datamanager(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("datamanager_v1")
    info = (await api.active_device_info()).data
    assert info.inverters["1"].device_type == 122
    assert info.inverters["1"].serial == "30412345"
    assert info.meters["0"].device_type is None
    assert info.string_controls == {}


def test_sensor_card_channel_names() -> None:
    from fronius_solarapi.parsers import parse_active_device_info

    raw = {
        "SensorCard": {
            "1": {"ChannelNames": ["Temperature 1", "Irradiation"], "DT": 254}
        }
    }
    info = parse_active_device_info(raw)
    assert info.sensor_cards["1"].channel_names == ("Temperature 1", "Irradiation")
    assert info.sensor_cards["1"].device_type == 254


async def test_logger_info_utc_offset_wraps(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    """Negative offsets are reported as unsigned 32 bit integers."""
    mock_fronius.use_fixture_set("primo_s0")
    info = (await api.logger_info()).data
    assert info.utc_offset == -10800
    assert info.timezone_name == "-03"
    assert info.cash_currency == "BRL"


async def test_logger_info_escaped(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("symo")
    mock_fronius.add(
        "/solar_api/v1/GetLoggerInfo.cgi",
        fixture="synthetic/GetLoggerInfo_escaped.json",
    )
    info = (await api.logger_info()).data
    assert info.cash_currency == "€"
    assert info.co2_unit == "kg"
    assert info.utc_offset == -10800
    assert info.product_id is None
    assert info.delivery_factor is None


async def test_logger_info_v0(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("datamanager_v0")
    info = (await api.logger_info()).data
    assert info.unique_id == "240.123456"
    assert info.product_id is None
    assert info.platform_id is None
    assert info.delivery_factor is None
    assert info.cash_factor == pytest.approx(0.076)


async def test_logger_led_info(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("datamanager_v1")
    leds = (await api.logger_led_info()).data
    assert leds.power_led is not None
    assert leds.power_led.color == "green"
    assert leds.power_led.state == "on"
    assert leds.solar_web_led is not None
    assert leds.solar_web_led.color == "none"
    assert leds.solar_web_led.state == "off"
    assert leds.solar_net_led is not None
    assert leds.wlan_led is not None
    assert set(leds.leds) == {"PowerLED", "SolarNetLED", "SolarWebLED", "WLANLED"}


def test_meter_gen24_channel_aliases() -> None:
    """Some GEN24 firmware reports channels under internal names."""
    meter = parse_meter_data(
        _body("synthetic/GetMeterRealtimeData_Device_0_aliases.json")
    )
    assert meter.current_ac_phase_1 == 1.2
    assert meter.current_ac_phase_2 == 2.3
    assert meter.current_ac_phase_3 == 3.4
    assert meter.energy_real_consumed == 1000.0
    assert meter.energy_real_produced == 2000.0
    assert meter.power_real_phase_1 == 100.0
    assert meter.power_real_phase_2 == 200.0
    assert meter.power_real_phase_3 == 300.0
    assert meter.power_real == 600.0
    # floats standing for integers and booleans
    assert meter.enabled is True
    assert meter.visible is True
    assert meter.meter_location_code == 0
    assert meter.meter_location is MeterLocation.GRID
    assert meter.timestamp == datetime(2021, 11, 26, 11, 7, 52, tzinfo=UTC)


async def test_meter_kinds(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("spec_listings")
    meters = (await api.system_meter_data()).data
    assert meters["0"].meter_location is MeterLocation.GRID
    assert meters["1"].meter_location is MeterLocation.SUBLOAD
    assert meters["1"].energy_real_phase_2_produced == 3043466
    assert meters["1"].voltage_ac_phase_average == pytest.approx(233.553, abs=1e-3)
    assert meters["2"].energy_reactive_phase_1_produced == 8261790
    assert meters["2"].current_ac_phase_2 is None
    s0 = meters["3"]
    assert s0.details is not None
    assert s0.details.serial == "n.a."
    assert s0.details.model == "S0 Meter at inverter 40"
    assert s0.energy_real_minus_relative == 0
    assert s0.energy_real_plus_relative == 0
    assert s0.power_real == 0
    assert s0.current_ac_phase_1 is None


def test_meter_details_missing() -> None:
    assert parse_meter_data({"PowerReal_P_Sum": 1.5}).details is None


def test_storage_serial_whitespace() -> None:
    """Battery serial numbers are padded with whitespace, which is kept."""
    storage = parse_storage_data(
        _body("gen24_storage/GetStorageRealtimeData.json")["0"]
    )
    assert storage.controller is not None
    assert storage.controller.details is not None
    assert storage.controller.details.serial == "P030T020Z2001234567     "
    assert storage.controller.status_battery_cell == 0
    assert storage.controller.enabled is True
    assert storage.modules == ()


async def test_storage_modules(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("spec_listings")
    storages = (await api.system_storage_data()).data
    storage = storages["0"]
    assert storage.controller is not None
    assert storage.controller.voltage_dc_maximum_cell == pytest.approx(3.329)
    assert storage.controller.status_battery_cell is None
    assert len(storage.modules) == 2
    module = storage.modules[0]
    assert module.details is not None
    assert module.details.serial == "S012002885 "
    assert module.cycle_count_battery_cell == 255
    assert module.status_battery_cell == 53
    assert module.temperature_cell_maximum == 27.75
    assert module.timestamp == datetime.fromtimestamp(1560346263, tz=UTC)


async def test_ohmpilot(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("gen24_storage")
    ohmpilot = (await api.system_ohmpilot_data()).data["0"]
    assert ohmpilot.state_code == 0
    assert ohmpilot.state is OhmpilotState.UP_AND_RUNNING
    assert ohmpilot.error_code is None
    assert ohmpilot.details is not None
    assert ohmpilot.details.hardware == "6"
    assert ohmpilot.details.software == "1.0.25-3"

    mock_fronius.use_fixture_set("spec_listings")
    ohmpilot = (await api.ohmpilot_data(0)).data
    assert ohmpilot.error_code == 926
    assert ohmpilot.state is OhmpilotState.UP_AND_RUNNING


def test_ohmpilot_unknown_state() -> None:
    from fronius_solarapi.parsers import parse_ohmpilot_data

    assert parse_ohmpilot_data({"CodeOfState": 99}).state is None
    assert parse_ohmpilot_data({}).state is None


async def test_power_flow_version_and_sections(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("spec_listings")
    flow = (await api.power_flow()).data
    assert flow.version == 13
    assert flow.site.mode == "meter"
    assert flow.site.backup_mode is False
    assert flow.site.battery_standby is None
    assert flow.site.power_grid == 0.0
    assert flow.inverters["1"].model == InverterModel("Fronius", "GEN24/Tauro/Verto")
    assert flow.inverters["1"].energy_day is None
    assert flow.ohmpilots == {}
    eco = flow.ohmpilot_ecos["0"]
    assert eco.state_heating_rod_1 == "normal"
    assert eco.temperature_2 == 0.0
    meter = flow.secondary_meters["12"]
    assert meter.meter_location_code == 256
    assert meter.meter_location is MeterLocation.SUBLOAD
    assert meter.category == "METER_CAT_OTHERHEATING"
    assert meter.label == "Heat"
    assert meter.power == 0.0


def test_power_flow_hybrid() -> None:
    flow = parse_power_flow(
        _body("spec_listings/variants/GetPowerFlowRealtimeData_hybrid.json")
    )
    assert flow.version == 12
    inverter = flow.inverters["1"]
    assert inverter.battery_mode == "normal"
    assert inverter.state_of_charge == 55
    assert inverter.model == InverterModel("Fronius", "Symo Hybrid 5.0-3-S")
    assert flow.site.power_battery == pytest.approx(-384.7)
    assert flow.ohmpilots["720897"].power_ac_total == 2635
    assert flow.ohmpilots["720897"].temperature == 30.7
    assert flow.secondary_meters == {}
    assert flow.ohmpilot_ecos == {}


def test_power_flow_without_version() -> None:
    """Datamanagers before 3.8.1-1 did not report a version."""
    flow = parse_power_flow(_body("datamanager_v1/GetPowerFlowRealtimeData.json"))
    assert flow.version is None
    assert flow.inverters["1"].power is None
    assert flow.site.meter_location == "load"


async def test_night_responses(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    """A sleeping inverter answers with empty data, not an error."""
    mock_fronius.use_fixture_set("igplus_v2", night=True)
    assert (await api.inverter_info()).data == {}
    data = (await api.inverter_common_data(1)).data
    assert data.power_ac is None
    assert data.device_status is None
    flow = (await api.power_flow()).data
    assert flow.inverters == {}
    assert flow.site.power_photovoltaics is None


def test_head() -> None:
    head = parse_head(json.loads(load_fixture("symo/GetInverterInfo.json")))
    assert head.timestamp == datetime.fromisoformat("2021-10-07T13:41:00+02:00")
    assert head.status.code == 0
    assert head.status.reason == ""
    assert head.request_arguments == {}
    head = parse_head(
        json.loads(load_fixture("symo/GetInverterRealtimeData_Device_1.json"))
    )
    assert head.request_arguments["DeviceId"] == "1"


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (None, None),
        (0, InverterState.STARTUP),
        (6, InverterState.STARTUP),
        (7, InverterState.RUNNING),
        (8, InverterState.STANDBY),
        (9, InverterState.BOOTLOADING),
        (10, InverterState.ERROR),
        (11, InverterState.IDLE),
        (12, InverterState.READY),
        (13, InverterState.SLEEPING),
        (255, InverterState.UNKNOWN),
        (14, None),
        (-1, None),
    ],
)
def test_inverter_state(code: int | None, state: InverterState | None) -> None:
    assert inverter_state(code) is state


@pytest.mark.parametrize(
    ("code", "location"),
    [
        (None, None),
        (0, MeterLocation.GRID),
        (1, MeterLocation.LOAD),
        (2, None),
        (3, MeterLocation.EXTERNAL_GENERATOR),
        (4, MeterLocation.EXTERNAL_GENERATOR_WITH_BATTERY),
        (255, None),
        (256, MeterLocation.SUBLOAD),
        (511, MeterLocation.SUBLOAD),
        (512, None),
    ],
)
def test_meter_location(code: int | None, location: MeterLocation | None) -> None:
    assert meter_location(code) is location


def test_inverter_model() -> None:
    assert inverter_model(None) is None
    assert inverter_model(0) is None
    assert inverter_model(121) == InverterModel("Fronius", "Symo 20.0-3-M")
    assert inverter_model(130) == InverterModel("SunPower", "SPR 8001F-3 EU")


def test_api_version_enum() -> None:
    assert ApiVersion(1) is ApiVersion.V1
    assert ApiVersion(0) is ApiVersion.V0
