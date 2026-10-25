"""Conversion of raw Solar API JSON into typed models.

Every function here tolerates missing channels, as the spec says devices omit
values they cannot provide, and is strict about the shape of what is present.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from html import unescape
from typing import Any, Final

from .const import ApiVersion
from .exceptions import InvalidResponseError
from .models import (
    ActiveDevice,
    ActiveDeviceInfo,
    ApiVersionInfo,
    CommonInverterData,
    CumulationInverterData,
    DeviceDetails,
    DeviceStatus,
    InverterInfo,
    LedStatus,
    LoggerInfo,
    LoggerLedInfo,
    MeterData,
    OhmpilotData,
    PowerFlow,
    PowerFlowInverter,
    PowerFlowOhmpilot,
    PowerFlowOhmpilotEco,
    PowerFlowSecondaryMeter,
    PowerFlowSite,
    ResponseHead,
    ResponseStatus,
    StorageController,
    StorageData,
    StorageModule,
    ThreePhaseInverterData,
)

type JsonObject = dict[str, Any]


def _invalid(message: str) -> InvalidResponseError:
    return InvalidResponseError(message)


def _object(value: Any, what: str) -> JsonObject:
    if not isinstance(value, dict):
        raise _invalid(f"{what} is not a JSON object: {value!r}")
    return value


def _number(data: JsonObject, key: str) -> float | None:
    """Return a number field as reported, an `int` where JSON has no fraction."""
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(f"{key} is not a number: {value!r}")
    return value


def _integer(data: JsonObject, key: str) -> int | None:
    """Return an integer field. GEN24 devices encode some of them as floats."""
    value = _number(data, key)
    return None if value is None else int(value)


def _boolean(data: JsonObject, key: str) -> bool | None:
    """Return a boolean field, which may be encoded as 0/1 or 0.0/1.0."""
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    raise _invalid(f"{key} is not a boolean: {value!r}")


def _string(data: JsonObject, key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(f"{key} is not a string: {value!r}")
    return value


def _html_string(data: JsonObject, key: str) -> str | None:
    """Return a string field that Datamanagers HTML-escape, GEN24 don't."""
    value = _string(data, key)
    return None if value is None else unescape(value)


def _epoch(data: JsonObject, key: str) -> datetime | None:
    """Return a unix timestamp field as aware datetime."""
    value = _number(data, key)
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


# The unit of each inverter channel the models document. The spec says units
# never carry a prefix, so anything else would silently scale the value.
# Channels the spec gives no unit for (ambient temperature, fan speeds) are
# not checked, and neither are `null` values - nothing is scaled then, and
# GEN24 devices always report some channels as `null`.
_CHANNEL_UNITS: Final[dict[str, str]] = {
    "PAC": "W",
    "SAC": "VA",
    "IAC": "A",
    "UAC": "V",
    "FAC": "Hz",
    "IDC": "A",
    "IDC_2": "A",
    "IDC_3": "A",
    "IDC_4": "A",
    "UDC": "V",
    "UDC_2": "V",
    "UDC_3": "V",
    "UDC_4": "V",
    "DAY_ENERGY": "Wh",
    "YEAR_ENERGY": "Wh",
    "TOTAL_ENERGY": "Wh",
    "IAC_L1": "A",
    "IAC_L2": "A",
    "IAC_L3": "A",
    "UAC_L1": "V",
    "UAC_L2": "V",
    "UAC_L3": "V",
}


def _check_unit(key: str, pair: JsonObject) -> None:
    """Raise if a channel is reported in another unit than documented."""
    if (expected := _CHANNEL_UNITS.get(key)) is None:
        return
    if (unit := pair.get("Unit")) is not None and unit != expected:
        raise _invalid(f"{key} is reported in {unit!r} instead of {expected!r}")


def _value_of(data: JsonObject, key: str) -> float | None:
    """Return the `Value` of a value-unit pair."""
    pair = data.get(key)
    if pair is None:
        return None
    pair = _object(pair, key)
    if (value := _number(pair, "Value")) is not None:
        _check_unit(key, pair)
    return value


def _integer_value_of(data: JsonObject, key: str) -> int | None:
    value = _value_of(data, key)
    return None if value is None else int(value)


def _first(data: JsonObject, *keys: str) -> Any:
    """Return the first key present, for channels that are known by aliases."""
    for key in keys:
        if key in data:
            return data[key]
    return None


