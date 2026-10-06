"""Digital Twin client tests."""

from __future__ import annotations

import pytest

from pysmarthq import SmartHQApi, SmartHQApiError, SmartHQAuth
from pysmarthq.models import Device

from tests.mock_http import MockSession, Response, json_body


def _auth(session: MockSession) -> SmartHQAuth:
    return SmartHQAuth(
        session,  # type: ignore[arg-type]
        {"access_token": "access-1", "expires_at": 9_999_999_999},
        host="https://twin.example",
    )


@pytest.mark.asyncio
async def test_list_and_detail_devices_keep_api_fields() -> None:
    session = MockSession()
    session.routes[("GET", "/v2/device")] = Response(
        200,
        {
            "kind": "device#list",
            "page": 1,
            "perpage": 50,
            "total": 1,
            "userId": "user-1",
            "devices": [
                {
                    "deviceId": "device-1",
                    "deviceType": "cloud.smarthq.device.washer",
                    "nickname": "Washer",
                    "presence": "ONLINE",
                }
            ],
        },
    )
    session.routes[("GET", "/v2/device/device-1")] = Response(
        200,
        {
            "kind": "device#item",
            "deviceId": "device-1",
            "deviceType": "cloud.smarthq.device.washer",
            "alertTypes": ["cloud.smarthq.alert.endofcycle"],
            "services": [
                {
                    "serviceId": "service-1",
                    "serviceType": "cloud.smarthq.service.toggle",
                    "domainType": "cloud.smarthq.domain.power",
                    "serviceDeviceType": "cloud.smarthq.device.washer",
                    "supportedCommands": ["cloud.smarthq.command.toggle.set"],
                    "state": {"on": False},
                    "config": {},
                }
            ],
        },
    )
    api = SmartHQApi(_auth(session))
    listed = await api.async_get_devices(params={"deviceType": "cloud.smarthq.device.washer", "page": 1})
    assert listed.kind == "device#list"
    assert listed.total == 1
    assert listed.userId == "user-1"
    device = listed.devices[0]
    assert device.deviceId == "device-1"
    assert device.nickname == "Washer"
    assert device.services is None
    assert session.requests[0]["params"] == {
        "deviceType": "cloud.smarthq.device.washer",
        "page": 1,
    }
    assert session.requests[0]["headers"]["Authorization"] == "Bearer access-1"

    await device.async_update()
    assert device.kind == "device#item"
    assert device.alertTypes == ["cloud.smarthq.alert.endofcycle"]
    service = device.services[0]
    assert service.state == {"on": False}
    assert service.state is device.raw_data["services"][0]["state"]


@pytest.mark.asyncio
async def test_send_command_uses_the_service_command_envelope() -> None:
    session = MockSession()
    session.routes[("POST", "/v2/command")] = Response(
        200,
        {
            "kind": "service#command",
            "success": True,
            "correlationId": "corr-1",
            "services": [],
            "outcome": "cloud.smarthq.outcome.success",
        },
    )
    device = Device(
        {"deviceId": "device-1", "deviceType": "cloud.smarthq.device.dishwasher"},
        _auth(session),
    )
    result = await device.async_send_command(
        serviceType="cloud.smarthq.service.dishwasher.state.v1",
        domainType="cloud.smarthq.domain.dishwasher",
        serviceDeviceType="cloud.smarthq.device.dishwasher",
        command={"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"},
    )
    assert result.correlationId == "corr-1"
    assert result.success is True
    assert json_body(session.requests[0]) == {
        "kind": "service#command",
        "deviceId": "device-1",
        "serviceType": "cloud.smarthq.service.dishwasher.state.v1",
        "domainType": "cloud.smarthq.domain.dishwasher",
        "serviceDeviceType": "cloud.smarthq.device.dishwasher",
        "command": {"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"},
    }


@pytest.mark.asyncio
async def test_command_requires_command_type() -> None:
    device = Device({"deviceId": "device-1"}, _auth(MockSession()))
    with pytest.raises(Exception, match="commandType"):
        await device.async_send_command(
            serviceType="cloud.smarthq.service.toggle",
            domainType="cloud.smarthq.domain.power",
            serviceDeviceType="cloud.smarthq.device.light",
            command={"on": True},
        )


