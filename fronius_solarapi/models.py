"""Typed representations of Solar API responses.

Measurement fields carry the base unit of the API: W, VA, VAr, Wh, VArh, V, A,
Hz, °C and percent. `None` means the device did not report the value - either
because the channel does not exist on it or because it is not available right
now (e.g. energies on GEN24 devices, which always report `null` for day and
year energy).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    ApiVersion,
    InverterState,
    MeterLocation,
    OhmpilotState,
    StatusCode,
    inverter_state,
    meter_location,
)
from .device_types import InverterModel, inverter_model


@dataclass(frozen=True, slots=True)
class ApiVersionInfo:
    """Answer of `GetAPIVersion.cgi`."""

    api_version: ApiVersion
    base_url: str
    compatibility_range: str | None
    """`MAJOR.MINOR-BUILD` of the implementation, `None` on older firmware."""


@dataclass(frozen=True, slots=True)
class ResponseStatus:
    """The `Status` object of the common response header."""

    code: int
    reason: str
    user_message: str

    @property
    def status_code(self) -> StatusCode | None:
        """Return the code as enum member, if it is a documented one."""
        try:
            return StatusCode(self.code)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class ResponseHead:
    """The common response header every Solar API response carries."""

    timestamp: datetime
    """When the request was answered, in local time of the data logger."""
    status: ResponseStatus
    request_arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Response[T]:
    """A parsed response: the common header and the typed body."""

    head: ResponseHead
    data: T


@dataclass(frozen=True, slots=True)
class DeviceDetails:
    """The `Details` object of meters, storages and Ohmpilots."""

    manufacturer: str | None
    model: str | None
    serial: str | None
    hardware: str | None = None
    software: str | None = None


@dataclass(frozen=True, slots=True)
class InverterInfo:
    """One inverter of `GetInverterInfo.cgi`."""

    device_id: str
    """Solar Net address of the inverter, the key of the response object."""
    device_type: int
    unique_id: str
    pv_power: int | None
    """Connected PV power in W as configured, 0 if none configured on GEN24."""
    custom_name: str | None
    """User-assigned name. Not available on API v0."""
    show: bool | None
    """Whether the device shall be displayed in visualizations."""
    error_code: int | None
    """Currently present error code. `None` when the device has no valid one."""
    status_code: int | None
    """Numeric operational state, see `state`."""
    inverter_state: str | None
    """Textual operational state, only provided by GEN24/Tauro/Verto."""

    @property
    def model(self) -> InverterModel | None:
        """Return manufacturer and model for the device type, if known."""
        return inverter_model(self.device_type)

    @property
    def state(self) -> InverterState | None:
        """Return the operational state derived from the status code."""
        return inverter_state(self.status_code)


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """The `DeviceStatus` object of inverter realtime data."""

    status_code: int | None
    error_code: int | None
    led_color: int | None
    led_state: int | None
    mgmt_timer_remaining_time: int | None
    state_to_reset: bool | None
    inverter_state: str | None
    """Textual operational state, only provided by GEN24/Tauro/Verto."""

    @property
    def state(self) -> InverterState | None:
        """Return the operational state derived from the status code."""
        return inverter_state(self.status_code)


@dataclass(frozen=True, slots=True)
class CommonInverterData:
    """`GetInverterRealtimeData.cgi` with `DataCollection=CommonInverterData`."""

    power_ac: float | None
    """AC power in W, negative when consuming."""
    power_apparent: float | None
    """AC apparent power in VA, GEN24/Tauro/Verto only."""
    current_ac: float | None
    voltage_ac: float | None
    frequency_ac: float | None
    current_dc: float | None
    voltage_dc: float | None
    current_dc_2: float | None
    """DC current of MPP tracker 2, GEN24/Tauro/Verto only."""
    voltage_dc_2: float | None
    current_dc_3: float | None
    voltage_dc_3: float | None
    current_dc_4: float | None
    voltage_dc_4: float | None
    energy_day: float | None
    """AC energy of the current day in Wh, always `None` on GEN24/Tauro/Verto."""
    energy_year: float | None
    """AC energy of the current year in Wh, always `None` on GEN24/Tauro/Verto."""
    energy_total: float | None
    """AC energy ever since in Wh."""
    device_status: DeviceStatus | None


@dataclass(frozen=True, slots=True)
class ThreePhaseInverterData:
    """`GetInverterRealtimeData.cgi` with `DataCollection=3PInverterData`."""

    current_ac_phase_1: float | None
    current_ac_phase_2: float | None
    current_ac_phase_3: float | None
    voltage_ac_phase_1: float | None
    voltage_ac_phase_2: float | None
    voltage_ac_phase_3: float | None
    temperature_ambient: float | None
    """Ambient temperature, only provided by CL, XL and IG 500/400."""
    fan_speed_front_left: int | None
    fan_speed_front_right: int | None
    fan_speed_back_left: int | None
    fan_speed_back_right: int | None


@dataclass(frozen=True, slots=True)
class CumulationInverterData:
    """Cumulation values of one inverter.

    `GetInverterRealtimeData.cgi` with `DataCollection=CumulationInverterData`,
    and the per-device values of a `Scope=System` request, where
    `device_status` is not provided.
    """

    power_ac: float | None
    energy_day: float | None
    energy_year: float | None
    energy_total: float | None
    device_status: DeviceStatus | None


@dataclass(frozen=True, slots=True)
class LoggerInfo:
    """`GetLoggerInfo.cgi`."""

    unique_id: str
    product_id: str | None
    """E.g. "fronius-datamanager-card", not available on API v0."""
    platform_id: str | None
    """Hardware platform, e.g. "wilma", not available on API v0."""
    hardware_version: str | None
    software_version: str | None
    timezone_location: str | None
    timezone_name: str | None
    utc_offset: int | None
    """Seconds east of UTC including daylight saving."""
    default_language: str | None
    delivery_factor: float | None
    """Grid supply tariff per kWh in `cash_currency`."""
    cash_factor: float | None
    """Cash factor per kWh in `cash_currency`."""
    cash_currency: str | None
    co2_factor: float | None
    """CO2 factor per kWh in `co2_unit`."""
    co2_unit: str | None


@dataclass(frozen=True, slots=True)
class LedStatus:
    """Color and state of one logger LED."""

    color: str
    state: str


@dataclass(frozen=True, slots=True)
class LoggerLedInfo:
    """`GetLoggerLEDInfo.cgi`."""

    leds: Mapping[str, LedStatus]
    """All reported LEDs by their API name, e.g. "PowerLED"."""

    @property
    def power_led(self) -> LedStatus | None:
        """Return the power LED."""
        return self.leds.get("PowerLED")

    @property
    def solar_net_led(self) -> LedStatus | None:
        """Return the Solar Net LED."""
        return self.leds.get("SolarNetLED")

    @property
    def solar_web_led(self) -> LedStatus | None:
        """Return the Solar.web LED."""
        return self.leds.get("SolarWebLED")

    @property
    def wlan_led(self) -> LedStatus | None:
        """Return the WLAN LED."""
        return self.leds.get("WLANLED")


@dataclass(frozen=True, slots=True)
class ActiveDevice:
    """One device of `GetActiveDeviceInfo.cgi`."""

    device_type: int | None
    """Only valid for inverters, sensor cards and string controls."""
    serial: str | None
    channel_names: tuple[str, ...] | None
    """Only provided for sensor cards."""


@dataclass(frozen=True, slots=True)
class ActiveDeviceInfo:
    """`GetActiveDeviceInfo.cgi` for every device class, keyed by device id."""

    inverters: Mapping[str, ActiveDevice]
    meters: Mapping[str, ActiveDevice]
    ohmpilots: Mapping[str, ActiveDevice]
    sensor_cards: Mapping[str, ActiveDevice]
    storages: Mapping[str, ActiveDevice]
    string_controls: Mapping[str, ActiveDevice]


@dataclass(frozen=True, slots=True)
class MeterData:
    """One meter of `GetMeterRealtimeData.cgi`.

    Signs of power and energy depend on the meter location, see spec
    sections 4.8.6 and 4.8.7.
    """

    details: DeviceDetails | None
    enabled: bool | None
    visible: bool | None
    """Whether the values are usable. `False` for incomplete or outdated values."""
    meter_location_code: int | None
    """Raw `Meter_Location_Current`, see `meter_location`."""
    timestamp: datetime | None
    """When the meter last refreshed its values, in UTC."""
    current_ac_phase_1: float | None
    current_ac_phase_2: float | None
    current_ac_phase_3: float | None
    current_ac_sum: float | None
    energy_reactive_consumed: float | None
    energy_reactive_produced: float | None
    energy_reactive_phase_1_consumed: float | None
    energy_reactive_phase_1_produced: float | None
    energy_real_minus_absolute: float | None
    """Absolute counter in the system specific view, see spec section 4.8.6."""
    energy_real_plus_absolute: float | None
    energy_real_minus_relative: float | None
    """Relative counter of S0 meters."""
    energy_real_plus_relative: float | None
    energy_real_consumed: float | None
    """`EnergyReal_WAC_Sum_Consumed`, the meter specific view."""
    energy_real_produced: float | None
    energy_real_phase_1_consumed: float | None
    energy_real_phase_1_produced: float | None
    energy_real_phase_2_consumed: float | None
    energy_real_phase_2_produced: float | None
    energy_real_phase_3_consumed: float | None
    energy_real_phase_3_produced: float | None
    frequency_phase_average: float | None
    power_apparent_phase_1: float | None
    power_apparent_phase_2: float | None
    power_apparent_phase_3: float | None
    power_apparent: float | None
    power_factor_phase_1: float | None
    power_factor_phase_2: float | None
    power_factor_phase_3: float | None
    power_factor: float | None
    power_reactive_phase_1: float | None
    power_reactive_phase_2: float | None
    power_reactive_phase_3: float | None
    power_reactive: float | None
    power_real_phase_1: float | None
    power_real_phase_2: float | None
    power_real_phase_3: float | None
    power_real: float | None
    voltage_ac_phase_1: float | None
    voltage_ac_phase_2: float | None
    voltage_ac_phase_3: float | None
    voltage_ac_phase_to_phase_12: float | None
    voltage_ac_phase_to_phase_23: float | None
    voltage_ac_phase_to_phase_31: float | None
    voltage_ac_phase_average: float | None

    @property
    def meter_location(self) -> MeterLocation | None:
        """Return the kind of location the meter is installed at."""
        return meter_location(self.meter_location_code)


@dataclass(frozen=True, slots=True)
class StorageController:
    """The `Controller` section of a storage."""

    details: DeviceDetails | None
    enabled: bool | None
    """Whether the device is managed (`True`) or disconnected (`False`)."""
    timestamp: datetime | None
    state_of_charge: float | None
    """Relative charged capacity in percent."""
    capacity_maximum: float | None
    """Current maximum capacity in Wh."""
    designed_capacity: float | None
    """Designed capacity in Wh."""
    current_dc: float | None
    """Battery output current in A, positive when charging."""
    voltage_dc: float | None
    temperature_cell: float | None
    voltage_dc_maximum_cell: float | None
    voltage_dc_minimum_cell: float | None
    status_battery_cell: int | None
    """Manufacturer specific status, see spec table 2."""


@dataclass(frozen=True, slots=True)
class StorageModule:
    """One entry of the `Modules` section of a storage (Fronius Solar Battery)."""

    details: DeviceDetails | None
    enabled: bool | None
    timestamp: datetime | None
    state_of_charge: float | None
    capacity_maximum: float | None
    designed_capacity: float | None
    current_dc: float | None
    voltage_dc: float | None
    temperature_cell: float | None
    temperature_cell_maximum: float | None
    temperature_cell_minimum: float | None
    voltage_dc_maximum_cell: float | None
    voltage_dc_minimum_cell: float | None
    cycle_count_battery_cell: int | None
    status_battery_cell: int | None
    """Current and previous cell state, one byte `0xYX`, see spec table 2."""


@dataclass(frozen=True, slots=True)
class StorageData:
    """One storage of `GetStorageRealtimeData.cgi`."""

    controller: StorageController | None
    modules: tuple[StorageModule, ...]


@dataclass(frozen=True, slots=True)
class OhmpilotData:
    """One Ohmpilot of `GetOhmPilotRealtimeData.cgi`."""

    details: DeviceDetails | None
    energy_real_consumed: float | None
    """Total consumed energy in Wh."""
    power_real: float | None
    """Actual power consumption in W."""
    temperature_channel_1: float | None
    state_code: int | None
    """Raw `CodeOfState`, see `state`."""
    error_code: int | None
    """Refer to the Ohmpilot manual."""

    @property
    def state(self) -> OhmpilotState | None:
        """Return the operating state, if it is a documented one."""
        if self.state_code is None:
            return None
        try:
            return OhmpilotState(self.state_code)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class PowerFlowSite:
    """The `Site` object of `GetPowerFlowRealtimeData.fcgi`."""

    mode: str
    """See `PowerFlowMode`."""
    battery_standby: bool | None
    backup_mode: bool | None
    power_grid: float | None
    """W, positive from grid, negative to grid. `None` without a meter."""
    power_load: float | None
    """W, positive generator, negative consumer. `None` without a meter."""
    power_battery: float | None
    """W, negative charging, positive discharging. `None` without a battery."""
    power_photovoltaics: float | None
    """W, DC side on GEN24 and Symo Hybrid, AC side on SnapINverters."""
    relative_self_consumption: float | None
    relative_autonomy: float | None
    meter_location: str | None
    """See `PowerFlowMeterLocation`."""
    energy_day: float | None
    energy_year: float | None
    energy_total: float | None


@dataclass(frozen=True, slots=True)
class PowerFlowInverter:
    """One entry of the `Inverters` object of the power flow."""

    device_type: int | None
    """Invalid on GEN24/Tauro/Verto, which always report 1."""
    power: float | None
    """AC power in W, `None` when not running."""
    state_of_charge: float | None
    """Percent. GEN24 without battery falsely reports 0.0 until firmware 1.17."""
    component_id: int | None
    battery_mode: str | None
    """See `BatteryMode`. GEN24 without battery reports "disabled" until 1.17."""
    energy_day: float | None
    energy_year: float | None
    energy_total: float | None

    @property
    def model(self) -> InverterModel | None:
        """Return manufacturer and model for the device type, if known."""
        return inverter_model(self.device_type)


@dataclass(frozen=True, slots=True)
class PowerFlowOhmpilot:
    """One entry of `Smartloads.Ohmpilots` of the power flow."""

    power_ac_total: float | None
    state: str | None
    temperature: float | None


@dataclass(frozen=True, slots=True)
class PowerFlowOhmpilotEco:
    """One entry of `Smartloads.OhmpilotEcos` of the power flow."""

    power_ac_total: float | None
    state_heating_rod_1: str | None
    state_heating_rod_2: str | None
    temperature_1: float | None
    temperature_2: float | None


@dataclass(frozen=True, slots=True)
class PowerFlowSecondaryMeter:
    """One entry of `SecondaryMeters` of the power flow."""

    power: float | None
    """W, consumption negative for sub loads, production positive for generators."""
    meter_location_code: int | None
    label: str | None
    """User defined name, "<primary>" for primary meters."""
    category: str | None
    """Category token, e.g. "METER_CAT_HEATPUMP"."""

    @property
    def meter_location(self) -> MeterLocation | None:
        """Return the kind of location the meter is installed at."""
        return meter_location(self.meter_location_code)


@dataclass(frozen=True, slots=True)
class PowerFlow:
    """`GetPowerFlowRealtimeData.fcgi`."""

    version: int | None
    """Version of the power flow data container, see spec section 4.11.2."""
    site: PowerFlowSite
    inverters: Mapping[str, PowerFlowInverter]
    ohmpilots: Mapping[str, PowerFlowOhmpilot]
    ohmpilot_ecos: Mapping[str, PowerFlowOhmpilotEco]
    secondary_meters: Mapping[str, PowerFlowSecondaryMeter]
