"""Print everything a Fronius device reports over the Solar API.

Usage: uv run scripts/dump.py <host> [--insecure]
"""

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from functools import partial
from typing import Any

import aiohttp

from fronius_solarapi import FroniusError, FroniusSolarApi


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return value if isinstance(value, int | float | str | bool | None) else str(value)


async def _dump(host: str, insecure: bool) -> None:
    connector = aiohttp.TCPConnector(ssl=False) if insecure else None
    async with aiohttp.ClientSession(connector=connector) as session:
        api = FroniusSolarApi(session, host)
        print(f"API version: {await api.fetch_api_version()}")
        requests: dict[str, Callable[[], Awaitable[Any]]] = {
            "inverter_info": api.inverter_info,
            "logger_info": api.logger_info,
            "logger_led_info": api.logger_led_info,
            "active_device_info": api.active_device_info,
            "system_inverter_data": api.system_inverter_data,
            "system_meter_data": api.system_meter_data,
            "system_storage_data": api.system_storage_data,
            "system_ohmpilot_data": api.system_ohmpilot_data,
            "power_flow": api.power_flow,
        }
        try:
            inverters = (await api.inverter_info()).data
        except FroniusError as err:
            print(f"inverter_info failed: {err}")
            inverters = {}
        for device_id in inverters:
            requests[f"inverter_common_data({device_id})"] = partial(
                api.inverter_common_data, device_id
            )
            requests[f"inverter_3p_data({device_id})"] = partial(
                api.inverter_3p_data, device_id
            )
        for name, request in requests.items():
            print(f"\n=== {name}")
            try:
                response = await request()
            except FroniusError as err:
                print(f"{type(err).__name__}: {err}")
                continue
            print(json.dumps(_plain(response.data), indent=2, default=str))


def main() -> None:
    """Parse arguments and dump the device."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="host name, IP address or URL of the device")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="accept the self-signed certificate of GEN24 devices on HTTPS",
    )
    args = parser.parse_args()
    asyncio.run(_dump(args.host, args.insecure))


if __name__ == "__main__":
    main()