@pytest.mark.asyncio
async def test_batch_command_and_history() -> None:
    session = MockSession()
    session.routes[("POST", "/v2/commands")] = Response(
        200,
        {"kind": "service#commands", "total": 3, "correlationId": "batch-1"},
    )
    session.routes[("GET", "/v2/command/batch-1")] = Response(
        200,
        {
            "kind": "command#outcomes",
            "correlationId": "batch-1",
            "page": 1,
            "perpage": 50,
            "total": 1,
            "command": {"commandType": "cloud.smarthq.command.temperature.set"},
            "outcomes": [
                {
                    "deviceId": "device-1",
                    "outcome": "cloud.smarthq.outcome.success",
                    "serviceType": "cloud.smarthq.service.temperature",
                }
            ],
        },
    )
    session.routes[("GET", "/v2/command/batch-1/summary")] = Response(
        200,
        {
            "kind": "command#summary",
            "correlationId": "batch-1",
            "total": 1,
            "success": 1,
            "failed": 0,
            "timeout": 0,
            "unknown": 0,
            "outcomes": [{"outcome": "cloud.smarthq.outcome.success", "count": 1}],
        },
    )
    api = SmartHQApi(_auth(session))
    batch = await api.async_send_commands(
        {
            "kind": "service#commands",
            "serviceType": "cloud.smarthq.service.temperature",
            "domainType": "cloud.smarthq.domain.setpoint",
            "serviceDeviceType": "cloud.smarthq.device.refrigerator.freshfood",
            "command": {"commandType": "cloud.smarthq.command.temperature.set", "fahrenheit": 40},
        },
        params={"deviceType": "cloud.smarthq.device.refrigerator"},
    )
    assert session.requests[0]["params"] == {"deviceType": "cloud.smarthq.device.refrigerator"}
    assert batch.total == 3
    outcomes = await api.async_get_command("batch-1", params={"deviceId": "device-1"})
    assert outcomes.outcomes[0].outcome == "cloud.smarthq.outcome.success"
    assert outcomes.command["commandType"] == "cloud.smarthq.command.temperature.set"
    summary = await api.async_get_command_summary("batch-1")
    assert summary.success == 1
    assert summary.outcomes[0]["count"] == 1


@pytest.mark.asyncio
async def test_api_error_status_and_empty_body() -> None:
    session = MockSession()
    session.routes[("GET", "/v2/device")] = Response(403)
    session.routes[("DELETE", "/v2/device/device-1")] = Response(404, text="")
    api = SmartHQApi(_auth(session))
    with pytest.raises(SmartHQApiError) as caught:
        await api.async_get_devices()
    assert caught.value.status == 403
    assert caught.value.body is None

    device = Device({"deviceId": "device-1"}, api.auth)
    with pytest.raises(SmartHQApiError) as deleted:
        await device.async_remove()
    assert deleted.value.status == 404


@pytest.mark.asyncio
async def test_delete_device_accepts_no_content() -> None:
    session = MockSession()
    session.routes[("DELETE", "/v2/device/device-1")] = Response(204)
    device = Device({"deviceId": "device-1"}, _auth(session))
    await device.async_remove()
    assert session.requests[0]["method"] == "DELETE"


@pytest.mark.asyncio
async def test_account_and_device_pubsub_bodies() -> None:
    session = MockSession()
    session.routes[("POST", "/v2/pubsub")] = Response(200, {"kind": "user#pubsub", "success": True})
    session.routes[("GET", "/v2/pubsub")] = Response(
        200,
        {
            "kind": "user#pubsub",
            "services": True,
            "presence": False,
            "alerts": False,
            "commands": False,
        },
    )
    session.routes[("DELETE", "/v2/pubsub")] = Response(204)
    session.routes[("POST", "/v2/device/device-1/pubsub")] = Response(
        200,
        {"kind": "device#pubsub", "success": True},
    )
    api = SmartHQApi(_auth(session))
    written = await api.async_set_pubsub(pubsub=True, services=True, alerts=False)
    assert written.success is True
    assert json_body(session.requests[0]) == {
        "kind": "user#pubsub",
        "pubsub": True,
        "services": True,
        "alerts": False,
    }
    current = await api.async_get_pubsub()
    assert current.services is True
    assert current.pubsub is None
    await api.async_delete_pubsub()

    device = Device({"deviceId": "device-1"}, api.auth)
    await device.async_set_pubsub(pubsub=True, presence=True)
    assert json_body(session.requests[-1]) == {
        "kind": "device#pubsub",
        "pubsub": True,
        "presence": True,
    }