def _per_device[T](
    data: JsonObject, parse: Callable[[JsonObject], T], what: str
) -> dict[str, T]:
    return {
        device_id: parse(_object(device, f"{what} {device_id}"))
        for device_id, device in data.items()
    }


def parse_api_version(raw: Any) -> ApiVersionInfo:
    """Parse `GetAPIVersion.cgi`."""
    data = _object(raw, "API version response")
    version = _integer(data, "APIVersion")
    base_url = _string(data, "BaseURL")
    if version is None or base_url is None:
        raise _invalid(f"API version response is incomplete: {data!r}")
    try:
        api_version = ApiVersion(version)
    except ValueError as err:
        raise _invalid(f"Unknown API version {version}") from err
    return ApiVersionInfo(
        api_version=api_version,
        base_url=base_url,
        compatibility_range=_string(data, "CompatibilityRange"),
    )


def parse_head(raw: Any) -> ResponseHead:
    """Parse the common response header of a response."""
    response = _object(raw, "Response")
    try:
        head = _object(response["Head"], "Head")
        status = _object(head["Status"], "Head.Status")
        timestamp = head["Timestamp"]
        code = status["Code"]
    except KeyError as err:
        raise _invalid(f"Response header is incomplete: {raw!r}") from err
    if not isinstance(timestamp, str) or isinstance(code, bool | float | str):
        raise _invalid(f"Response header is malformed: {head!r}")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp)
    except ValueError as err:
        raise _invalid(f"Invalid timestamp {timestamp!r}") from err
    return ResponseHead(
        timestamp=parsed_timestamp,
        status=ResponseStatus(
            code=code,
            reason=_string(status, "Reason") or "",
            user_message=_string(status, "UserMessage") or "",
        ),
        request_arguments=_object(
            head.get("RequestArguments", {}), "Head.RequestArguments"
        ),
    )


def body_data(raw: Any) -> JsonObject:
    """Return the body payload of a response.

    `GetLoggerInfo.cgi` deviates from every other request and puts it under
    `Body.LoggerInfo` instead of `Body.Data`.
    """
    body = _object(_object(raw, "Response").get("Body"), "Body")
    data = _first(body, "Data", "LoggerInfo")
    return _object(data, "Body.Data")


def parse_details(data: JsonObject) -> DeviceDetails | None:
    """Parse the `Details` object of meters, storages and Ohmpilots."""
    if (details := data.get("Details")) is None:
        return None
    details = _object(details, "Details")
    return DeviceDetails(
        manufacturer=_html_string(details, "Manufacturer"),
        model=_html_string(details, "Model"),
        # kept as reported: batteries pad it with whitespace, and callers may
        # already use the padded value as an identifier
        serial=_string(details, "Serial"),
        hardware=_string(details, "Hardware"),
        software=_string(details, "Software"),
    )


def _parse_inverter_info(device_id: str, data: JsonObject) -> InverterInfo:
    device_type = _integer(data, "DT")
    unique_id = _string(data, "UniqueID")
    if device_type is None or unique_id is None:
        raise _invalid(f"Inverter info {device_id} is incomplete: {data!r}")
    # GEN24 firmware before 1.13.5 reports the state string as StatusCode
    status_code = data.get("StatusCode")
    inverter_state = _string(data, "InverterState")
    if isinstance(status_code, str):
        inverter_state = inverter_state or status_code
        status_code = None
    else:
        status_code = _integer(data, "StatusCode")
    error_code = _integer(data, "ErrorCode")
    return InverterInfo(
        device_id=device_id,
        device_type=device_type,
        unique_id=unique_id,
        pv_power=_integer(data, "PVPower"),
        custom_name=_html_string(data, "CustomName"),
        show=_boolean(data, "Show"),
        # -1 means that there is no valid error code
        error_code=None if error_code == -1 else error_code,
        status_code=status_code,
        inverter_state=inverter_state,
    )


def parse_inverter_info(data: JsonObject) -> dict[str, InverterInfo]:
    """Parse the body of `GetInverterInfo.cgi`."""
    return {
        device_id: _parse_inverter_info(
            device_id, _object(device, f"Inverter info {device_id}")
        )
        for device_id, device in data.items()
    }


