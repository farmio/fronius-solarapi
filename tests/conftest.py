"""Test fixtures: an aiohttp server answering like a Fronius device."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from fronius_solarapi import ApiVersion, FroniusSolarApi

FIXTURES = Path(__file__).parent / "fixtures"
V0_BASE = "/solar_api/"
V1_BASE = "/solar_api/v1/"

type Query = tuple[tuple[str, str], ...]
type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def load_fixture(name: str) -> str:
    """Return the text of a fixture file."""
    return (FIXTURES / name).read_text()


def snapshot_value(value: Any) -> Any:
    """Return a plain data structure of a model for snapshotting."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {key: snapshot_value(item) for key, item in value.items()}
    return value


_DEVICE_FILE = re.compile(
    r"^(?P<endpoint>Get\w+?RealtimeData)_Device_(?P<device_id>\w+?)"
    r"(?:_(?P<collection>Cumulation|3P|[a-z_]+))?$"
)
_COLLECTIONS = {
    None: "CommonInverterData",
    "Cumulation": "CumulationInverterData",
    "3P": "3PInverterData",
}


class MockFronius:
    """Serve fixtures the way a Fronius device would."""

    def __init__(self) -> None:
        """Set up an application catching every request."""
        self._routes: dict[tuple[str, Query], Handler] = {}
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self._handle)
        self.not_found_body = load_fixture("error_404.html")
        self.api_version = ApiVersion.V1
        self.url = ""

    @property
    def base(self) -> str:
        """Return the base path of the served API version."""
        return V0_BASE if self.api_version is ApiVersion.V0 else V1_BASE

    @property
    def device_id_param(self) -> str:
        """Return the device id parameter name of the served API version."""
        return "DeviceIndex" if self.api_version is ApiVersion.V0 else "DeviceId"

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        query = dict(request.query)
        self.requests.append((request.path, query))
        key = (request.path, tuple(sorted(query.items())))
        if (handler := self._routes.get(key)) is None:
            return web.Response(
                status=404, text=self.not_found_body, content_type="text/html"
            )
        return await handler(request)

    def add(
        self,
        path: str,
        query: dict[str, str] | None = None,
        *,
        text: str = "",
        fixture: str | None = None,
        status: int = 200,
        content_type: str = "application/json",
        handler: Handler | None = None,
    ) -> None:
        """Register a response for a path and exact query."""
        if fixture is not None:
            text = load_fixture(fixture)

        async def _respond(request: web.Request) -> web.StreamResponse:
            return web.Response(status=status, text=text, content_type=content_type)

        key = (path, tuple(sorted((query or {}).items())))
        self._routes[key] = handler or _respond

    def add_device_endpoint(
        self,
        endpoint: str,
        device_id: str,
        *,
        fixture: str,
        collection: str | None = None,
    ) -> None:
        """Register a `Scope=Device` response for the served API version."""
        query = {"Scope": "Device", self.device_id_param: device_id}
        if collection is not None:
            query["DataCollection"] = collection
        self.add(f"{self.base}{endpoint}.cgi", query, fixture=fixture)

    def use_fixture_set(self, name: str, *, night: bool = False) -> None:
        """Register every file of a fixture set under its endpoint.

        File names follow the Home Assistant fixtures: `<Endpoint>.json` for
        system requests, `<Endpoint>_Device_<id>[_<collection>].json` for
        device requests and a `_night` suffix for variants served when
        `night` is set. A set without `GetAPIVersion.json` is served as v0.
        """
        files = {path.stem: path for path in (FIXTURES / name).glob("*.json")}
        self.api_version = ApiVersion.V1 if "GetAPIVersion" in files else ApiVersion.V0
        variants = [stem for stem in files if not stem.endswith("_night")]
        if night:
            variants += [stem for stem in files if stem.endswith("_night")]
        for stem in variants:
            self._register(name, stem.removesuffix("_night"), files[stem])

    def _register(self, set_name: str, stem: str, path: Path) -> None:
        fixture = f"{set_name}/{path.name}"
        if stem == "GetAPIVersion":
            self.add("/solar_api/GetAPIVersion.cgi", fixture=fixture)
        elif stem == "GetPowerFlowRealtimeData":
            self.add(f"{self.base}GetPowerFlowRealtimeData.fcgi", fixture=fixture)
        elif stem in ("GetLoggerInfo", "GetLoggerLEDInfo", "GetInverterInfo"):
            self.add(f"{self.base}{stem}.cgi", fixture=fixture)
        elif stem == "GetActiveDeviceInfo":
            self.add(
                f"{self.base}{stem}.cgi", {"DeviceClass": "System"}, fixture=fixture
            )
        elif stem.startswith("GetActiveDeviceInfo_"):
            device_class = stem.removeprefix("GetActiveDeviceInfo_")
            self.add(
                f"{self.base}GetActiveDeviceInfo.cgi",
                {"DeviceClass": device_class},
                fixture=fixture,
            )
        elif stem.endswith("RealtimeData") or stem.endswith("RealtimeData_System"):
            endpoint = stem.removesuffix("_System")
            self.add(f"{self.base}{endpoint}.cgi", {"Scope": "System"}, fixture=fixture)
        elif (match := _DEVICE_FILE.match(stem)) is not None:
            collection = match["collection"]
            if match["endpoint"] == "GetInverterRealtimeData":
                collection = _COLLECTIONS.get(collection, collection)
            else:
                # a suffix on other endpoints only names a variant
                collection = None
            self.add_device_endpoint(
                match["endpoint"],
                match["device_id"],
                fixture=fixture,
                collection=collection,
            )
        else:
            raise ValueError(f"Fixture file {path} does not name an endpoint")


@pytest.fixture
async def mock_fronius() -> AsyncIterator[MockFronius]:
    """Return a mock device served by a test server."""
    mock = MockFronius()
    async with TestServer(mock.app) as server:
        mock.url = str(server.make_url(""))
        yield mock


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    """Return a client session."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def api(mock_fronius: MockFronius, session: aiohttp.ClientSession) -> FroniusSolarApi:
    """Return a client for the mock device."""
    return FroniusSolarApi(session, mock_fronius.url)
