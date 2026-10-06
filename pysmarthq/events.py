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
from typing import Any

from aiohttp import WSMsgType

from .auth import AbstractAuth
from ._http import async_api
from .const import WEBSOCKET_IDLE_PING_SECONDS, WEBSOCKET_MAX_PAYLOAD_BYTES
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
    endpoint on each ``async_connect`` and does not reconnect on its own: when
    the access token expires, SmartHQ closes the socket.
    """

    def __init__(
        self,
        auth: AbstractAuth,
        *,
        idle_ping_seconds: float | None = WEBSOCKET_IDLE_PING_SECONDS,
    ) -> None:
        """Initialize the stream.

        ``idle_ping_seconds`` is the documented quiet period before a
        ``websocket#ping``. Pass ``None`` to disable that ping.
        """
        self.auth = auth
        self.idle_ping_seconds = idle_ping_seconds
        self.endpoint: WebsocketEndpoint | None = None
        self._ws: Any = None
        self._keepalive: asyncio.Task[None] | None = None
        self._last_activity = 0.0

    async def async_connect(self) -> WebsocketEndpoint:
        """Fetch ``GET /v2/websocket`` and connect to the returned URL.

        The connect acknowledgement is not consumed. Read it with
        ``async_receive``.
        """
        data = await async_api(self.auth, "GET", "v2/websocket")
        endpoint = WebsocketEndpoint(data, self.auth)
        if not endpoint.endpoint:
            raise SmartHQError("GET /v2/websocket did not include endpoint", body=data)
        self.endpoint = endpoint
        self._ws = await self.auth.websession.ws_connect(endpoint.endpoint)
        self._touch()
        if self.idle_ping_seconds:
            self._keepalive = asyncio.create_task(self._keepalive_loop())
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
        await self._send(payload)

    async def async_ping(self, id: str | None = None) -> None:
        """Send ``websocket#ping``. ``id`` is copied onto the pong when set."""
        payload: dict[str, Any] = {"kind": "websocket#ping", "action": "ping"}
        if id is not None:
            payload["id"] = id
        await self._send(payload)

    async def async_receive(self) -> Event:
        """Read the next event message.

        Protocol-level ping and pong frames are ignored. A closed socket raises
        ``SmartHQStreamClosed``.
        """
        ws = self._require_ws()
        while True:
            message = await ws.receive()
            kind = message.type
            if kind in (WSMsgType.PING, WSMsgType.PONG):
                continue
            if kind == WSMsgType.TEXT:
                self._touch()
                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError as err:
                    raise SmartHQError("Event message was not JSON") from err
                if not isinstance(payload, dict):
                    raise SmartHQError("Event message was not a JSON object")
                return parse_event(payload)
            if kind == WSMsgType.BINARY:
                raise SmartHQError("Unexpected binary WebSocket frame")
            if kind in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                raise SmartHQStreamClosed("WebSocket connection closed")
            if kind == WSMsgType.ERROR:
                raise SmartHQError("WebSocket connection failed")
            raise SmartHQError(f"Unsupported WebSocket frame type {kind}")

    def __aiter__(self) -> EventStream:
        return self

    async def __anext__(self) -> Event:
        try:
            return await self.async_receive()
        except SmartHQStreamClosed as err:
            raise StopAsyncIteration from err

    async def async_close(self) -> None:
        """Stop the idle ping and close the socket."""
        task = self._keepalive
        self._keepalive = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        ws = self._ws
        self._ws = None
        if ws is not None and not getattr(ws, "closed", False):
            await ws.close()

    async def __aenter__(self) -> EventStream:
        await self.async_connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.async_close()

    async def _send(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        if len(encoded) > WEBSOCKET_MAX_PAYLOAD_BYTES:
            raise SmartHQError("WebSocket payload exceeds 32 KB")
        await self._require_ws().send_str(encoded.decode())
        self._touch()

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
        except asyncio.CancelledError:
            raise

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    def _require_ws(self) -> Any:
        if self._ws is None:
            raise SmartHQError("Event stream is not connected")
        return self._ws


def _put_optional(payload: dict[str, Any], **flags: bool | None) -> None:
    for key, value in flags.items():
        if value is not None:
            payload[key] = value
