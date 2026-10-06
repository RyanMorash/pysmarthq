"""Event Stream client.

Messages follow the Event Stream AsyncAPI. The transport implemented here is
the WebSocket channel: ``GET /v2/websocket`` returns a URL that already carries
the access token, and JSON text frames carry event configuration messages and
event messages.

HTTPS/SNS delivery uses the Digital Twin pubsub routes on ``SmartHQApi`` and
``Device``. Registering the callback URL itself is done with SmartHQ, not by
an API operation in these specs.

The real-time updates guide describes a ``websocket#pubsub`` acknowledgement
(``kind`` and ``success``) that is not one of the AsyncAPI event schemas. That
payload is parsed as ``PubsubAckEvent`` when it arrives.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from typing import Any

from aiohttp import ClientWSTimeout, WSMsgType

from .auth import AbstractAuth
from ._http import async_api, redact_access_token
from .const import (
    REQUEST_TIMEOUT_SECONDS,
    WEBSOCKET_IDLE_PING_SECONDS,
    WEBSOCKET_INBOUND_GRACE_INTERVALS,
    WEBSOCKET_MAX_PAYLOAD_BYTES,
)
from .errors import SmartHQError, SmartHQStreamClosed
from .models import WebsocketEndpoint


class Event:
    """One JSON object received on the event stream."""

    def __init__(self, raw_data: dict[str, Any]) -> None:
        self.raw_data = raw_data

    @property
    def kind(self) -> str | None:
        """Message kind."""
        return self.raw_data.get("kind")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(kind={self.kind!r})"


class ConnectionEvent(Event):
    """``websocket#connect``."""

    @property
    def success(self) -> bool | None:
        """Whether the connection succeeded."""
        return self.raw_data.get("success")


class PongEvent(Event):
    """``websocket#pong``."""

    @property
    def id(self) -> str | None:
        """Id from the matching ping, when one was sent."""
        return self.raw_data.get("id")


class PubsubAckEvent(Event):
    """Acceptance payload documented for a WebSocket configuration message."""

    @property
    def success(self) -> bool | None:
        """Whether the configuration payload was accepted."""
        return self.raw_data.get("success")


class DeviceEvent(Event):
    """``pubsub#device``."""

    @property
    def userId(self) -> str | None:
        """User id. The guide says this is omitted on WebSocket connections."""
        return self.raw_data.get("userId")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self.raw_data.get("deviceId")

    @property
    def adapterId(self) -> str | None:
        """Adapter id."""
        return self.raw_data.get("adapterId")

    @property
    def gatewayId(self) -> str | None:
        """Gateway id."""
        return self.raw_data.get("gatewayId")

    @property
    def deviceType(self) -> str | None:
        """Device type."""
        return self.raw_data.get("deviceType")

    @property
    def lastSyncTime(self) -> str | None:
        """Last sync timestamp."""
        return self.raw_data.get("lastSyncTime")

    @property
    def event(self) -> str | None:
        """Device change, such as ``created``."""
        return self.raw_data.get("event")

    @property
    def services(self) -> list[Any] | None:
        """Service objects as returned. They are not rewritten."""
        return self.raw_data.get("services")


class PresenceEvent(Event):
    """``pubsub#presence``."""

    @property
    def userId(self) -> str | None:
        """User id."""
        return self.raw_data.get("userId")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self.raw_data.get("deviceId")

    @property
    def adapterId(self) -> str | None:
        """Adapter id."""
        return self.raw_data.get("adapterId")

    @property
    def deviceType(self) -> str | None:
        """Device type."""
        return self.raw_data.get("deviceType")

    @property
    def lastSyncTime(self) -> str | None:
        """Last sync timestamp."""
        return self.raw_data.get("lastSyncTime")

    @property
    def presence(self) -> str | None:
        """``ONLINE`` or ``OFFLINE``."""
        return self.raw_data.get("presence")


