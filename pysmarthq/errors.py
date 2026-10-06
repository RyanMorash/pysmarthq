"""Errors raised by the SmartHQ client."""

from __future__ import annotations

from typing import Any


class SmartHQError(Exception):
    """Base error for pysmarthq."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class SmartHQAuthError(SmartHQError):
    """The Identity and Access Management API rejected a token request.

    ``error`` and ``error_description`` are the fields defined on the
    ``/oauth2/token`` and ``/oauth2/auth`` error responses.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        error: str | None = None,
        error_description: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message, status=status, body=body)
        self.error = error
        self.error_description = error_description


class SmartHQApiError(SmartHQError):
    """A Digital Twin API call returned an error status."""


class SmartHQStreamClosed(SmartHQError):
    """The event-stream WebSocket closed.

    The real-time updates guide says SmartHQ closes the socket when the access
    token expires. Get a new token, call ``GET /v2/websocket`` again, reconnect,
    and send the event configuration messages again.
    """
