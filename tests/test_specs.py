"""The copied specifications still describe the operations this client calls."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs"


def _load(name: str) -> dict:
    return json.loads((SPECS / name).read_text())


def test_identity_spec_covers_oauth() -> None:
    spec = _load("smarthq-identity-and-access-management-openapi.json")
    assert spec["servers"][0]["url"] == "https://accounts.brillion.geappliances.com"
    assert set(spec["paths"]) == {
        "/oauth2/auth",
        "/oauth2/token",
        "/oauth2/applogout",
        "/oauth2/register",
    }
    assert "get" in spec["paths"]["/oauth2/applogout"]
    grant = spec["paths"]["/oauth2/token"]["post"]["requestBody"]["content"][
        "application/x-www-form-urlencoded"
    ]["schema"]
    assert grant["properties"]["grant_type"]["enum"] == ["authorization_code", "refresh_token"]


def test_digital_twin_spec_covers_the_wrapped_operations() -> None:
    spec = _load("smarthq-digital-twin-openapi.json")
    assert spec["servers"][0]["url"] == "https://client.mysmarthq.com"
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    paths = spec["paths"]
    for path in (
        "/v2/device",
        "/v2/device/{deviceId}",
        "/v2/device/count",
        "/v2/device/{deviceId}/service/{serviceId}",
        "/v2/device/{deviceId}/presence",
        "/v2/device/{deviceId}/setting",
        "/v2/device/{deviceId}/setting/{ruleId}",
        "/v2/device/{deviceId}/alert",
        "/v2/command",
        "/v2/commands",
        "/v2/command/{correlationId}",
        "/v2/command/{correlationId}/summary",
        "/v2/pubsub",
        "/v2/device/{deviceId}/pubsub",
        "/v2/websocket",
    ):
        assert path in paths


def test_event_stream_spec_uses_one_channel_and_both_directions() -> None:
    spec = _load("smarthq-event-stream-asyncapi.json")
    assert spec["asyncapi"] == "3.0.0"
    assert spec["operations"]["/.send"]["action"] == "send"
    assert spec["operations"]["/.receive"]["action"] == "receive"
    schemas = spec["components"]["schemas"]
    account = schemas["Account-Level Configuration Request"]
    assert account["properties"]["kind"]["enum"] == ["websocket#pubsub", "user#pubsub"]
    assert "pubsub" in account["required"]
    device = schemas["Device-Level Configuration Request"]["properties"]
    assert "deviceId" in device
    assert "pubsub" not in device
    assert schemas["WebSocket Ping Request"]["properties"]["kind"]["enum"] == ["websocket#ping"]
