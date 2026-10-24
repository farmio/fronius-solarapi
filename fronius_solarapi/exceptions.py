"""Exceptions raised by fronius-solarapi."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import STATUS_CODE_DESCRIPTIONS, StatusCode

if TYPE_CHECKING:
    from .models import ResponseHead


class FroniusError(Exception):
    """Base class of every error raised by this library."""


class FroniusConnectionError(FroniusError):
    """The device could not be reached, or did not answer in time."""


class InvalidResponseError(FroniusError):
    """The device answered with something that is not a valid Solar API response."""


class EndpointNotFoundError(InvalidResponseError):
    """The device answered with HTTP 404.

    Raised for endpoints a device does not serve at all. GEN24 devices also
    answer every request this way while the Solar API is disabled in their
    web interface.
    """


class NotSupportedError(FroniusError):
    """The request is not supported by the API version the device serves."""


class StatusError(FroniusError):
    """The device answered with a non-zero status code in the response header."""

    def __init__(self, endpoint: str, head: ResponseHead) -> None:
        """Initialize with the endpoint and the parsed response header."""
        self.endpoint = endpoint
        self.head = head
        self.code = head.status.code
        self.reason = head.status.reason
        self.user_message = head.status.user_message
        description = STATUS_CODE_DESCRIPTIONS.get(self.code, "Unknown status code")
        message = f"{endpoint} answered with status {self.code} ({description})"
        if self.reason:
            message = f"{message}: {self.reason}"
        super().__init__(message)

    @property
    def status_code(self) -> StatusCode | None:
        """Return the status code as enum member, if it is a documented one."""
        try:
            return StatusCode(self.code)
        except ValueError:
            return None


class RequestNotSupportedError(StatusError, NotSupportedError):
    """The device reported that it does not support the request.

    Status code 11 (NotSupported), or code 255 with a "not supported" reason,
    as older firmware reports e.g. storage requests on devices without one.
    """
