"""Event stream tests."""

from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp import WSMsgType

from pysmarthq import EventStream, SmartHQAuth, SmartHQAuthError, SmartHQError, SmartHQStreamClosed
from pysmarthq.events import AlertEvent, ConnectionEvent, PresenceEvent, PubsubAckEvent, ServiceEvent

from tests.mock_http import MockSession, Response


class FakeSocket:
    def __init__(
        self,
        incoming: list[dict],
        *,
        close_code: int | None = None,
        close_reason: str | None = None,
        block_until_closed: bool = False,
    ) -> None:
        self.incoming = [
            type("Frame", (), {"type": WSMsgType.TEXT, "data": json.dumps(item)})() for item in incoming
        ]
        self.sent: list[str] = []
        self.closed = False
        self.close_code = close_code
        self.close_reason = close_reason
        self.block_until_closed = block_until_closed
        self._closed_event = asyncio.Event()

    async def send_str(self, data: str) -> None:
        self.sent.append(data)

    async def receive(self):
        if self.incoming:
            return self.incoming.pop(0)
        if self.block_until_closed:
            await self._closed_event.wait()
        return type(
            "Frame",
            (),
            {"type": WSMsgType.CLOSE, "data": self.close_code, "extra": self.close_reason},
        )()

    async def close(self) -> None:
        self.closed = True
        self._closed_event.set()


def _session(socket: FakeSocket, *, websocket_status: int = 200) -> MockSession:
    session = MockSession()
    session.ws = socket
    if websocket_status == 200:
        session.routes[("GET", "/v2/websocket")] = Response(
            200,
            {
                "kind": "websocket#endpoint",
                "endpoint": "wss://example.com/socket?access_token=randomvalue",
            },
        )
    else:
        session.routes[("GET", "/v2/websocket")] = Response(websocket_status, text="")
    return session


def _auth(session: MockSession) -> SmartHQAuth:
    return SmartHQAuth(
        session,  # type: ignore[arg-type]
        {"access_token": "access-1", "expires_at": 9_999_999_999},
        host="https://twin.example",
    )


@pytest.mark.asyncio
async def test_connect_uses_the_endpoint_url_and_parses_events() -> None:
    socket = FakeSocket(
        [
            {"kind": "websocket#connect", "success": True},
            {
                "kind": "pubsub#presence",
                "deviceId": "device-1",
                "deviceType": "cloud.smarthq.device.washer",
                "presence": "ONLINE",
                "lastSyncTime": "2019-05-21T19:05:11.000Z",
            },
            {
                "kind": "pubsub#service",
                "deviceId": "device-1",
                "serviceType": "cloud.smarthq.service.toggle",
                "domainType": "cloud.smarthq.domain.power",
                "state": {"on": True},
                "statePrevious": {"on": False},
            },
        ]
    )
    session = _session(socket)
    stream = EventStream(_auth(session), idle_ping_seconds=None)
    endpoint = await stream.async_connect()
    assert endpoint.kind == "websocket#endpoint"
    assert endpoint.endpoint == "wss://example.com/socket?access_token=randomvalue"
    connect_call = session.requests[-1]
    assert connect_call["method"] == "WS"
    assert connect_call["url"] == endpoint.endpoint
    assert "headers" not in connect_call

    connected = await stream.async_receive()
    assert isinstance(connected, ConnectionEvent)
    assert connected.success is True
    presence = await stream.async_receive()
    assert isinstance(presence, PresenceEvent)
    assert presence.presence == "ONLINE"
    service = await stream.async_receive()
    assert isinstance(service, ServiceEvent)
    assert service.state == {"on": True}
    assert service.statePrevious == {"on": False}
    await stream.async_close()
    assert socket.closed


@pytest.mark.asyncio
async def test_configuration_messages_match_the_asyncapi_fields() -> None:
    socket = FakeSocket([{"kind": "websocket#pubsub", "success": True}])
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=None)
    await stream.async_connect()
    await stream.async_configure_account(pubsub=True, services=True, presence=False, alerts=True, commands=True)
    await stream.async_configure_device("device-1", services=True, alerts=True)
    await stream.async_ping(id="abc123")
    sent = [json.loads(item) for item in socket.sent]
    assert sent[0] == {
        "kind": "websocket#pubsub",
        "action": "pubsub",
        "pubsub": True,
        "services": True,
        "presence": False,
        "alerts": True,
        "commands": True,
    }
    assert sent[1] == {
        "kind": "websocket#pubsub",
        "action": "pubsub",
        "deviceId": "device-1",
        "services": True,
        "alerts": True,
    }
    assert "pubsub" not in sent[1]
    assert sent[2] == {"kind": "websocket#ping", "action": "ping", "id": "abc123"}
    ack = await stream.async_receive()
    assert isinstance(ack, PubsubAckEvent)
    assert ack.success is True
    await stream.async_close()


@pytest.mark.asyncio
async def test_alert_event_keeps_service_state() -> None:
    socket = FakeSocket(
        [
            {
                "kind": "pubsub#alert",
                "deviceId": "device-1",
                "adapterId": "adapter-1",
                "deviceType": "cloud.smarthq.device.fan",
                "alertType": "cloud.smarthq.alert.filterdirty",
                "lastAlertTime": "2021-02-26T14:07:23.354Z",
                "alertId": "alert-1",
                "services": [{"serviceType": "cloud.smarthq.service.mode", "state": {"mode": "low"}}],
            }
        ]
    )
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=None)
    await stream.async_connect()
    event = await stream.async_receive()
    assert isinstance(event, AlertEvent)
    assert event.alertType == "cloud.smarthq.alert.filterdirty"
    assert event.services[0]["state"]["mode"] == "low"
    await stream.async_close()