def _parse_device_status(data: JsonObject) -> DeviceStatus | None:
    # a GEN24 Primo was seen reporting the key with a trailing colon
    status = _first(data, "DeviceStatus", "DeviceStatus:")
    if status is None:
        return None
    status = _object(status, "DeviceStatus")
    return DeviceStatus(
        # API v0 named it DeviceState in early firmware
        status_code=_integer(status, "StatusCode")
        if "StatusCode" in status
        else _integer(status, "DeviceState"),
        error_code=_integer(status, "ErrorCode"),
        led_color=_integer(status, "LEDColor"),
        led_state=_integer(status, "LEDState"),
        mgmt_timer_remaining_time=_integer(status, "MgmtTimerRemainingTime"),
        state_to_reset=_boolean(status, "StateToReset"),
        inverter_state=_string(status, "InverterState"),
    )


def parse_common_inverter_data(data: JsonObject) -> CommonInverterData:
    """Parse the body of a `CommonInverterData` device request."""
    return CommonInverterData(
        power_ac=_value_of(data, "PAC"),
        power_apparent=_value_of(data, "SAC"),
        current_ac=_value_of(data, "IAC"),
        voltage_ac=_value_of(data, "UAC"),
        frequency_ac=_value_of(data, "FAC"),
        current_dc=_value_of(data, "IDC"),
        voltage_dc=_value_of(data, "UDC"),
        current_dc_2=_value_of(data, "IDC_2"),
        voltage_dc_2=_value_of(data, "UDC_2"),
        current_dc_3=_value_of(data, "IDC_3"),
        voltage_dc_3=_value_of(data, "UDC_3"),
        current_dc_4=_value_of(data, "IDC_4"),
        voltage_dc_4=_value_of(data, "UDC_4"),
        energy_day=_value_of(data, "DAY_ENERGY"),
        energy_year=_value_of(data, "YEAR_ENERGY"),
        energy_total=_value_of(data, "TOTAL_ENERGY"),
        device_status=_parse_device_status(data),
    )


def parse_3p_inverter_data(data: JsonObject) -> ThreePhaseInverterData:
    """Parse the body of a `3PInverterData` device request."""
    return ThreePhaseInverterData(
        current_ac_phase_1=_value_of(data, "IAC_L1"),
        current_ac_phase_2=_value_of(data, "IAC_L2"),
        current_ac_phase_3=_value_of(data, "IAC_L3"),
        voltage_ac_phase_1=_value_of(data, "UAC_L1"),
        voltage_ac_phase_2=_value_of(data, "UAC_L2"),
        voltage_ac_phase_3=_value_of(data, "UAC_L3"),
        temperature_ambient=_value_of(data, "T_AMBIENT"),
        fan_speed_front_left=_integer_value_of(data, "ROTATION_SPEED_FAN_FL"),
        fan_speed_front_right=_integer_value_of(data, "ROTATION_SPEED_FAN_FR"),
        fan_speed_back_left=_integer_value_of(data, "ROTATION_SPEED_FAN_BL"),
        fan_speed_back_right=_integer_value_of(data, "ROTATION_SPEED_FAN_BR"),
    )


def parse_cumulation_inverter_data(data: JsonObject) -> CumulationInverterData:
    """Parse the body of a `CumulationInverterData` device request."""
    return CumulationInverterData(
        power_ac=_value_of(data, "PAC"),
        energy_day=_value_of(data, "DAY_ENERGY"),
        energy_year=_value_of(data, "YEAR_ENERGY"),
        energy_total=_value_of(data, "TOTAL_ENERGY"),
        device_status=_parse_device_status(data),
    )


def parse_system_inverter_data(data: JsonObject) -> dict[str, CumulationInverterData]:
    """Parse the body of a `GetInverterRealtimeData.cgi?Scope=System` request.

    The response is organized by channel, each holding values per device id.
    GEN24 devices name that object `Value` instead of `Values`.
    """
    channels: dict[str, dict[str, float | None]] = {}
    device_ids: dict[str, None] = {}
    for channel, content in data.items():
        content = _object(content, channel)
        values = _first(content, "Values", "Value")
        if values is None:
            channels[channel] = {}
            continue
        channels[channel] = {
            device_id: _number(_object(values, channel), device_id)
            for device_id in _object(values, channel)
        }
        if any(value is not None for value in channels[channel].values()):
            _check_unit(channel, content)
        device_ids.update(dict.fromkeys(channels[channel]))
    return {
        device_id: CumulationInverterData(
            power_ac=channels.get("PAC", {}).get(device_id),
            energy_day=channels.get("DAY_ENERGY", {}).get(device_id),
            energy_year=channels.get("YEAR_ENERGY", {}).get(device_id),
            energy_total=channels.get("TOTAL_ENERGY", {}).get(device_id),
            device_status=None,
        )
        for device_id in device_ids
    }


