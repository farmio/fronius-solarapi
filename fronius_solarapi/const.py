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


class PowerFlowOhmpilotState(StrEnum):
    """Known values of the `State` of an Ohmpilot in the power flow."""

    NORMAL = "normal"
    MIN_TEMPERATURE = "min-temperature"
    LEGIONELLA_PROTECTION = "legionella-protection"
    FAULT = "fault"
    WARNING = "warning"
    BOOST = "boost"


class PowerFlowOhmpilotEcoState(StrEnum):
    """Known values of the heating rod states of an Ohmpilot Eco in the power flow."""

    NORMAL = "normal"
    MIN_TEMPERATURE = "min-temperature"
    LEGIONELLA_PROTECTION = "legionella-protection"
    FAULT = "fault"
    WARNING = "warning"
    BOOST = "boost"
    TARGET_TEMPERATURE = "target-temperature"
    MAX_TEMPERATURE = "max-temperature"
    TIMESCHEDULE = "timeschedule"


class MeterCategory(StrEnum):
    """Known `Category` tokens of secondary meters in the power flow."""

    PV_INVERTER = "METER_CAT_WR"
    AC_STORAGE = "METER_CAT_BAT"
    PV_INVERTER_WITH_STORAGE = "METER_CAT_PV_BAT"
    WIND_TURBINE = "METER_CAT_WINDMILL"
    COMBINED_HEAT_AND_POWER = "METER_CAT_BHKW"
    ELECTRIC_VEHICLE = "METER_CAT_ECAR"
    HEAT_PUMP = "METER_CAT_HEATPUMP"
    OTHER_HEATING = "METER_CAT_OTHERHEATING"
    PUMP = "METER_CAT_PUMP"
    WHITE_GOODS = "METER_CAT_WHITEGOODS"
    CLIMATE = "METER_CAT_CLIMATE"
    BUILDING_SERVICES = "METER_CAT_BUILDING"
    OTHER = "METER_CAT_OTHER"


class SolarBatteryCellState(IntEnum):
    """State of a Fronius Solar Battery module (spec table 2).

    The values 0, 8 and 15 are reserved.
    """

    PRE_CHARGE = 0x1
    INITIAL = 0x2
    NORMAL_CHARGE = 0x3
    CHARGE_TERMINATE = 0x4
    NORMAL_DISCHARGE = 0x5
    OVER_VOLTAGE = 0x6
    OVER_DISCHARGE = 0x7
    OVER_TEMPERATURE_CHARGE = 0x9
    OVER_CURRENT_CHARGE = 0xA
    OVER_TEMPERATURE_DISCHARGE = 0xB
    OVER_CURRENT_DISCHARGE = 0xC
    CELL_UNBALANCE = 0xD
    CHARGE_SUSPEND = 0xE


class LgChemBatteryState(IntEnum):
    """Controller state of an LG Chem RESU H battery (spec table 2)."""

    STANDBY = 1
    ENABLED = 3
    FAULTED = 5
    SLEEP = 10


class BydBatteryState(IntEnum):
    """Controller state of a BYD Battery-Box (spec table 2)."""

    STANDBY = 0
    INACTIVE = 1
    DARKSTART = 2
    ACTIVE = 3
    FAULT = 4
    UPDATING = 5


def solar_battery_cell_states(
    status: int | None,
) -> tuple[SolarBatteryCellState | None, SolarBatteryCellState | None]:
    """Return the current and previous state of a Fronius Solar Battery module.

    `Status_BatteryCell` of a module is one byte `0xYX`, the high nibble `Y`
    is the current and the low nibble `X` the previous state. Reserved or
    out-of-range values are `None`.
    """
    if status is None or not 0 <= status <= 0xFF:
        return None, None
    return _cell_state(status >> 4), _cell_state(status & 0xF)


def _cell_state(nibble: int) -> SolarBatteryCellState | None:
    try:
        return SolarBatteryCellState(nibble)
    except ValueError:
        return None


_CONTROLLER_STATES: dict[str, type[LgChemBatteryState] | type[BydBatteryState]] = {
    "lg-chem": LgChemBatteryState,
    "byd": BydBatteryState,
}


def battery_controller_state(
    manufacturer: str | None, status: int | None
) -> LgChemBatteryState | BydBatteryState | None:
    """Return the state of a storage controller from its `Status_BatteryCell`.

    The meaning of the code depends on the battery manufacturer; the spec
    documents LG Chem RESU H and BYD Battery-Box. Other manufacturers, and
    codes outside the documented tables, are `None`.
    """
    if manufacturer is None or status is None:
        return None
    if (enum := _CONTROLLER_STATES.get(manufacturer.strip().casefold())) is None:
        return None
    try:
        return enum(status)
    except ValueError:
        return None