@pytest.mark.asyncio
async def test_presence_settings_alerts_and_count() -> None:
    session = MockSession()
    session.routes[("GET", "/v2/device/count")] = Response(
        200,
        {
            "kind": "device#count",
            "userId": "user-1",
            "devices": [{"deviceType": "cloud.smarthq.device.washer", "count": 2}],
        },
    )
    session.routes[("GET", "/v2/device/device-1/presence")] = Response(
        200,
        {
            "kind": "device#presence",
            "deviceId": "device-1",
            "presence": "OFFLINE",
            "history": [{"presenceTime": "2024-09-11T19:03:46.347Z", "presence": "OFFLINE"}],
        },
    )
    session.routes[("GET", "/v2/device/device-1/setting")] = Response(
        200,
        {
            "kind": "device#settings",
            "settings": [
                {
                    "ruleId": "rule-1",
                    "title": "Shutoff Valve Closed on Water Heater",
                    "description": "Get a notification when the shutoff valve has been closed",
                    "ruleEnabled": True,
                }
            ],
        },
    )
    session.routes[("GET", "/v2/device/device-1/alert")] = Response(
        200,
        {
            "kind": "device#alerts",
            "deviceId": "device-1",
            "totalTriggeredAlerts": 1,
            "totalTriggeredFaults": 0,
            "alerts": [{"alertType": "cloud.smarthq.alert.endofcycle", "alertId": "alert-1"}],
        },
    )
    api = SmartHQApi(_auth(session))
    count = await api.async_get_device_count()
    assert count.devices[0]["count"] == 2
    device = Device({"deviceId": "device-1"}, api.auth)
    presence = await device.async_get_presence()
    assert presence.presence == "OFFLINE"
    assert presence.history[0]["presence"] == "OFFLINE"
    settings = await device.async_get_settings()
    assert settings.settings[0].ruleEnabled is True
    alerts = await device.async_get_alerts(params={"status": "triggered"})
    assert alerts.alerts[0].alertType == "cloud.smarthq.alert.endofcycle"
    assert session.requests[-1]["params"] == {"status": "triggered"}


def _batch_body() -> dict:
    return {
        "kind": "service#commands",
        "serviceType": "cloud.smarthq.service.temperature",
        "domainType": "cloud.smarthq.domain.setpoint",
        "serviceDeviceType": "cloud.smarthq.device.refrigerator.freshfood",
        "command": {"commandType": "cloud.smarthq.command.temperature.set", "fahrenheit": 40},
    }


@pytest.mark.asyncio
async def test_device_list_follows_pages_of_100() -> None:
    session = MockSession()

    def devices(method: str, url: str, kwargs: dict) -> Response:
        params = kwargs["params"]
        assert params["perpage"] == 100
        assert params["deviceType"] == "cloud.smarthq.device.washer"
        page = params["page"]
        if page == 1:
            rows = [{"deviceId": f"d{index}"} for index in range(100)]
        elif page == 2:
            rows = [{"deviceId": f"d{index}"} for index in range(100, 150)]
        else:
            raise AssertionError(page)
        return Response(
            200,
            {"kind": "device#list", "page": page, "perpage": 100, "total": 150, "devices": rows},
        )

    session.routes[("GET", "/v2/device")] = devices
    api = SmartHQApi(_auth(session))
    listed = await api.async_get_all_devices(params={"deviceType": "cloud.smarthq.device.washer", "page": 9})
    assert [device.deviceId for device in listed] == [f"d{index}" for index in range(150)]
    assert [item["params"]["page"] for item in session.requests] == [1, 2]


@pytest.mark.asyncio
async def test_batch_command_requires_a_filter() -> None:
    from pysmarthq import SmartHQError

    api = SmartHQApi(_auth(MockSession()))
    with pytest.raises(SmartHQError, match="device filter"):
        await api.async_send_commands(_batch_body())
    with pytest.raises(SmartHQError, match="device filter"):
        await api.async_send_commands(_batch_body(), params={"page": 1})