def parse_logger_info(data: JsonObject) -> LoggerInfo:
    """Parse the body of `GetLoggerInfo.cgi`."""
    unique_id = _string(data, "UniqueID")
    if unique_id is None:
        raise _invalid(f"Logger info is incomplete: {data!r}")
    utc_offset = _integer(data, "UTCOffset")
    if utc_offset is not None and utc_offset >= 2**31:
        # negative offsets are reported as unsigned 32 bit integer
        utc_offset -= 2**32
    return LoggerInfo(
        unique_id=unique_id,
        product_id=_string(data, "ProductID"),
        platform_id=_string(data, "PlatformID"),
        hardware_version=_string(data, "HWVersion"),
        software_version=_string(data, "SWVersion"),
        timezone_location=_string(data, "TimezoneLocation"),
        timezone_name=_string(data, "TimezoneName"),
        utc_offset=utc_offset,
        default_language=_string(data, "DefaultLanguage"),
        delivery_factor=_number(data, "DeliveryFactor"),
        cash_factor=_number(data, "CashFactor"),
        cash_currency=_html_string(data, "CashCurrency"),
        co2_factor=_number(data, "CO2Factor"),
        co2_unit=_html_string(data, "CO2Unit"),
    )


def parse_logger_led_info(data: JsonObject) -> LoggerLedInfo:
    """Parse the body of `GetLoggerLEDInfo.cgi`."""
    leds = {}
    for name, led in data.items():
        led = _object(led, name)
        color = _string(led, "Color")
        state = _string(led, "State")
        if color is None or state is None:
            raise _invalid(f"LED {name} is incomplete: {led!r}")
        leds[name] = LedStatus(color=color, state=state)
    return LoggerLedInfo(leds=leds)


def _parse_active_device(data: JsonObject) -> ActiveDevice:
    device_type = _integer(data, "DT")
    channel_names = data.get("ChannelNames")
    if channel_names is not None and (
        not isinstance(channel_names, list)
        or not all(isinstance(name, str) for name in channel_names)
    ):
        raise _invalid(f"ChannelNames is not a list of strings: {channel_names!r}")
    return ActiveDevice(
        # -1 is reported for device classes that have no device type
        device_type=None if device_type == -1 else device_type,
        serial=_string(data, "Serial"),
        channel_names=None if channel_names is None else tuple(channel_names),
    )


_ACTIVE_DEVICE_CLASSES = {
    "Inverter": "inverters",
    "Meter": "meters",
    "Ohmpilot": "ohmpilots",
    "SensorCard": "sensor_cards",
    "Storage": "storages",
    "StringControl": "string_controls",
}


def parse_active_device_info(data: JsonObject) -> ActiveDeviceInfo:
    """Parse the body of `GetActiveDeviceInfo.cgi?DeviceClass=System`.

    GEN24 devices put their inverters at the top level, next to the device
    class objects, instead of inside an `Inverter` object.
    """
    classes: dict[str, dict[str, ActiveDevice]] = {
        attribute: {} for attribute in _ACTIVE_DEVICE_CLASSES.values()
    }
    for key, content in data.items():
        content = _object(content, key)
        if (attribute := _ACTIVE_DEVICE_CLASSES.get(key)) is not None:
            classes[attribute].update(_per_device(content, _parse_active_device, key))
        else:
            classes["inverters"][key] = _parse_active_device(content)
    return ActiveDeviceInfo(**classes)


def parse_active_devices(data: JsonObject) -> dict[str, ActiveDevice]:
    """Parse the body of `GetActiveDeviceInfo.cgi` for a single device class."""
    return _per_device(data, _parse_active_device, "Active device")