@pytest.mark.asyncio
async def test_closed_socket_and_oversized_payload() -> None:
    socket = FakeSocket([])
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=None)
    await stream.async_connect()
    with pytest.raises(SmartHQStreamClosed):
        await stream.async_receive()
    with pytest.raises(SmartHQError, match="32 KB"):
        await stream._send({"kind": "websocket#ping", "action": "ping", "id": "x" * 40000})
    assert socket.sent == []
    await stream.async_close()


@pytest.mark.asyncio
async def test_websocket_http_error_does_not_open_a_socket() -> None:
    session = _session(FakeSocket([]), websocket_status=401)
    stream = EventStream(_auth(session), idle_ping_seconds=None)
    with pytest.raises(SmartHQAuthError) as caught:
        await stream.async_connect()
    assert caught.value.status == 401
    assert all(item["method"] != "WS" for item in session.requests)


@pytest.mark.asyncio
async def test_idle_ping_follows_quiet_time() -> None:
    socket = FakeSocket([])
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=0.05)
    await stream.async_connect()
    await asyncio.sleep(0.18)
    sent = [json.loads(item) for item in socket.sent]
    assert sent
    assert sent[0]["kind"] == "websocket#ping"
    assert sent[0]["action"] == "ping"
    await stream.async_close()


@pytest.mark.asyncio
async def test_async_for_raises_stream_closed_with_the_close_code() -> None:
    socket = FakeSocket(
        [{"kind": "websocket#connect", "success": True}],
        close_code=1000,
        close_reason="expired",
    )
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=None)
    await stream.async_connect()
    seen = []
    with pytest.raises(SmartHQStreamClosed) as caught:
        async for event in stream:
            seen.append(event)
    assert len(seen) == 1
    assert caught.value.code == 1000
    assert caught.value.reason == "expired"
    assert "1000" in str(caught.value)
    await stream.async_close()


@pytest.mark.asyncio
async def test_second_connect_closes_the_first_socket_and_replays_config() -> None:
    first = FakeSocket([])
    second = FakeSocket([])
    session = _session(first)
    session.ws = [first, second]
    stream = EventStream(_auth(session), idle_ping_seconds=None)
    await stream.async_connect()
    await stream.async_configure_account(pubsub=True, services=True, presence=True)
    await stream.async_configure_device("device-1", services=True)
    await stream.async_connect()
    assert first.closed
    assert second.closed is False
    sent = [json.loads(item) for item in second.sent]
    assert sent[0]["pubsub"] is True
    assert sent[0]["services"] is True
    assert sent[1]["deviceId"] == "device-1"
    assert stream.socket_expires_at == 9_999_999_999
    await stream.async_close()


@pytest.mark.asyncio
async def test_ping_task_failure_still_closes_the_socket() -> None:
    class BoomSocket(FakeSocket):
        async def send_str(self, data: str) -> None:
            raise RuntimeError("send failed")

    socket = BoomSocket([])
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=0.05)
    await stream.async_connect()
    task = stream._keepalive
    assert task is not None
    for _ in range(50):
        if task.done():
            break
        await asyncio.sleep(0.02)
    assert task.done()
    with pytest.raises(RuntimeError, match="send failed"):
        await stream.async_close()
    assert socket.closed


@pytest.mark.asyncio
async def test_no_inbound_frame_within_the_grace_period() -> None:
    socket = FakeSocket([], block_until_closed=True)
    stream = EventStream(_auth(_session(socket)), idle_ping_seconds=0.05)
    await stream.async_connect()
    with pytest.raises(SmartHQStreamClosed, match="inbound"):
        await asyncio.wait_for(stream.async_receive(), timeout=1)
    assert socket.closed
    await stream.async_close()


@pytest.mark.asyncio
async def test_connect_failure_redacts_the_access_token() -> None:
    from aiohttp import ClientError

    from pysmarthq.models import WebsocketEndpoint

    session = MockSession()
    session.routes[("GET", "/v2/websocket")] = Response(
        200,
        {
            "kind": "websocket#endpoint",
            "endpoint": "wss://example.com/socket?access_token=secret-token",
        },
    )

    async def fail_connect(url: str, **kwargs: object) -> None:
        session.requests.append({"method": "WS", "url": url, **kwargs})
        raise ClientError(f"Cannot connect to host {url}")

    session.ws_connect = fail_connect  # type: ignore[method-assign]
    stream = EventStream(_auth(session), idle_ping_seconds=None)
    with pytest.raises(SmartHQError) as caught:
        await stream.async_connect()
    assert "secret-token" not in str(caught.value)
    assert "REDACTED" in str(caught.value)
    assert caught.value.__cause__ is None
    shown = WebsocketEndpoint(
        {"endpoint": "wss://example.com/socket?access_token=secret-token&x=1"},
        stream.auth,
    )
    assert "secret-token" not in repr(shown)
    assert "REDACTED" in repr(shown)
