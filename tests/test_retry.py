"""Tests of the retry of requests answered with a transient status code."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator

import aiohttp
import pytest
from aiohttp import web

from fronius_solarapi import (
    FroniusConnectionError,
    FroniusSolarApi,
    RequestNotSupportedError,
    StatusError,
)
from fronius_solarapi.client import DEFAULT_STATUS_RETRIES

from .conftest import MockFronius, load_fixture

INVERTER_PATH = "/solar_api/v1/GetInverterRealtimeData.cgi"
INVERTER_QUERY = {
    "Scope": "Device",
    "DeviceId": "1",
    "DataCollection": "CommonInverterData",
}
METER_PATH = "/solar_api/v1/GetMeterRealtimeData.cgi"


def _status_response(code: int, reason: str = "") -> str:
    return json.dumps(
        {
            "Body": {"Data": {}},
            "Head": {
                "RequestArguments": {},
                "Status": {"Code": code, "Reason": reason, "UserMessage": ""},
                "Timestamp": "2021-10-07T10:01:17+02:00",
            },
        }
    )


class SequenceHandler:
    """Answer with the given status codes in turn, then with the last one."""

    def __init__(self, codes: list[int], success_fixture: str) -> None:
        self.calls = 0
        self._codes: Iterator[int] = iter(codes)
        self._last = codes[-1]
        self._success = load_fixture(success_fixture)

    async def __call__(self, request: web.Request) -> web.StreamResponse:
        self.calls += 1
        code = next(self._codes, self._last)
        text = self._success if code == 0 else _status_response(code, f"code {code}")
        return web.Response(text=text, content_type="application/json")


@pytest.fixture
def symo(mock_fronius: MockFronius) -> MockFronius:
    mock_fronius.use_fixture_set("symo")
    return mock_fronius


@pytest.mark.parametrize(
    "codes",
    [
        pytest.param([8, 0], id="ln_request_timeout"),
        pytest.param([7, 0], id="ln_request_error"),
        pytest.param([9, 0], id="ln_parse_error"),
        pytest.param([8, 7, 0], id="two_transient"),
    ],
)
async def test_transient_status_retried(
    symo: MockFronius, api: FroniusSolarApi, codes: list[int]
) -> None:
    handler = SequenceHandler(codes, "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    response = await api.inverter_common_data(1)
    assert response.data.power_ac == 1190
    assert handler.calls == len(codes)


async def test_retries_exhausted(symo: MockFronius, api: FroniusSolarApi) -> None:
    handler = SequenceHandler([8], "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    with pytest.raises(StatusError) as excinfo:
        await api.inverter_common_data(1)
    assert excinfo.value.code == 8
    assert excinfo.value.reason == "code 8"
    assert handler.calls == DEFAULT_STATUS_RETRIES + 1


async def test_ends_on_other_error(symo: MockFronius, api: FroniusSolarApi) -> None:
    """A non-transient answer to a retry ends retrying and is reported."""
    handler = SequenceHandler([8, 12], "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    with pytest.raises(StatusError) as excinfo:
        await api.inverter_common_data(1)
    assert excinfo.value.code == 12
    assert handler.calls == 2


@pytest.mark.parametrize(
    ("code", "error"),
    [
        pytest.param(1, StatusError, id="not_implemented"),
        pytest.param(5, StatusError, id="timeout"),
        pytest.param(6, StatusError, id="argument_error"),
        pytest.param(10, StatusError, id="config_io_error"),
        pytest.param(11, RequestNotSupportedError, id="not_supported"),
        pytest.param(12, StatusError, id="device_not_available"),
        pytest.param(255, StatusError, id="unknown_error"),
    ],
)
async def test_other_status_not_retried(
    symo: MockFronius,
    api: FroniusSolarApi,
    code: int,
    error: type[StatusError],
) -> None:
    handler = SequenceHandler([code], "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    with pytest.raises(error):
        await api.inverter_common_data(1)
    assert handler.calls == 1


async def test_retry_applies_to_other_requests(
    symo: MockFronius, api: FroniusSolarApi
) -> None:
    handler = SequenceHandler([8, 0], "symo/GetMeterRealtimeData.json")
    symo.add(METER_PATH, {"Scope": "System"}, handler=handler)
    meters = (await api.system_meter_data()).data
    assert set(meters) == {"0"}
    assert handler.calls == 2


async def test_retries_disabled(
    symo: MockFronius, session: aiohttp.ClientSession
) -> None:
    handler = SequenceHandler([8, 0], "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    api = FroniusSolarApi(session, symo.url, status_retries=0)
    with pytest.raises(StatusError):
        await api.inverter_common_data(1)
    assert handler.calls == 1


async def test_retry_delay(symo: MockFronius, session: aiohttp.ClientSession) -> None:
    handler = SequenceHandler([8, 8, 0], "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    api = FroniusSolarApi(session, symo.url, retry_delay=0.05)
    await api.inverter_common_data(1)  # resolves the API version
    handler = SequenceHandler([8, 8, 0], "symo/GetInverterRealtimeData_Device_1.json")
    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=handler)
    start = time.monotonic()
    await api.inverter_common_data(1)
    assert time.monotonic() - start >= 0.1
    assert handler.calls == 3


async def test_connection_errors_not_retried(
    symo: MockFronius, session: aiohttp.ClientSession
) -> None:
    calls = 0

    async def _hang(request: web.Request) -> web.StreamResponse:
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return web.Response(text="{}")

    symo.add(INVERTER_PATH, INVERTER_QUERY, handler=_hang)
    api = FroniusSolarApi(session, symo.url, timeout=0.05, retry_delay=0)
    await api.inverter_info()  # resolves the API version
    with pytest.raises(FroniusConnectionError, match="timed out"):
        await api.inverter_common_data(1)
    assert calls == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"status_retries": -1}, id="negative_retries"),
        pytest.param({"retry_delay": -0.1}, id="negative_delay"),
    ],
)
def test_invalid_retry_options(
    session: aiohttp.ClientSession, kwargs: dict[str, float]
) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        FroniusSolarApi(session, "fronius", **kwargs)  # type: ignore[arg-type]
