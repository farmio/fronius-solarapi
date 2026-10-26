# fronius-solarapi

Async Python library for the [Fronius Solar API](https://www.fronius.com/en/solar-energy/installers-partners/technical-data/all-products/system-monitoring/open-interfaces/fronius-solar-api-json-),
the JSON interface of Fronius Datamanager, Datalogger Web, Symo Hybrid and
GEN24/Tauro/Verto devices. Built on [aiohttp](https://docs.aiohttp.org).

> [!WARNING]
> **Alpha version.** The parsers are verified against recorded responses of a
> Symo (Datamanager 2.0), a Primo pair with an S0 meter, an IG Plus, two GEN24
> (one with a BYD battery and an Ohmpilot), a Datamanager serving API v0 and
> the examples of the official specification. Expect breaking API changes while
> the Home Assistant integration moves over. Feedback and recordings of other
> devices are very welcome!

Supports both API versions:

- **v1** (`/solar_api/v1/`) — every Datamanager 2.0, Symo Hybrid and
  GEN24/Tauro/Verto device
- **v0** (`/solar_api/`) — first generation Datalogger Web and Datamanager 1.0;
  only inverter, logger and active device requests exist there

The highest version a device supports is detected on the first request, as the
spec describes: a device without `GetAPIVersion.cgi` serves v0.

## Requests

Every request returns a `Response[T]` with the common response `head`
(timestamp, status, request arguments) and the typed `data`:

| Method | Returns `data` | Solar API request |
| --- | --- | --- |
| `fetch_api_version()` | `ApiVersionInfo` (no head) | `GetAPIVersion.cgi` |
| `inverter_info()` | `dict[str, InverterInfo]` | `GetInverterInfo.cgi` |
| `logger_info()` | `LoggerInfo` | `GetLoggerInfo.cgi` |
| `logger_led_info()` | `LoggerLedInfo` | `GetLoggerLEDInfo.cgi` |
| `active_device_info()` | `ActiveDeviceInfo` | `GetActiveDeviceInfo.cgi?DeviceClass=System` |
| `inverter_common_data(id)` | `CommonInverterData` | `GetInverterRealtimeData.cgi` CommonInverterData |
| `inverter_3p_data(id)` | `ThreePhaseInverterData` | `GetInverterRealtimeData.cgi` 3PInverterData |
| `inverter_cumulation_data(id)` | `CumulationInverterData` | `GetInverterRealtimeData.cgi` CumulationInverterData |
| `system_inverter_data()` | `dict[str, CumulationInverterData]` | `GetInverterRealtimeData.cgi?Scope=System` |
| `meter_data(id)` / `system_meter_data()` | `MeterData` / `dict[str, MeterData]` | `GetMeterRealtimeData.cgi` |
| `storage_data(id)` / `system_storage_data()` | `StorageData` / `dict[str, StorageData]` | `GetStorageRealtimeData.cgi` |
| `ohmpilot_data(id)` / `system_ohmpilot_data()` | `OhmpilotData` / `dict[str, OhmpilotData]` | `GetOhmPilotRealtimeData.cgi` |
| `power_flow()` | `PowerFlow` | `GetPowerFlowRealtimeData.fcgi` |

System scope results and the active device info are keyed by the device id the
device reports (the Solar Net address, `"1"` on GEN24).

All models are frozen dataclasses. Measurements are `float | None` in the base
unit of the API (W, VA, VAr, Wh, VArh, V, A, Hz, °C, percent), kept as `int`
where the device reports a number without fraction. Inverter values come with
their unit, which is checked against the documented one rather than passed on
(`null` values are not checked);
codes are
`int | None`; flags are `bool | None`. `None` means the device did not report
the value. Lookups for the codes are included: `InverterInfo.model` and
`PowerFlowInverter.model` resolve the device type table of the spec,
`InverterInfo.state` and `DeviceStatus.state` the inverter status codes,
`MeterData.meter_location` the meter location codes and `OhmpilotData.state`
the Ohmpilot state codes. Battery states are decoded as the spec describes:
`StorageModule.cell_state` and `previous_cell_state` for Fronius Solar Battery
modules, and `StorageController.state` for LG Chem RESU H and BYD Battery-Box
controllers. The known string values of power flow mode, battery mode, meter
location, secondary meter category, Ohmpilot and Ohmpilot Eco states and LED
color/state are available as `StrEnum`s for comparison.

## Errors

All errors derive from `FroniusError`:

- `FroniusConnectionError` — the device is unreachable or did not answer in time
- `InvalidResponseError` — the answer is not a valid Solar API response
  (non-JSON, missing header, wrong types, or an inverter value reported in
  another unit than the model documents)
  - `EndpointNotFoundError` — HTTP 404; GEN24 devices answer every request this
    way while the Solar API is disabled in their web interface
- `NotSupportedError` — the request does not exist on the API version served
  (e.g. meters on v0); raised before anything is sent
- `StatusError` — the response header carries a non-zero status code, with
  `code`, `reason`, `user_message` and the parsed `head`
  - `RequestNotSupportedError` — the device reported code 11 (NotSupported) or
    code 255 with a "not supported" reason, as older firmware does for e.g.
    storages on devices without one; also a `NotSupportedError`

Datamanagers reach inverters, meters and storages over Solar Net, whose
requests fail now and then (about 1 % of inverter requests on Symo devices end
in `LNRequestTimeout`). Answers with the status codes 7, 8 and 9 (Solar Net
request error, timeout and parse error) are therefore repeated up to
`status_retries` times (default 2) after `retry_delay` seconds (default 0.5).
Every other status code, connection errors and timeouts are raised right away;
backing off from an unreachable device is left to the caller.

## Usage

```python
import aiohttp

from fronius_solarapi import FroniusSolarApi, NotSupportedError

async with aiohttp.ClientSession() as session:
    api = FroniusSolarApi(session, "192.168.0.10")

    inverters = (await api.inverter_info()).data
    for device_id, inverter in inverters.items():
        data = (await api.inverter_common_data(device_id)).data
        print(inverter.custom_name, inverter.model, data.power_ac, "W")

    try:
        flow = (await api.power_flow()).data
    except NotSupportedError:
        print("no power flow on this device")
    else:
        print(flow.site.power_grid, flow.site.power_load, flow.site.power_photovoltaics)
```

The connection lifecycle stays with the caller. GEN24 firmware 1.35 and later
redirects requests from non-private IP addresses to HTTPS with a self-signed
certificate; a session for such a device needs SSL verification disabled.
Requests are limited to two in parallel per client, as the spec asks for, and
time out after 10 seconds by default (`timeout=`).

`scripts/dump.py <host>` prints everything a device reports.

## Fronius quirks handled

- `GetLoggerInfo.cgi` puts its body under `Body.LoggerInfo`, every other
  request under `Body.Data`.
- Datamanagers HTML-escape `CustomName`, `CashCurrency` and `CO2Unit`, GEN24
  devices send plain UTF-8.
- A negative `UTCOffset` is reported as unsigned 32 bit integer.
- GEN24 devices encode integers and flags as floats (`"Visible": 1.0`,
  `"CodeOfState": 0.0`).
- GEN24 firmware before 1.13.5 reports the inverter state string as
  `StatusCode`.
- `ErrorCode` -1 means no valid error code.
- A GEN24 Primo was seen reporting `"DeviceStatus:"` (trailing colon) in the
  cumulation collection.
- GEN24 devices answer `Scope=System` inverter requests with `Value` instead of
  `Values`, and list their inverters at the top level of the active device
  info instead of inside `Inverter`.
- Some GEN24 firmware reports meter channels under internal names
  (`SMARTMETER_*`, `ACBRIDGE_*`).
- The power flow `Version` is an integer within a string, and absent on old
  Datamanagers.
- API v0 names the device parameter `DeviceIndex` and has no system scope for
  active devices, so one request per device class is made.
- The content type of responses is not checked, as some devices send
  `text/javascript`.

## Development

```sh
uv sync
uv run pytest
uv run coverage run -m pytest && uv run coverage combine && uv run coverage report
uv run ruff check . && uv run ruff format --check . && uv run mypy fronius_solarapi tests scripts
```

Recorded device responses live in `tests/fixtures`. The sets `symo`, `gen24`,
`gen24_storage`, `igplus_v2` and `primo_s0` are shared with the Home Assistant
integration, `datamanager_v0` and `datamanager_v1` come from pyfronius and
`spec_listings` from the examples in the official specification. Every request
is snapshotted against every set with [syrupy](https://github.com/syrupy-project/syrupy).

## Acknowledgements

This library replaces [pyfronius](https://github.com/nielstron/pyfronius) by
Niels Mündler and Gerrit Beine, whose handling of device quirks it inherits.