def parse_meter_data(data: JsonObject) -> MeterData:
    """Parse one meter of `GetMeterRealtimeData.cgi`.

    Some GEN24 firmware versions report a few channels under their internal
    names (`SMARTMETER_*`, `ACBRIDGE_*`), which are accepted as aliases.
    """

    def channel(*keys: str) -> float | None:
        for key in keys:
            if (value := _number(data, key)) is not None:
                return value
        return None

    return MeterData(
        details=parse_details(data),
        enabled=_boolean(data, "Enable"),
        visible=_boolean(data, "Visible"),
        meter_location_code=_integer(data, "Meter_Location_Current"),
        timestamp=_epoch(data, "TimeStamp"),
        current_ac_phase_1=channel(
            "Current_AC_Phase_1", "ACBRIDGE_CURRENT_ACTIVE_MEAN_01_F32"
        ),
        current_ac_phase_2=channel(
            "Current_AC_Phase_2", "ACBRIDGE_CURRENT_ACTIVE_MEAN_02_F32"
        ),
        current_ac_phase_3=channel(
            "Current_AC_Phase_3", "ACBRIDGE_CURRENT_ACTIVE_MEAN_03_F32"
        ),
        current_ac_sum=channel("Current_AC_Sum"),
        energy_reactive_consumed=channel("EnergyReactive_VArAC_Sum_Consumed"),
        energy_reactive_produced=channel("EnergyReactive_VArAC_Sum_Produced"),
        energy_reactive_phase_1_consumed=channel(
            "EnergyReactive_VArAC_Phase_1_Consumed"
        ),
        energy_reactive_phase_1_produced=channel(
            "EnergyReactive_VArAC_Phase_1_Produced"
        ),
        energy_real_minus_absolute=channel("EnergyReal_WAC_Minus_Absolute"),
        energy_real_plus_absolute=channel("EnergyReal_WAC_Plus_Absolute"),
        energy_real_minus_relative=channel("EnergyReal_WAC_Minus_Relative"),
        energy_real_plus_relative=channel("EnergyReal_WAC_Plus_Relative"),
        energy_real_consumed=channel(
            "EnergyReal_WAC_Sum_Consumed", "SMARTMETER_ENERGYACTIVE_CONSUMED_SUM_F64"
        ),
        energy_real_produced=channel(
            "EnergyReal_WAC_Sum_Produced", "SMARTMETER_ENERGYACTIVE_PRODUCED_SUM_F64"
        ),
        energy_real_phase_1_consumed=channel("EnergyReal_WAC_Phase_1_Consumed"),
        energy_real_phase_1_produced=channel("EnergyReal_WAC_Phase_1_Produced"),
        energy_real_phase_2_consumed=channel("EnergyReal_WAC_Phase_2_Consumed"),
        energy_real_phase_2_produced=channel("EnergyReal_WAC_Phase_2_Produced"),
        energy_real_phase_3_consumed=channel("EnergyReal_WAC_Phase_3_Consumed"),
        energy_real_phase_3_produced=channel("EnergyReal_WAC_Phase_3_Produced"),
        frequency_phase_average=channel("Frequency_Phase_Average"),
        power_apparent_phase_1=channel("PowerApparent_S_Phase_1"),
        power_apparent_phase_2=channel("PowerApparent_S_Phase_2"),
        power_apparent_phase_3=channel("PowerApparent_S_Phase_3"),
        power_apparent=channel("PowerApparent_S_Sum"),
        power_factor_phase_1=channel("PowerFactor_Phase_1"),
        power_factor_phase_2=channel("PowerFactor_Phase_2"),
        power_factor_phase_3=channel("PowerFactor_Phase_3"),
        power_factor=channel("PowerFactor_Sum"),
        power_reactive_phase_1=channel("PowerReactive_Q_Phase_1"),
        power_reactive_phase_2=channel("PowerReactive_Q_Phase_2"),
        power_reactive_phase_3=channel("PowerReactive_Q_Phase_3"),
        power_reactive=channel("PowerReactive_Q_Sum"),
        power_real_phase_1=channel(
            "PowerReal_P_Phase_1", "SMARTMETER_POWERACTIVE_01_F64"
        ),
        power_real_phase_2=channel(
            "PowerReal_P_Phase_2", "SMARTMETER_POWERACTIVE_02_F64"
        ),
        power_real_phase_3=channel(
            "PowerReal_P_Phase_3", "SMARTMETER_POWERACTIVE_03_F64"
        ),
        power_real=channel("PowerReal_P_Sum", "SMARTMETER_POWERACTIVE_MEAN_SUM_F64"),
        voltage_ac_phase_1=channel("Voltage_AC_Phase_1"),
        voltage_ac_phase_2=channel("Voltage_AC_Phase_2"),
        voltage_ac_phase_3=channel("Voltage_AC_Phase_3"),
        voltage_ac_phase_to_phase_12=channel("Voltage_AC_PhaseToPhase_12"),
        voltage_ac_phase_to_phase_23=channel("Voltage_AC_PhaseToPhase_23"),
        voltage_ac_phase_to_phase_31=channel("Voltage_AC_PhaseToPhase_31"),
        voltage_ac_phase_average=channel("Voltage_AC_Phase_Average"),
    )