class ServiceEvent(Event):
    """``pubsub#service``."""

    @property
    def userId(self) -> str | None:
        """User id."""
        return self.raw_data.get("userId")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self.raw_data.get("deviceId")

    @property
    def adapterId(self) -> str | None:
        """Adapter id."""
        return self.raw_data.get("adapterId")

    @property
    def deviceType(self) -> str | None:
        """Device type."""
        return self.raw_data.get("deviceType")

    @property
    def serviceId(self) -> str | None:
        """Service id."""
        return self.raw_data.get("serviceId")

    @property
    def serviceType(self) -> str | None:
        """Service type."""
        return self.raw_data.get("serviceType")

    @property
    def domainType(self) -> str | None:
        """Domain type."""
        return self.raw_data.get("domainType")

    @property
    def serviceDeviceType(self) -> str | None:
        """Service device type."""
        return self.raw_data.get("serviceDeviceType")

    @property
    def lastSyncTime(self) -> str | None:
        """Last sync timestamp."""
        return self.raw_data.get("lastSyncTime")

    @property
    def lastStateTime(self) -> str | None:
        """Last state timestamp."""
        return self.raw_data.get("lastStateTime")

    @property
    def config(self) -> dict[str, Any] | None:
        """Config object, unchanged."""
        return self.raw_data.get("config")

    @property
    def state(self) -> dict[str, Any] | None:
        """State object, unchanged."""
        return self.raw_data.get("state")

    @property
    def statePrevious(self) -> dict[str, Any] | None:
        """Previous state when the payload includes it."""
        return self.raw_data.get("statePrevious")


class AlertEvent(Event):
    """``pubsub#alert``."""

    @property
    def userId(self) -> str | None:
        """User id."""
        return self.raw_data.get("userId")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self.raw_data.get("deviceId")

    @property
    def adapterId(self) -> str | None:
        """Adapter id."""
        return self.raw_data.get("adapterId")

    @property
    def deviceType(self) -> str | None:
        """Device type."""
        return self.raw_data.get("deviceType")

    @property
    def alertType(self) -> str | None:
        """Alert type."""
        return self.raw_data.get("alertType")

    @property
    def alertId(self) -> str | None:
        """Alert id when the payload includes it."""
        return self.raw_data.get("alertId")

    @property
    def lastAlertTime(self) -> str | None:
        """Last alert timestamp."""
        return self.raw_data.get("lastAlertTime")

    @property
    def services(self) -> list[Any] | None:
        """Alert services as returned."""
        return self.raw_data.get("services")


class CommandEvent(Event):
    """``pubsub#command``."""

    @property
    def userId(self) -> str | None:
        """User id."""
        return self.raw_data.get("userId")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self.raw_data.get("deviceId")

    @property
    def adapterId(self) -> str | None:
        """Adapter id."""
        return self.raw_data.get("adapterId")

    @property
    def deviceType(self) -> str | None:
        """Device type."""
        return self.raw_data.get("deviceType")

    @property
    def serviceId(self) -> str | None:
        """Service id."""
        return self.raw_data.get("serviceId")

    @property
    def serviceType(self) -> str | None:
        """Service type."""
        return self.raw_data.get("serviceType")

    @property
    def domainType(self) -> str | None:
        """Domain type."""
        return self.raw_data.get("domainType")

    @property
    def serviceDeviceType(self) -> str | None:
        """Service device type."""
        return self.raw_data.get("serviceDeviceType")

    @property
    def correlationId(self) -> str | None:
        """Correlation id."""
        return self.raw_data.get("correlationId")

    @property
    def command(self) -> dict[str, Any] | None:
        """Command object, unchanged."""
        return self.raw_data.get("command")

    @property
    def commandDateTime(self) -> str | None:
        """Command timestamp."""
        return self.raw_data.get("commandDateTime")

    @property
    def outcome(self) -> str | None:
        """Outcome string."""
        return self.raw_data.get("outcome")

    @property
    def outcomeDateTime(self) -> str | None:
        """Outcome timestamp."""
        return self.raw_data.get("outcomeDateTime")


_EVENT_TYPES: dict[str, type[Event]] = {
    "websocket#connect": ConnectionEvent,
    "websocket#pong": PongEvent,
    "websocket#pubsub": PubsubAckEvent,
    "pubsub#device": DeviceEvent,
    "pubsub#presence": PresenceEvent,
    "pubsub#service": ServiceEvent,
    "pubsub#alert": AlertEvent,
    "pubsub#command": CommandEvent,
}


def parse_event(payload: dict[str, Any]) -> Event:
    """Build the event object for a decoded WebSocket payload."""
    kind = payload.get("kind")
    return _EVENT_TYPES.get(kind, Event)(payload)


