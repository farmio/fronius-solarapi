"""Constants and enumerations of the Fronius Solar API."""

from enum import IntEnum, StrEnum
from typing import Final


class ApiVersion(IntEnum):
    """Version of the Solar API served by a device."""

    V0 = 0
    V1 = 1


API_BASE_PATHS: Final[dict[ApiVersion, str]] = {
    ApiVersion.V0: "/solar_api/",
    ApiVersion.V1: "/solar_api/v1/",
}
API_VERSION_PATH: Final = "/solar_api/GetAPIVersion.cgi"


class StatusCode(IntEnum):
    """Status code of the common response header (spec table 1)."""

    OKAY = 0
    NOT_IMPLEMENTED = 1
    UNINITIALIZED = 2
    INITIALIZED = 3
    RUNNING = 4
    TIMEOUT = 5
    ARGUMENT_ERROR = 6
    LN_REQUEST_ERROR = 7
    LN_REQUEST_TIMEOUT = 8
    LN_PARSE_ERROR = 9
    CONFIG_IO_ERROR = 10
    NOT_SUPPORTED = 11
    DEVICE_NOT_AVAILABLE = 12
    UNKNOWN_ERROR = 255


STATUS_CODE_DESCRIPTIONS: Final[dict[int, str]] = {
    StatusCode.OKAY: "Request successfully finished, data are valid",
    StatusCode.NOT_IMPLEMENTED: "The request or a part of it is not implemented yet",
    StatusCode.UNINITIALIZED: "Instance of API request created, but not configured",
    StatusCode.INITIALIZED: "Request is configured and ready to be sent",
    StatusCode.RUNNING: "Request is currently being processed",
    StatusCode.TIMEOUT: "Response was not received within desired time",
    StatusCode.ARGUMENT_ERROR: "Invalid arguments or missing arguments",
    StatusCode.LN_REQUEST_ERROR: "Error during sending/receiving of LN message",
    StatusCode.LN_REQUEST_TIMEOUT: "LN request timed out",
    StatusCode.LN_PARSE_ERROR: "Error during parsing of received LN message",
    StatusCode.CONFIG_IO_ERROR: "Error while reading settings from local config",
    StatusCode.NOT_SUPPORTED: "The operation or feature is not supported",
    StatusCode.DEVICE_NOT_AVAILABLE: "The device is not available",
    StatusCode.UNKNOWN_ERROR: "Undefined runtime error",
}


class DeviceClass(StrEnum):
    """Device classes of the Solar API."""

    INVERTER = "Inverter"
    STORAGE = "Storage"
    OHMPILOT = "Ohmpilot"
    SENSOR_CARD = "SensorCard"
    STRING_CONTROL = "StringControl"
    METER = "Meter"
    SYSTEM = "System"


class InverterState(StrEnum):
    """Operational state of an inverter, derived from its numeric status code."""

    STARTUP = "startup"
    RUNNING = "running"
    STANDBY = "standby"
    BOOTLOADING = "bootloading"
    ERROR = "error"
    IDLE = "idle"
    READY = "ready"
    SLEEPING = "sleeping"
    UNKNOWN = "unknown"


def inverter_state(status_code: int | None) -> InverterState | None:
    """Return the operational state for a numeric inverter status code.

    Spec section 4.6.5. Codes outside the documented table return `None`.
    """
    match status_code:
        case None:
            return None
        case int() if 0 <= status_code <= 6:
            return InverterState.STARTUP
        case 7:
            return InverterState.RUNNING
        case 8:
            return InverterState.STANDBY
        case 9:
            return InverterState.BOOTLOADING
        case 10:
            return InverterState.ERROR
        case 11:
            return InverterState.IDLE
        case 12:
            return InverterState.READY
        case 13:
            return InverterState.SLEEPING
        case 255:
            return InverterState.UNKNOWN
    return None


class OhmpilotState(IntEnum):
    """Ohmpilot `CodeOfState` values (spec section 4.10.5)."""

    UP_AND_RUNNING = 0
    KEEP_MINIMUM_TEMPERATURE = 1
    LEGIONELLA_PROTECTION = 2
    CRITICAL_FAULT = 3
    FAULT = 4
    BOOST_MODE = 5


class MeterLocation(StrEnum):
    """Kind of location a meter is installed at, derived from the numeric code."""

    GRID = "grid"
    LOAD = "load"
    EXTERNAL_GENERATOR = "external_generator"
    EXTERNAL_GENERATOR_WITH_BATTERY = "external_generator_with_battery"
    SUBLOAD = "subload"


def meter_location(code: int | None) -> MeterLocation | None:
    """Return the kind of location for a `Meter_Location_Current` code.

    Spec sections 4.8.5 to 4.8.7: 0 is the grid interconnection point (primary
    meter in the feed-in path), 1 the consumption path (primary meter in the
    load path), 3 an additional generator, 4 an additional generator with a
    battery and 256 to 511 are sub loads.
    """
    match code:
        case 0:
            return MeterLocation.GRID
        case 1:
            return MeterLocation.LOAD
        case 3:
            return MeterLocation.EXTERNAL_GENERATOR
        case 4:
            return MeterLocation.EXTERNAL_GENERATOR_WITH_BATTERY
        case int() if 256 <= code <= 511:
            return MeterLocation.SUBLOAD
    return None


class PowerFlowMode(StrEnum):
    """Known values of the power flow `Site.Mode` field."""

    PRODUCE_ONLY = "produce-only"
    METER = "meter"
    VAGUE_METER = "vague-meter"
    BIDIRECTIONAL = "bidirectional"
    AC_COUPLED = "ac-coupled"


class PowerFlowMeterLocation(StrEnum):
    """Known values of the power flow `Site.Meter_Location` field."""

    LOAD = "load"
    GRID = "grid"
    UNKNOWN = "unknown"


class BatteryMode(StrEnum):
    """Known values of the power flow `Battery_Mode` field."""

    DISABLED = "disabled"
    NORMAL = "normal"
    SERVICE = "service"
    CHARGE_BOOST = "charge boost"
    NEARLY_DEPLETED = "nearly depleted"
    SUSPENDED = "suspended"
    CALIBRATE = "calibrate"
    GRID_SUPPORT = "grid support"
    DEPLETE_RECOVERY = "deplete recovery"
    NON_OPERABLE_VOLTAGE = "non operable (voltage)"
    NON_OPERABLE_TEMPERATURE = "non operable (temperature)"
    PREHEATING = "preheating"
    STARTUP = "startup"
    STOPPED_TEMPERATURE = "stopped (temperature)"
    BATTERY_FULL = "battery full"


class LedColor(StrEnum):
    """Known values of a logger LED color."""

    RED = "red"
    GREEN = "green"
    NONE = "none"


class LedState(StrEnum):
    """Known values of a logger LED state."""

    ON = "on"
    OFF = "off"
    BLINKING = "blinking"
    ALTERNATING = "alternating"
