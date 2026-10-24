"""Tests of the HTTP client: version detection, URLs and error handling."""

from __future__ import annotations

import asyncio

import aiohttp
import pytest
from aiohttp import web

from fronius_solarapi import (
    ApiVersion,
    EndpointNotFoundError,
    FroniusConnectionError,
    FroniusSolarApi,
    InvalidResponseError,
    NotSupportedError,
    RequestNotSupportedError,
    StatusCode,
    StatusError,
)
from fronius_solarapi.client import MAX_CONCURRENT_REQUESTS

from .conftest import MockFronius, load_fixture

LN_TIMEOUT_QUERY = {
    "Scope": "Device",
    "DeviceId": "1",
    "DataCollection": "CommonInverterData",
}


@pytest.mark.parametrize(
    ("host", "url"),
    [
        ("fronius", "http://fronius"),
        ("192.168.0.10/", "http://192.168.0.10"),
        ("http://fronius:8080", "http://fronius:8080"),
        ("https://fronius/", "https://fronius"),
    ],
)
def test_url_normalization(session: aiohttp.ClientSession, host: str, url: str) -> None:
    assert FroniusSolarApi(session, host).url == url


async def test_api_version_v1(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("symo")
    assert api.api_version is None
    info = await api.fetch_api_version()
    assert info.api_version is ApiVersion.V1
    assert info.base_url == "/solar_api/v1/"
    assert info.compatibility_range == "1.6-3"
    # fetching the version does not resolve it, the first request does
    assert api.api_version is None
    await api.inverter_info()
    assert api.api_version is ApiVersion.V1
    assert mock_fronius.requests == [
        ("/solar_api/GetAPIVersion.cgi", {}),
        ("/solar_api/GetAPIVersion.cgi", {}),
        ("/solar_api/v1/GetInverterInfo.cgi", {}),
    ]


async def test_api_version_v0_from_404(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("datamanager_v0")
    info = await api.fetch_api_version()
    assert info.api_version is ApiVersion.V0
    assert info.base_url == "/solar_api/"
    assert info.compatibility_range is None


async def test_api_version_v0_explicit_answer(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("datamanager_v0")
    mock_fronius.add(
        "/solar_api/GetAPIVersion.cgi", fixture="synthetic/GetAPIVersion_v0.json"
    )
    response = await api.inverter_common_data(1)
    assert api.api_version is ApiVersion.V0
    assert response.data.power_ac == 1762
    assert mock_fronius.requests[-1] == (
        "/solar_api/GetInverterRealtimeData.cgi",
        {
            "Scope": "Device",
            "DeviceIndex": "1",
            "DataCollection": "CommonInverterData",
        },
    )


async def test_api_version_unknown(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.add(
        "/solar_api/GetAPIVersion.cgi", fixture="synthetic/GetAPIVersion_future.json"
    )
    with pytest.raises(InvalidResponseError, match="Unknown API version 2"):
        await api.inverter_info()


async def test_api_version_given(
    mock_fronius: MockFronius, session: aiohttp.ClientSession
) -> None:
    mock_fronius.use_fixture_set("symo")
    api = FroniusSolarApi(session, mock_fronius.url, api_version=ApiVersion.V1)
    await api.inverter_info()
    assert mock_fronius.requests == [("/solar_api/v1/GetInverterInfo.cgi", {})]


async def test_v1_query_parameters(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("primo_s0")
    await api.inverter_common_data(2)
    await api.system_meter_data()
    await api.power_flow()
    assert mock_fronius.requests[1:] == [
        (
            "/solar_api/v1/GetInverterRealtimeData.cgi",
            {
                "Scope": "Device",
                "DeviceId": "2",
                "DataCollection": "CommonInverterData",
            },
        ),
        ("/solar_api/v1/GetMeterRealtimeData.cgi", {"Scope": "System"}),
        ("/solar_api/v1/GetPowerFlowRealtimeData.fcgi", {}),
    ]


@pytest.mark.parametrize(
    "request_name",
    [
        "logger_led_info",
        "system_meter_data",
        "system_storage_data",
        "system_ohmpilot_data",
        "power_flow",
    ],
)
async def test_v0_not_supported(
    mock_fronius: MockFronius, api: FroniusSolarApi, request_name: str
) -> None:
    mock_fronius.use_fixture_set("datamanager_v0")
    with pytest.raises(NotSupportedError, match="not available on Solar API v0"):
        await getattr(api, request_name)()
    # nothing but the version query reached the device
    assert mock_fronius.requests == [("/solar_api/GetAPIVersion.cgi", {})]


async def test_v0_active_device_info(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("datamanager_v0")
    for device_class in ("Inverter", "SensorCard", "StringControl"):
        mock_fronius.add(
            "/solar_api/GetActiveDeviceInfo.cgi",
            {"DeviceClass": device_class},
            text=(
                '{"Head": {"Status": {"Code": 0, "Reason": "", "UserMessage": ""},'
                ' "Timestamp": "2019-06-12T15:31:02+02:00"},'
                f' "Body": {{"Data": {{"{device_class}1": {{"DT": 192}}}}}}}}'
            ),
        )
    response = await api.active_device_info()
    assert set(response.data.inverters) == {"Inverter1"}
    assert set(response.data.sensor_cards) == {"SensorCard1"}
    assert set(response.data.string_controls) == {"StringControl1"}
    assert response.data.meters == {}
    assert response.data.storages == {}
    assert response.data.ohmpilots == {}


async def test_request_not_supported_code_255(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("symo")
    with pytest.raises(RequestNotSupportedError) as excinfo:
        await api.system_storage_data()
    assert excinfo.value.code == 255
    assert excinfo.value.status_code is StatusCode.UNKNOWN_ERROR
    assert "not supported by this device" in excinfo.value.reason
    assert isinstance(excinfo.value, NotSupportedError)
    assert isinstance(excinfo.value, StatusError)


async def test_request_not_supported_code_11(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("gen24")
    with pytest.raises(RequestNotSupportedError) as excinfo:
        await api.logger_info()
    assert excinfo.value.status_code is StatusCode.NOT_SUPPORTED
    assert excinfo.value.head.timestamp.isoformat() == "2021-11-26T11:07:53+00:00"
    assert str(excinfo.value) == (
        "GetLoggerInfo.cgi answered with status 11 (The operation or feature is"
        " not supported): v1/GetLoggerInfo.cgi request is not supported."
    )


async def test_status_error(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("symo")
    mock_fronius.add(
        "/solar_api/v1/GetInverterRealtimeData.cgi",
        LN_TIMEOUT_QUERY,
        fixture="synthetic/GetInverterRealtimeData_ln_timeout.json",
    )
    with pytest.raises(StatusError) as excinfo:
        await api.inverter_common_data(1)
    assert not isinstance(excinfo.value, NotSupportedError)
    assert excinfo.value.code == 8
    assert excinfo.value.status_code is StatusCode.LN_REQUEST_TIMEOUT
    assert excinfo.value.endpoint == "GetInverterRealtimeData.cgi"
    assert excinfo.value.reason == "LNRequestTimeout"
    assert excinfo.value.user_message == ""


async def test_undocumented_status_code(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("symo")
    mock_fronius.add(
        "/solar_api/v1/GetInverterInfo.cgi",
        text=(
            '{"Head": {"Status": {"Code": 42, "Reason": "", "UserMessage": ""},'
            ' "Timestamp": "2019-06-12T15:31:02+02:00"}, "Body": {"Data": {}}}'
        ),
    )
    with pytest.raises(StatusError, match=r"status 42 \(Unknown status code\)$") as exc:
        await api.inverter_info()
    assert exc.value.status_code is None


async def test_endpoint_not_found(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("gen24")
    # the Solar API is disabled in the web interface of this GEN24
    mock_fronius.not_found_body = "Solar API disabled by customer config"
    with pytest.raises(EndpointNotFoundError, match="HTTP 404"):
        await api.logger_led_info()


async def test_http_error(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("gen24")
    mock_fronius.add("/solar_api/v1/GetInverterInfo.cgi", status=500, text="boom")
    with pytest.raises(InvalidResponseError, match="HTTP 500"):
        await api.inverter_info()


async def test_non_json(mock_fronius: MockFronius, api: FroniusSolarApi) -> None:
    mock_fronius.use_fixture_set("gen24")
    mock_fronius.add(
        "/solar_api/v1/GetInverterInfo.cgi", text="<html/>", content_type="text/html"
    )
    with pytest.raises(InvalidResponseError, match="non-JSON"):
        await api.inverter_info()


async def test_text_javascript_content_type(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("symo")
    mock_fronius.add(
        "/solar_api/v1/GetInverterInfo.cgi",
        fixture="symo/GetInverterInfo.json",
        content_type="text/javascript",
    )
    response = await api.inverter_info()
    assert response.data["1"].custom_name == "Symo 20"


@pytest.mark.parametrize(
    ("fixture", "match"),
    [
        ("igplus_v2/GetStorageRealtimeData.json", "header is incomplete"),
        ("synthetic/no_head.json", "header is incomplete"),
        ("synthetic/bad_timestamp.json", "Invalid timestamp"),
        ("synthetic/no_body.json", "Body is not a JSON object"),
        ("synthetic/wrong_types.json", "Value is not a number"),
    ],
)
async def test_malformed_responses(
    mock_fronius: MockFronius, api: FroniusSolarApi, fixture: str, match: str
) -> None:
    mock_fronius.use_fixture_set("gen24")
    mock_fronius.add(
        "/solar_api/v1/GetInverterRealtimeData.cgi", LN_TIMEOUT_QUERY, fixture=fixture
    )
    with pytest.raises(InvalidResponseError, match=match):
        await api.inverter_common_data(1)


async def test_api_version_malformed(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.add(
        "/solar_api/GetAPIVersion.cgi", text='{"BaseURL": "/solar_api/v1/"}'
    )
    with pytest.raises(InvalidResponseError, match="incomplete"):
        await api.fetch_api_version()


async def test_connection_refused(session: aiohttp.ClientSession) -> None:
    api = FroniusSolarApi(session, "http://127.0.0.1:1")
    with pytest.raises(FroniusConnectionError, match="failed"):
        await api.inverter_info()


async def test_timeout(
    mock_fronius: MockFronius, session: aiohttp.ClientSession
) -> None:
    async def _hang(request: web.Request) -> web.StreamResponse:
        await asyncio.sleep(1)
        return web.Response(text="{}")

    mock_fronius.add("/solar_api/GetAPIVersion.cgi", handler=_hang)
    api = FroniusSolarApi(session, mock_fronius.url, timeout=0.05)
    with pytest.raises(FroniusConnectionError, match="timed out"):
        await api.inverter_info()


async def test_client_timeout_object(
    mock_fronius: MockFronius, session: aiohttp.ClientSession
) -> None:
    mock_fronius.use_fixture_set("symo")
    api = FroniusSolarApi(
        session,
        mock_fronius.url,
        timeout=aiohttp.ClientTimeout(total=5),
    )
    assert (await api.inverter_info()).data["1"].unique_id == "1234567"


async def test_concurrency_limit(
    mock_fronius: MockFronius, api: FroniusSolarApi
) -> None:
    mock_fronius.use_fixture_set("symo")
    in_flight = 0
    seen = 0

    async def _slow(request: web.Request) -> web.StreamResponse:
        nonlocal in_flight, seen
        in_flight += 1
        seen = max(seen, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return web.Response(
            text=load_fixture("symo/GetInverterInfo.json"),
            content_type="application/json",
        )

    mock_fronius.add("/solar_api/v1/GetInverterInfo.cgi", handler=_slow)
    await asyncio.gather(*(api.inverter_info() for _ in range(6)))
    assert seen == MAX_CONCURRENT_REQUESTS