class EventStream:
    """WebSocket event stream for one SmartHQ user.

    The caller owns the aiohttp session on ``auth``. This client fetches a new
    endpoint on each ``async_connect`` and does not reconnect on its own.
    Home Assistant should schedule that from ``socket_expires_at``: the socket
    is tied to the access token in its URL and still closes at that expiry.
    ``async_connect`` closes any current socket and sends the last account and
    device configuration messages again.
    """

    def __init__(
        self,
        auth: AbstractAuth,
        *,
        idle_ping_seconds: float | None = WEBSOCKET_IDLE_PING_SECONDS,
    ) -> None:
        """Initialize the stream.

        ``idle_ping_seconds`` is the documented quiet period before a
        ``websocket#ping``. Pass ``None`` to disable that ping. With pinging
        enabled, the socket fails when no inbound frame arrives within about
        two ping intervals.
        """
        self.auth = auth
        self.idle_ping_seconds = idle_ping_seconds
        self.endpoint: WebsocketEndpoint | None = None
        self.socket_expires_at: float | None = None
        self._account_config: dict[str, Any] | None = None
        self._device_configs: dict[str, dict[str, Any]] = {}
        self._ws: Any = None
        self._keepalive: asyncio.Task[None] | None = None
        self._last_activity = 0.0
        self._last_inbound = 0.0
        self._closed_error: SmartHQStreamClosed | None = None

    async def async_connect(self) -> WebsocketEndpoint:
        """Fetch ``GET /v2/websocket`` and connect to the returned URL.

        Closes the current socket first. After the handshake, sends the last
        account configuration and the last configuration for each device again.
        The connect acknowledgement is not consumed. Read it with
        ``async_receive``. ``socket_expires_at`` is the token expiry baked into
        this URL.
        """
        await self.async_close()
        self.endpoint = None
        self.socket_expires_at = None
        data = await async_api(self.auth, "GET", "v2/websocket")
        endpoint = WebsocketEndpoint(data, self.auth)
        if not endpoint.endpoint:
            raise SmartHQError("GET /v2/websocket did not include endpoint", body=data)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                socket = await self.auth.websession.ws_connect(
                    endpoint.endpoint,
                    timeout=ClientWSTimeout(ws_close=float(REQUEST_TIMEOUT_SECONDS)),
                )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            raise SmartHQError(redact_access_token(str(err))) from None
        self._ws = socket
        self.endpoint = endpoint
        self.socket_expires_at = _token_expires_at(self.auth)
        self._closed_error = None
        self._note_inbound()
        if self.idle_ping_seconds:
            self._keepalive = asyncio.create_task(self._keepalive_loop())
        await self._replay_configuration()
        return endpoint

    async def async_configure_account(
        self,
        *,
        pubsub: bool,
        services: bool | None = None,
        presence: bool | None = None,
        alerts: bool | None = None,
        commands: bool | None = None,
    ) -> None:
        """Send an account-level WebSocket configuration message.

        ``kind`` is ``websocket#pubsub`` and ``action`` is ``pubsub``. Optional
        flags that are left as ``None`` are omitted.
        """
        payload: dict[str, Any] = {
            "kind": "websocket#pubsub",
            "action": "pubsub",
            "pubsub": pubsub,
        }
        _put_optional(payload, services=services, presence=presence, alerts=alerts, commands=commands)
        self._account_config = dict(payload)
        await self._send(payload)

    async def async_configure_device(
        self,
        device_id: str,
        *,
        services: bool | None = None,
        presence: bool | None = None,
        alerts: bool | None = None,
        commands: bool | None = None,
    ) -> None:
        """Send a device-level WebSocket configuration message.

        Account pubsub must already be enabled. This payload has no ``pubsub``
        field; that field belongs to the account configuration and to the
        Digital Twin device pubsub body.
        """
        payload: dict[str, Any] = {
            "kind": "websocket#pubsub",
            "action": "pubsub",
            "deviceId": device_id,
        }
        _put_optional(payload, services=services, presence=presence, alerts=alerts, commands=commands)
        self._device_configs[device_id] = dict(payload)
        await self._send(payload)

    async def async_ping(self, id: str | None = None) -> None:
        """Send ``websocket#ping``. ``id`` is copied onto the pong when set."""
        payload: dict[str, Any] = {"kind": "websocket#ping", "action": "ping"}
        if id is not None:
            payload["id"] = id
        await self._send(payload)

    async def async_receive(self) -> Event:
        """Read the next event message.

        Protocol-level ping frames are ignored. A pong or an event counts as
        inbound traffic. A closed socket raises ``SmartHQStreamClosed`` with
        the close code and reason when the peer sent them.
        """
        if self._closed_error is not None:
            raise self._closed_error
        ws = self._require_ws()
        while True:
            message = await ws.receive()
            if self._closed_error is not None:
                raise self._closed_error
            kind = message.type
            if kind == WSMsgType.PONG:
                self._note_inbound()
                continue
            if kind == WSMsgType.PING:
                continue
            if kind == WSMsgType.TEXT:
                self._note_inbound()
                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError as err:
                    raise SmartHQError("Event message was not JSON") from err
                if not isinstance(payload, dict):
                    raise SmartHQError("Event message was not a JSON object")
                return parse_event(payload)
            if kind == WSMsgType.BINARY:
                raise SmartHQError("Unexpected binary WebSocket frame")
            if kind in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR):
                raise _stream_closed(message)
            raise SmartHQError(f"Unsupported WebSocket frame type {kind}")

    def __aiter__(self) -> EventStream:
        return self

    async def __anext__(self) -> Event:
        return await self.async_receive()

    async def async_close(self) -> None:
        """Stop the idle ping and close the socket.

        The socket is closed even when the ping task has already failed.
        Stored event configuration is kept for the next ``async_connect``.
        """
        task = self._keepalive
        self._keepalive = None
        try:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            await self._close_socket()

    async def __aenter__(self) -> EventStream:
        await self.async_connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.async_close()

    async def _replay_configuration(self) -> None:
        if self._account_config is not None:
            await self._send(dict(self._account_config))
        for payload in self._device_configs.values():
            await self._send(dict(payload))

    async def _send(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        if len(encoded) > WEBSOCKET_MAX_PAYLOAD_BYTES:
            raise SmartHQError("WebSocket payload exceeds 32 KB")
        await self._require_ws().send_str(encoded.decode())
        self._note_outbound()

    async def _keepalive_loop(self) -> None:
        interval = self.idle_ping_seconds
        if not interval:
            return
        try:
            while True:
                await asyncio.sleep(interval)
                if self._ws is None:
                    return
                if time.monotonic() - self._last_activity >= interval:
                    await self.async_ping()
                if self._ws is None:
                    return
                if time.monotonic() - self._last_inbound >= interval * WEBSOCKET_INBOUND_GRACE_INTERVALS:
                    self._closed_error = SmartHQStreamClosed(
                        "No inbound WebSocket frame within the grace period"
                    )
                    await self._close_socket()
                    return
        except asyncio.CancelledError:
            raise

    async def _close_socket(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None and not getattr(ws, "closed", False):
            await ws.close()

    def _note_outbound(self) -> None:
        self._last_activity = time.monotonic()

    def _note_inbound(self) -> None:
        now = time.monotonic()
        self._last_inbound = now
        self._last_activity = now

    def _require_ws(self) -> Any:
        if self._ws is None:
            raise SmartHQError("Event stream is not connected")
        return self._ws


def _token_expires_at(auth: AbstractAuth) -> float | None:
    token = getattr(auth, "token", None)
    if not isinstance(token, Mapping):
        return None
    expires_at = token.get("expires_at")
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
        return None
    return float(expires_at)


def _stream_closed(message: Any) -> SmartHQStreamClosed:
    data = getattr(message, "data", None)
    extra = getattr(message, "extra", None)
    if getattr(message, "type", None) == WSMsgType.ERROR:
        detail = data if data else extra
        text = "WebSocket connection failed" if not detail else f"WebSocket connection failed: {detail}"
        return SmartHQStreamClosed(text)
    code = data if isinstance(data, int) and not isinstance(data, bool) else None
    reason = extra if isinstance(extra, str) and extra else None
    if code is None and reason is None:
        return SmartHQStreamClosed("WebSocket connection closed")
    parts = ["WebSocket connection closed"]
    if code is not None:
        parts.append(f"code {code}")
    if reason:
        parts.append(reason)
    return SmartHQStreamClosed(" ".join(parts), code=code, reason=reason)


def _put_optional(payload: dict[str, Any], **flags: bool | None) -> None:
    for key, value in flags.items():
        if value is not None:
            payload[key] = value