def parse_system_meter_data(data: JsonObject) -> dict[str, MeterData]:
    """Parse the body of `GetMeterRealtimeData.cgi?Scope=System`."""
    return _per_device(data, parse_meter_data, "Meter")


def _parse_storage_controller(data: JsonObject) -> StorageController:
    return StorageController(
        details=parse_details(data),
        enabled=_boolean(data, "Enable"),
        timestamp=_epoch(data, "TimeStamp"),
        state_of_charge=_number(data, "StateOfCharge_Relative"),
        capacity_maximum=_number(data, "Capacity_Maximum"),
        designed_capacity=_number(data, "DesignedCapacity"),
        current_dc=_number(data, "Current_DC"),
        voltage_dc=_number(data, "Voltage_DC"),
        temperature_cell=_number(data, "Temperature_Cell"),
        voltage_dc_maximum_cell=_number(data, "Voltage_DC_Maximum_Cell"),
        voltage_dc_minimum_cell=_number(data, "Voltage_DC_Minimum_Cell"),
        status_battery_cell=_integer(data, "Status_BatteryCell"),
    )


def _parse_storage_module(data: JsonObject) -> StorageModule:
    return StorageModule(
        details=parse_details(data),
        enabled=_boolean(data, "Enable"),
        timestamp=_epoch(data, "TimeStamp"),
        state_of_charge=_number(data, "StateOfCharge_Relative"),
        capacity_maximum=_number(data, "Capacity_Maximum"),
        designed_capacity=_number(data, "DesignedCapacity"),
        current_dc=_number(data, "Current_DC"),
        voltage_dc=_number(data, "Voltage_DC"),
        temperature_cell=_number(data, "Temperature_Cell"),
        temperature_cell_maximum=_number(data, "Temperature_Cell_Maximum"),
        temperature_cell_minimum=_number(data, "Temperature_Cell_Minimum"),
        voltage_dc_maximum_cell=_number(data, "Voltage_DC_Maximum_Cell"),
        voltage_dc_minimum_cell=_number(data, "Voltage_DC_Minimum_Cell"),
        cycle_count_battery_cell=_integer(data, "CycleCount_BatteryCell"),
        status_battery_cell=_integer(data, "Status_BatteryCell"),
    )


def parse_storage_data(data: JsonObject) -> StorageData:
    """Parse one storage of `GetStorageRealtimeData.cgi`."""
    controller = data.get("Controller")
    modules = data.get("Modules", [])
    if not isinstance(modules, list):
        raise _invalid(f"Modules is not a list: {modules!r}")
    return StorageData(
        controller=None
        if controller is None
        else _parse_storage_controller(_object(controller, "Controller")),
        modules=tuple(
            _parse_storage_module(_object(module, "Module")) for module in modules
        ),
    )


def parse_system_storage_data(data: JsonObject) -> dict[str, StorageData]:
    """Parse the body of `GetStorageRealtimeData.cgi?Scope=System`."""
    return _per_device(data, parse_storage_data, "Storage")


def parse_ohmpilot_data(data: JsonObject) -> OhmpilotData:
    """Parse one Ohmpilot of `GetOhmPilotRealtimeData.cgi`."""
    return OhmpilotData(
        details=parse_details(data),
        energy_real_consumed=_number(data, "EnergyReal_WAC_Sum_Consumed"),
        power_real=_number(data, "PowerReal_PAC_Sum"),
        temperature_channel_1=_number(data, "Temperature_Channel_1"),
        state_code=_integer(data, "CodeOfState"),
        error_code=_integer(data, "CodeOfError"),
    )


