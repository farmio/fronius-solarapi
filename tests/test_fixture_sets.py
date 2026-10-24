"""Snapshot every request against every fixture set."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from fronius_solarapi import FroniusError, FroniusSolarApi

from .conftest import MockFronius, snapshot_value

type Call = Callable[[FroniusSolarApi], Awaitable[Any]]

REQUESTS: dict[str, Call] = {
    "fetch_api_version": lambda api: api.fetch_api_version(),
    "inverter_info": lambda api: api.inverter_info(),
    "logger_info": lambda api: api.logger_info(),
    "logger_led_info": lambda api: api.logger_led_info(),
    "active_device_info": lambda api: api.active_device_info(),
    "inverter_common_data(1)": lambda api: api.inverter_common_data(1),
    "inverter_common_data(2)": lambda api: api.inverter_common_data("2"),
    "inverter_3p_data(1)": lambda api: api.inverter_3p_data(1),
    "inverter_cumulation_data(1)": lambda api: api.inverter_cumulation_data(1),
    "system_inverter_data": lambda api: api.system_inverter_data(),
    "meter_data(0)": lambda api: api.meter_data(0),
    "system_meter_data": lambda api: api.system_meter_data(),
    "storage_data(0)": lambda api: api.storage_data(0),
    "system_storage_data": lambda api: api.system_storage_data(),
    "ohmpilot_data(0)": lambda api: api.ohmpilot_data(0),
    "system_ohmpilot_data": lambda api: api.system_ohmpilot_data(),
    "power_flow": lambda api: api.power_flow(),
}


async def _collect(api: FroniusSolarApi, url: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, call in REQUESTS.items():
        try:
            results[name] = snapshot_value(await call(api))
        except FroniusError as err:
            # the test server listens on a random port
            message = str(err).replace(url, "http://fronius")
            results[name] = f"{type(err).__name__}: {message}"
    return results


@pytest.mark.parametrize(
    ("fixture_set", "night"),
    [
        pytest.param("symo", False, id="symo"),
        pytest.param("symo", True, id="symo_night"),
        pytest.param("gen24", False, id="gen24"),
        pytest.param("gen24_storage", False, id="gen24_storage"),
        pytest.param("igplus_v2", False, id="igplus_v2"),
        pytest.param("igplus_v2", True, id="igplus_v2_night"),
        pytest.param("primo_s0", False, id="primo_s0"),
        pytest.param("datamanager_v0", False, id="datamanager_v0"),
        pytest.param("datamanager_v1", False, id="datamanager_v1"),
        pytest.param("spec_listings", False, id="spec_listings"),
    ],
)
async def test_fixture_set(
    mock_fronius: MockFronius,
    api: FroniusSolarApi,
    snapshot: SnapshotAssertion,
    fixture_set: str,
    night: bool,
) -> None:
    mock_fronius.use_fixture_set(fixture_set, night=night)
    assert await _collect(api, mock_fronius.url) == snapshot
    assert api.api_version is mock_fronius.api_version