@pytest.mark.asyncio
async def test_401_refreshes_once_and_a_second_401_is_an_auth_error() -> None:
    from pysmarthq import SmartHQAuthError

    session = MockSession()
    attempts = {"n": 0}

    def devices(method: str, url: str, kwargs: dict) -> Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return Response(401, text="")
        return Response(200, {"kind": "device#list", "page": 1, "perpage": 50, "total": 0, "devices": []})

    session.routes[("GET", "/v2/device")] = devices
    session.routes[("POST", "/oauth2/token")] = Response(
        200,
        {
            "token_type": "Bearer",
            "expires_in": 3600,
            "access_token": "access-2",
            "refresh_token": "refresh-2",
        },
    )
    auth = SmartHQAuth(
        session,  # type: ignore[arg-type]
        {"access_token": "access-1", "refresh_token": "refresh-1", "expires_at": 9_999_999_999},
        client_id="client",
        client_secret="secret",
        host="https://twin.example",
        iam_host="https://iam.example",
    )
    listed = await SmartHQApi(auth).async_get_devices()
    assert listed.devices == []
    assert attempts["n"] == 2
    token_calls = [item for item in session.requests if item["url"].endswith("/oauth2/token")]
    assert len(token_calls) == 1
    assert session.requests[-1]["headers"]["Authorization"] == "Bearer access-2"

    denied = MockSession()
    denied.routes[("GET", "/v2/device")] = Response(401, {"message": "token rejected"})
    denied.routes[("POST", "/oauth2/token")] = Response(
        200,
        {
            "token_type": "Bearer",
            "expires_in": 3600,
            "access_token": "access-3",
            "refresh_token": "refresh-3",
        },
    )
    auth = SmartHQAuth(
        denied,  # type: ignore[arg-type]
        {"access_token": "access-1", "refresh_token": "refresh-1", "expires_at": 9_999_999_999},
        client_id="client",
        client_secret="secret",
        host="https://twin.example",
        iam_host="https://iam.example",
    )
    with pytest.raises(SmartHQAuthError) as caught:
        await SmartHQApi(auth).async_get_devices()
    assert caught.value.status == 401
    assert "token rejected" in str(caught.value)
    assert len([item for item in denied.requests if item["url"].endswith("/oauth2/token")]) == 1
    assert len([item for item in denied.requests if item["url"].endswith("/v2/device")]) == 2


@pytest.mark.asyncio
async def test_error_string_includes_a_body_snippet_and_non_objects_fail() -> None:
    session = MockSession()
    session.routes[("GET", "/v2/device")] = Response(403, {"message": "forbidden for this client"})
    with pytest.raises(SmartHQApiError) as caught:
        await SmartHQApi(_auth(session)).async_get_devices()
    assert "forbidden for this client" in str(caught.value)
    assert caught.value.status == 403

    session.routes[("GET", "/v2/device")] = Response(200, text="[]")
    with pytest.raises(SmartHQApiError, match="not a JSON object"):
        await SmartHQApi(_auth(session)).async_get_devices()