def parse_system_ohmpilot_data(data: JsonObject) -> dict[str, OhmpilotData]:
    """Parse the body of `GetOhmPilotRealtimeData.cgi?Scope=System`."""
    return _per_device(data, parse_ohmpilot_data, "Ohmpilot")


def _parse_power_flow_site(data: JsonObject) -> PowerFlowSite:
    mode = _string(data, "Mode")
    if mode is None:
        raise _invalid(f"Power flow site has no mode: {data!r}")
    return PowerFlowSite(
        mode=mode,
        battery_standby=_boolean(data, "BatteryStandby"),
        backup_mode=_boolean(data, "BackupMode"),
        power_grid=_number(data, "P_Grid"),
        power_load=_number(data, "P_Load"),
        power_battery=_number(data, "P_Akku"),
        power_photovoltaics=_number(data, "P_PV"),
        relative_self_consumption=_number(data, "rel_SelfConsumption"),
        relative_autonomy=_number(data, "rel_Autonomy"),
        meter_location=_string(data, "Meter_Location"),
        energy_day=_number(data, "E_Day"),
        energy_year=_number(data, "E_Year"),
        energy_total=_number(data, "E_Total"),
    )


def _parse_power_flow_inverter(data: JsonObject) -> PowerFlowInverter:
    return PowerFlowInverter(
        device_type=_integer(data, "DT"),
        power=_number(data, "P"),
        state_of_charge=_number(data, "SOC"),
        component_id=_integer(data, "CID"),
        battery_mode=_string(data, "Battery_Mode"),
        energy_day=_number(data, "E_Day"),
        energy_year=_number(data, "E_Year"),
        energy_total=_number(data, "E_Total"),
    )


def _parse_power_flow_ohmpilot(data: JsonObject) -> PowerFlowOhmpilot:
    return PowerFlowOhmpilot(
        power_ac_total=_number(data, "P_AC_Total"),
        state=_string(data, "State"),
        temperature=_number(data, "Temperature"),
    )


def _parse_power_flow_ohmpilot_eco(data: JsonObject) -> PowerFlowOhmpilotEco:
    return PowerFlowOhmpilotEco(
        power_ac_total=_number(data, "P_AC_Total"),
        state_heating_rod_1=_string(data, "State_HR1"),
        state_heating_rod_2=_string(data, "State_HR2"),
        temperature_1=_number(data, "Temperature_1"),
        temperature_2=_number(data, "Temperature_2"),
    )


def _parse_power_flow_secondary_meter(data: JsonObject) -> PowerFlowSecondaryMeter:
    return PowerFlowSecondaryMeter(
        power=_number(data, "P"),
        meter_location_code=_integer(data, "MLoc"),
        label=_string(data, "Label"),
        category=_string(data, "Category"),
    )


def parse_power_flow(data: JsonObject) -> PowerFlow:
    """Parse the body of `GetPowerFlowRealtimeData.fcgi`.

    `Version` is an integer within a string. Everything but `Site` is optional
    and depends on the version and the device generation.
    """
    version = data.get("Version")
    if isinstance(version, str) and version.isdecimal():
        parsed_version: int | None = int(version)
    else:
        parsed_version = _integer(data, "Version")
    site = data.get("Site")
    if site is None:
        raise _invalid(f"Power flow has no Site: {data!r}")
    smartloads = _object(data.get("Smartloads", {}), "Smartloads")
    return PowerFlow(
        version=parsed_version,
        site=_parse_power_flow_site(_object(site, "Site")),
        inverters=_per_device(
            _object(data.get("Inverters", {}), "Inverters"),
            _parse_power_flow_inverter,
            "Inverter",
        ),
        ohmpilots=_per_device(
            _object(smartloads.get("Ohmpilots", {}), "Ohmpilots"),
            _parse_power_flow_ohmpilot,
            "Ohmpilot",
        ),
        ohmpilot_ecos=_per_device(
            _object(smartloads.get("OhmpilotEcos", {}), "OhmpilotEcos"),
            _parse_power_flow_ohmpilot_eco,
            "OhmpilotEco",
        ),
        secondary_meters=_per_device(
            _object(data.get("SecondaryMeters", {}), "SecondaryMeters"),
            _parse_power_flow_secondary_meter,
            "SecondaryMeter",
        ),
    )
