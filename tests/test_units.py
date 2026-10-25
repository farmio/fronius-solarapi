"""Tests of the check of units reported along with inverter values."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fronius_solarapi import InvalidResponseError
from fronius_solarapi.parsers import (
    parse_3p_inverter_data,
    parse_common_inverter_data,
    parse_cumulation_inverter_data,
    parse_system_inverter_data,
)

from .conftest import load_fixture


def _common_data() -> dict[str, Any]:
    raw = json.loads(load_fixture("gen24/GetInverterRealtimeData_Device_1.json"))
    data: dict[str, Any] = raw["Body"]["Data"]
    return data


@pytest.mark.parametrize(
    ("key", "unit"),
    [
        pytest.param("PAC", "kW", id="power_with_prefix"),
        pytest.param("TOTAL_ENERGY", "kWh", id="energy_with_prefix"),
        pytest.param("IDC_2", "mA", id="current_with_prefix"),
        pytest.param("UAC", "A", id="wrong_quantity"),
        pytest.param("DAY_ENERGY", "wh", id="case_differs"),
    ],
)
def test_common_data_unexpected_unit(key: str, unit: str) -> None:
    data = _common_data()
    data[key]["Unit"] = unit
    with pytest.raises(InvalidResponseError, match=f"{key} is reported in '{unit}'"):
        parse_common_inverter_data(data)


def test_unit_checked_for_null_value() -> None:
    """GEN24 devices report `null` day energy, still with a unit."""
    data = _common_data()
    data["DAY_ENERGY"]["Unit"] = "kWh"
    assert data["DAY_ENERGY"]["Value"] is None
    with pytest.raises(InvalidResponseError, match="DAY_ENERGY"):
        parse_common_inverter_data(data)


def test_missing_unit_accepted() -> None:
    data = _common_data()
    del data["PAC"]["Unit"]
    assert parse_common_inverter_data(data).power_ac == pytest.approx(37.32045)


def test_cumulation_unexpected_unit() -> None:
    data = {"PAC": {"Unit": "kW", "Value": 1.2}}
    with pytest.raises(InvalidResponseError, match="PAC is reported in 'kW'"):
        parse_cumulation_inverter_data(data)


def test_3p_unexpected_unit() -> None:
    data = {"UAC_L2": {"Unit": "kV", "Value": 0.23}}
    with pytest.raises(InvalidResponseError, match="UAC_L2 is reported in 'kV'"):
        parse_3p_inverter_data(data)


def test_3p_channels_without_documented_unit() -> None:
    """The spec names no unit for ambient temperature and fan speeds."""
    data = {
        "T_AMBIENT": {"Unit": "°C", "Value": 31},
        "ROTATION_SPEED_FAN_FL": {"Unit": "RPM", "Value": 2400},
    }
    parsed = parse_3p_inverter_data(data)
    assert parsed.temperature_ambient == 31
    assert parsed.fan_speed_front_left == 2400


def test_system_unexpected_unit() -> None:
    raw = json.loads(load_fixture("datamanager_v0/GetInverterRealtimeData_System.json"))
    data: dict[str, Any] = raw["Body"]["Data"]
    data["YEAR_ENERGY"]["Unit"] = "MWh"
    with pytest.raises(InvalidResponseError, match="YEAR_ENERGY is reported in 'MWh'"):
        parse_system_inverter_data(data)


def test_system_unknown_channel_not_checked() -> None:
    data = {"PAC": {"Unit": "W", "Values": {"1": 100}}, "NEW": {"Unit": "x"}}
    assert parse_system_inverter_data(data)["1"].power_ac == 100