@pytest.mark.asyncio
async def test_boolean_query_values_are_lowercase() -> None:
    from aiohttp import ClientSession, web
    from aiohttp.test_utils import TestServer

    seen: dict[str, str] = {}

    async def handler(request: web.Request) -> web.Response:
        seen["query"] = request.query_string
        return web.json_response({"kind": "device#alerts", "deviceId": "device-1", "alerts": []})

    app = web.Application()
    app.router.add_get("/v2/device/device-1/alert", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        async with ClientSession() as session:
            host = str(server.make_url("/")).rstrip("/")
            auth = SmartHQAuth(
                session,
                {"access_token": "access-1", "expires_at": 9_999_999_999},
                host=host,
            )
            device = Device({"deviceId": "device-1"}, auth)
            await device.async_get_alerts(params={"fault": True, "clear": False, "onlyTriggered": True})
    finally:
        await server.close()
    assert seen["query"]
    assert "fault=true" in seen["query"]
    assert "clear=false" in seen["query"]
    assert "onlyTriggered=true" in seen["query"]
    assert "True" not in seen["query"]
    assert "False" not in seen["query"]


@pytest.mark.asyncio
async def test_service_update_is_visible_on_the_parent_device() -> None:
    session = MockSession()
    session.routes[("GET", "/v2/device/device-1/service/power")] = Response(
        200,
        {
            "serviceId": "power",
            "serviceType": "cloud.smarthq.service.toggle",
            "domainType": "cloud.smarthq.domain.power",
            "serviceDeviceType": "cloud.smarthq.device.washer",
            "state": {"on": True},
        },
    )
    device = Device(
        {
            "deviceId": "device-1",
            "services": [
                {
                    "serviceId": "power",
                    "serviceType": "cloud.smarthq.service.toggle",
                    "domainType": "cloud.smarthq.domain.power",
                    "serviceDeviceType": "cloud.smarthq.device.washer",
                    "state": {"on": False},
                }
            ],
        },
        _auth(session),
    )
    service = device.services[0]
    await service.async_update()
    assert device.services[0] is service
    assert device.services[0].state == {"on": True}
    assert device.raw_data["services"][0]["state"] == {"on": True}


def _washer() -> dict:
    return {
        "deviceId": "device-1",
        "presence": "OFFLINE",
        "services": [
            {
                "serviceId": "temp-set",
                "serviceType": "cloud.smarthq.service.temperature",
                "domainType": "cloud.smarthq.domain.setpoint",
                "serviceDeviceType": "cloud.smarthq.device.refrigerator.freshfood",
                "state": {"fahrenheit": 37, "celsius": 3},
                "config": {"fahrenheitDefault": 37},
                "supportedCommands": ["cloud.smarthq.command.temperature.set"],
            },
            {
                "serviceId": "temp-actual",
                "serviceType": "cloud.smarthq.service.temperature",
                "domainType": "cloud.smarthq.domain.actual.temperature",
                "serviceDeviceType": "cloud.smarthq.device.refrigerator.freshfood",
                "state": {"fahrenheit": 40},
                "config": {},
            },
            {
                "serviceId": "power",
                "serviceType": "cloud.smarthq.service.toggle",
                "domainType": "cloud.smarthq.domain.power",
                "serviceDeviceType": "cloud.smarthq.device.washer",
                "state": {"on": False},
            },
        ],
    }


@pytest.mark.asyncio
async def test_apply_event_updates_services_without_wiping_state() -> None:
    device = Device(_washer(), _auth(MockSession()))
    assert device.find_service("cloud.smarthq.service.temperature") is None
    setpoint = device.find_service(
        "cloud.smarthq.service.temperature",
        domainType="cloud.smarthq.domain.setpoint",
    )
    assert setpoint is not None
    assert setpoint.serviceId == "temp-set"

    device.apply_event(
        {
            "kind": "pubsub#service",
            "serviceId": "power",
            "state": {"on": True},
            "lastStateTime": "2024-01-01T00:00:00.000Z",
        }
    )
    assert device.services[2].state == {"on": True}
    assert device.raw_data["services"][2]["lastStateTime"] == "2024-01-01T00:00:00.000Z"

    device.apply_event(
        {
            "kind": "pubsub#presence",
            "presence": "ONLINE",
            "lastSyncTime": "2024-01-01T00:00:01.000Z",
        }
    )
    assert device.presence == "ONLINE"
    assert device.lastSyncTime == "2024-01-01T00:00:01.000Z"

    device.apply_event(
        {
            "kind": "pubsub#alert",
            "alertType": "cloud.smarthq.alert.endofcycle",
            "alertId": "alert-1",
            "clear": "true",
            "lastAlertTime": "2024-01-01T00:00:02.000Z",
            "services": [
                {
                    "serviceId": "power",
                    "state": {"on": False},
                    "lastStateTime": "2024-01-01T00:00:02.000Z",
                }
            ],
        }
    )
    stored = device.raw_data["alerts"][0]
    assert stored["clear"] == "true"
    assert isinstance(stored["clear"], str)
    assert stored["alertType"] == "cloud.smarthq.alert.endofcycle"
    assert device.services[2].state == {"on": False}

    device.apply_event(
        {
            "kind": "pubsub#device",
            "event": "removed",
            "services": [
                {
                    "serviceId": "temp-set",
                    "config": {"fahrenheitDefault": 34},
                    "supportedCommands": ["cloud.smarthq.command.temperature.set"],
                }
            ],
        }
    )
    assert device.services[0].state == {"fahrenheit": 37, "celsius": 3}
    assert device.services[0].config == {"fahrenheitDefault": 34}
    assert device.services[0].supportedCommands == ["cloud.smarthq.command.temperature.set"]
    assert len(device.services) == 3


@pytest.mark.asyncio
async def test_raise_for_outcome_on_http_200() -> None:
    session = MockSession()
    session.routes[("POST", "/v2/command")] = Response(
        200,
        {
            "kind": "service#command",
            "success": False,
            "correlationId": "corr-1",
            "outcome": "cloud.smarthq.outcome.timeout",
        },
    )
    api = SmartHQApi(_auth(session))
    raw = await api.async_send_command(
        {
            "kind": "service#command",
            "deviceId": "device-1",
            "serviceType": "cloud.smarthq.service.toggle",
            "domainType": "cloud.smarthq.domain.power",
            "serviceDeviceType": "cloud.smarthq.device.washer",
            "command": {"commandType": "cloud.smarthq.command.toggle.set", "on": True},
        }
    )
    assert raw.success is False
    with pytest.raises(SmartHQApiError) as caught:
        raw.raise_for_outcome()
    assert caught.value.status == 200
    assert "cloud.smarthq.outcome.timeout" in str(caught.value)
    assert caught.value.body["success"] is False

    device = Device({"deviceId": "device-1"}, api.auth)
    with pytest.raises(SmartHQApiError) as sent:
        await device.async_send_command(
            serviceType="cloud.smarthq.service.toggle",
            domainType="cloud.smarthq.domain.power",
            serviceDeviceType="cloud.smarthq.device.washer",
            command={"commandType": "cloud.smarthq.command.toggle.set", "on": True},
        )
    assert sent.value.status == 200
    assert sent.value.body["outcome"] == "cloud.smarthq.outcome.timeout"
