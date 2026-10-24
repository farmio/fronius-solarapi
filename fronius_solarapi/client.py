"""The Solar API client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Final

import aiohttp

from .const import (
    API_BASE_PATHS,
    API_VERSION_PATH,
    ApiVersion,
    DeviceClass,
    StatusCode,
)
from .exceptions import (
    EndpointNotFoundError,
    FroniusConnectionError,
    InvalidResponseError,
    NotSupportedError,
    RequestNotSupportedError,
    StatusError,
)
from .models import (
    ActiveDeviceInfo,
    ApiVersionInfo,
    CommonInverterData,
    CumulationInverterData,
    InverterInfo,
    LoggerInfo,
    LoggerLedInfo,
    MeterData,
    OhmpilotData,
    PowerFlow,
    Response,
    StorageData,
    ThreePhaseInverterData,
)
from .parsers import (
    JsonObject,
    body_data,
    parse_3p_inverter_data,
    parse_active_device_info,
    parse_active_devices,
    parse_api_version,
    parse_common_inverter_data,
    parse_cumulation_inverter_data,
    parse_head,
    parse_inverter_info,
    parse_logger_info,
    parse_logger_led_info,
    parse_meter_data,
    parse_ohmpilot_data,
    parse_power_flow,
    parse_storage_data,
    parse_system_inverter_data,
    parse_system_meter_data,
    parse_system_ohmpilot_data,
    parse_system_storage_data,
)

_LOGGER = logging.getLogger(__name__)

ALL_VERSIONS: Final = frozenset(ApiVersion)
V1_ONLY: Final = frozenset({ApiVersion.V1})

# the spec allows two realtime requests in parallel (section 2.6)
MAX_CONCURRENT_REQUESTS: Final = 2
DEFAULT_TIMEOUT: Final = 10.0

_DEVICE_ID_PARAM: Final = {ApiVersion.V0: "DeviceIndex", ApiVersion.V1: "DeviceId"}
_V0_ACTIVE_DEVICE_CLASSES: Final = (
    (DeviceClass.INVERTER, "inverters"),
    (DeviceClass.SENSOR_CARD, "sensor_cards"),
    (DeviceClass.STRING_CONTROL, "string_controls"),
)


class FroniusSolarApi:
    """Client for the Solar API of one Fronius device.

    The connection lifecycle stays with the caller: pass an
    `aiohttp.ClientSession`. GEN24 firmware 1.35 and later redirects requests
    from non-private IP addresses to HTTPS with a self-signed certificate, so a
    session reaching such a device needs to be created with SSL verification
    disabled.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        api_version: ApiVersion | None = None,
        timeout: float | aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client.

        `host` is a host name, an IP address or a full URL. Without a scheme
        plain HTTP is used, which is all most devices support. Without
        `api_version` the highest version the device supports is used; it is
        queried once on the first request.
        """
        self._session = session
        url = host.rstrip("/")
        if "://" not in url:
            url = f"http://{url}"
        self._url = url
        self._api_version = api_version
        self._timeout = (
            timeout
            if isinstance(timeout, aiohttp.ClientTimeout)
            else aiohttp.ClientTimeout(total=timeout)
        )
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    @property
    def url(self) -> str:
        """Return the base URL of the device, e.g. "http://192.168.0.10"."""
        return self._url

    @property
    def api_version(self) -> ApiVersion | None:
        """Return the API version in use, `None` before it has been resolved."""
        return self._api_version

    async def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self._url}{path}"
        _LOGGER.debug("Requesting %s %s", url, params or "")
        try:
            async with (
                self._semaphore,
                self._session.get(url, params=params, timeout=self._timeout) as res,
            ):
                if res.status == 404:
                    raise EndpointNotFoundError(f"{url} not found (HTTP 404)")
                if res.status >= 400:
                    raise InvalidResponseError(f"{url} answered HTTP {res.status}")
                text = await res.text()
        except TimeoutError as err:
            raise FroniusConnectionError(f"Request to {url} timed out") from err
        except aiohttp.ClientError as err:
            raise FroniusConnectionError(f"Request to {url} failed: {err}") from err
        # the content type is text/javascript on some devices, so it is not checked
        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            raise InvalidResponseError(
                f"{url} answered non-JSON: {text[:80]!r}"
            ) from err

    async def fetch_api_version(self) -> ApiVersionInfo:
        """Query the highest API version the device supports.

        Devices only serving API v0 answer with HTTP 404 (spec v0 section
        2.3.1), which is reported as version 0.
        """
        try:
            raw = await self._get_json(API_VERSION_PATH)
        except EndpointNotFoundError:
            return ApiVersionInfo(
                api_version=ApiVersion.V0,
                base_url=API_BASE_PATHS[ApiVersion.V0],
                compatibility_range=None,
            )
        return parse_api_version(raw)

    async def _resolve_api_version(self) -> ApiVersion:
        if self._api_version is None:
            info = await self.fetch_api_version()
            _LOGGER.debug(
                "%s serves Solar API v%s (%s)",
                self._url,
                info.api_version,
                info.compatibility_range,
            )
            self._api_version = info.api_version
        return self._api_version

    async def _request[T](
        self,
        endpoint: str,
        parse: Callable[[JsonObject], T],
        params: dict[str, str] | None = None,
        *,
        device_id: str | int | None = None,
        versions: frozenset[ApiVersion] = ALL_VERSIONS,
    ) -> Response[T]:
        api_version = await self._resolve_api_version()
        if api_version not in versions:
            raise NotSupportedError(
                f"{endpoint} is not available on Solar API v{api_version}"
            )
        query = dict(params or {})
        if device_id is not None:
            # the device id has to follow the scope parameter
            query[_DEVICE_ID_PARAM[api_version]] = str(device_id)
            if "DataCollection" in query:
                query["DataCollection"] = query.pop("DataCollection")
        raw = await self._get_json(f"{API_BASE_PATHS[api_version]}{endpoint}", query)
        head = parse_head(raw)
        if head.status.code != StatusCode.OKAY:
            if head.status.code == StatusCode.NOT_SUPPORTED or (
                head.status.code == StatusCode.UNKNOWN_ERROR
                and "not supported" in head.status.reason.lower()
            ):
                raise RequestNotSupportedError(endpoint, head)
            raise StatusError(endpoint, head)
        return Response(head=head, data=parse(body_data(raw)))

    async def inverter_info(self) -> Response[dict[str, InverterInfo]]:
        """Return all inverters seen by the logging device, keyed by device id.

        Inverters that have been offline for less than 24 hours are included.
        """
        return await self._request("GetInverterInfo.cgi", parse_inverter_info)

    async def logger_info(self) -> Response[LoggerInfo]:
        """Return information about the logging device.

        GEN24/Tauro/Verto devices report the request as not supported.
        """
        return await self._request("GetLoggerInfo.cgi", parse_logger_info)

    async def logger_led_info(self) -> Response[LoggerLedInfo]:
        """Return the states of the LEDs of the logging device.

        GEN24/Tauro/Verto devices report the request as not supported.
        """
        return await self._request(
            "GetLoggerLEDInfo.cgi", parse_logger_led_info, versions=V1_ONLY
        )

    async def active_device_info(self) -> Response[ActiveDeviceInfo]:
        """Return the devices that are currently online.

        API v0 has no system scope, so one request per device class it knows
        is made and the header of the first one is returned.
        """
        if await self._resolve_api_version() is ApiVersion.V1:
            return await self._request(
                "GetActiveDeviceInfo.cgi",
                parse_active_device_info,
                {"DeviceClass": DeviceClass.SYSTEM},
            )
        classes: dict[str, Any] = {
            "meters": {},
            "ohmpilots": {},
            "storages": {},
        }
        head = None
        for device_class, attribute in _V0_ACTIVE_DEVICE_CLASSES:
            response = await self._request(
                "GetActiveDeviceInfo.cgi",
                parse_active_devices,
                {"DeviceClass": device_class},
            )
            head = head or response.head
            classes[attribute] = response.data
        if head is None:  # pragma: no cover - the loop always runs
            raise InvalidResponseError("No active device info received")
        return Response(head=head, data=ActiveDeviceInfo(**classes))

    async def inverter_common_data(
        self, device_id: str | int
    ) -> Response[CommonInverterData]:
        """Return the `CommonInverterData` collection of one inverter."""
        return await self._request(
            "GetInverterRealtimeData.cgi",
            parse_common_inverter_data,
            {"Scope": "Device", "DataCollection": "CommonInverterData"},
            device_id=device_id,
        )

    async def inverter_3p_data(
        self, device_id: str | int
    ) -> Response[ThreePhaseInverterData]:
        """Return the `3PInverterData` collection of one three-phase inverter."""
        return await self._request(
            "GetInverterRealtimeData.cgi",
            parse_3p_inverter_data,
            {"Scope": "Device", "DataCollection": "3PInverterData"},
            device_id=device_id,
        )

    async def inverter_cumulation_data(
        self, device_id: str | int
    ) -> Response[CumulationInverterData]:
        """Return the `CumulationInverterData` collection of one inverter."""
        return await self._request(
            "GetInverterRealtimeData.cgi",
            parse_cumulation_inverter_data,
            {"Scope": "Device", "DataCollection": "CumulationInverterData"},
            device_id=device_id,
        )

    async def system_inverter_data(self) -> Response[dict[str, CumulationInverterData]]:
        """Return the cumulation values of all inverters, keyed by device id."""
        return await self._request(
            "GetInverterRealtimeData.cgi",
            parse_system_inverter_data,
            {"Scope": "System"},
        )

    async def meter_data(self, device_id: str | int) -> Response[MeterData]:
        """Return the data of one meter."""
        return await self._request(
            "GetMeterRealtimeData.cgi",
            parse_meter_data,
            {"Scope": "Device"},
            device_id=device_id,
            versions=V1_ONLY,
        )

    async def system_meter_data(self) -> Response[dict[str, MeterData]]:
        """Return the data of all meters, keyed by device id."""
        return await self._request(
            "GetMeterRealtimeData.cgi",
            parse_system_meter_data,
            {"Scope": "System"},
            versions=V1_ONLY,
        )

    async def storage_data(self, device_id: str | int) -> Response[StorageData]:
        """Return the data of one storage."""
        return await self._request(
            "GetStorageRealtimeData.cgi",
            parse_storage_data,
            {"Scope": "Device"},
            device_id=device_id,
            versions=V1_ONLY,
        )

    async def system_storage_data(self) -> Response[dict[str, StorageData]]:
        """Return the data of all storages, keyed by device id."""
        return await self._request(
            "GetStorageRealtimeData.cgi",
            parse_system_storage_data,
            {"Scope": "System"},
            versions=V1_ONLY,
        )

    async def ohmpilot_data(self, device_id: str | int) -> Response[OhmpilotData]:
        """Return the data of one Ohmpilot."""
        return await self._request(
            "GetOhmPilotRealtimeData.cgi",
            parse_ohmpilot_data,
            {"Scope": "Device"},
            device_id=device_id,
            versions=V1_ONLY,
        )

    async def system_ohmpilot_data(self) -> Response[dict[str, OhmpilotData]]:
        """Return the data of all Ohmpilots, keyed by device id."""
        return await self._request(
            "GetOhmPilotRealtimeData.cgi",
            parse_system_ohmpilot_data,
            {"Scope": "System"},
            versions=V1_ONLY,
        )

    async def power_flow(self) -> Response[PowerFlow]:
        """Return the current power flow of the site."""
        return await self._request(
            "GetPowerFlowRealtimeData.fcgi", parse_power_flow, versions=V1_ONLY
        )
