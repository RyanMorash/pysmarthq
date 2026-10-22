# pysmarthq

[![PyPI](https://img.shields.io/pypi/v/pysmarthq)](https://pypi.org/project/pysmarthq/)
[![Python versions](https://img.shields.io/pypi/pyversions/pysmarthq)](https://pypi.org/project/pysmarthq/)
[![Tests](https://github.com/RyanMorash/pysmarthq/actions/workflows/test.yml/badge.svg)](https://github.com/RyanMorash/pysmarthq/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/RyanMorash/pysmarthq/blob/main/LICENSE)

Async Python client for the [GE Appliances SmartHQ](https://docs.smarthq.com) APIs:

- Identity and Access Management at `https://accounts.brillion.geappliances.com`
- Digital Twin at `https://client.mysmarthq.com`
- The WebSocket event stream from `GET /v2/websocket`

pysmarthq is an asyncio library. Its only runtime dependency is [aiohttp](https://docs.aiohttp.org/). It follows the [Home Assistant API library guidance](https://developers.home-assistant.io/docs/api_lib_index): authentication is separate from the API models, and model properties use the API field names. Home Assistant is not required.

This is an unofficial client. GE Appliances does not publish it. GE, GE Appliances, and SmartHQ are trademarks of their owners.

The package is alpha (`0.1.0`). Names exported from `pysmarthq` are the supported surface, and they can change before 1.0.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Authentication](#authentication)
- [Devices](#devices)
- [Commands](#commands)
- [Events](#events)
- [Errors](#errors)
- [Public API](#public-api)
- [Coverage](#coverage)
- [Specifications](#specifications)
- [Development](#development)
- [License](#license)

## Installation

```bash
pip install pysmarthq
```

Python 3.11 or newer is required. The runtime dependency is `aiohttp` 3.9 or newer. Continuous integration runs the test suite on Python 3.11, 3.12, and 3.13.

## Quick start

Create an application in the SmartHQ Developer Portal and keep the client id, client secret, and callback URL. Open the authorization URL in a browser. SmartHQ redirects to that callback with `code`, `expires_in`, and the `state` you sent.

```python
import asyncio

import aiohttp

from pysmarthq import (
    SmartHQApi,
    SmartHQAuth,
    async_exchange_code,
    authorization_url,
    parse_authorization_callback,
)

CLIENT_ID = "your-client-id"
CLIENT_SECRET = "your-client-secret"
REDIRECT_URI = "https://example.com/callback"
STATE = "state-from-your-app"


async def main() -> None:
    print(
        authorization_url(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            state=STATE,
        )
    )
    callback = parse_authorization_callback(
        "https://example.com/callback?code=AUTH_CODE"
        "&state=state-from-your-app&expires_in=600"
    )
    if callback.get("state") != STATE or "error" in callback or "code" not in callback:
        message = callback.get("error_description") or callback.get("error") or "Authorization failed"
        raise RuntimeError(message)

    async with aiohttp.ClientSession() as session:
        token = await async_exchange_code(
            session,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            code=callback["code"],
            redirect_uri=REDIRECT_URI,
        )
        save_token(token)
        auth = SmartHQAuth(
            session,
            token,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_updater=save_token,
        )
        api = SmartHQApi(auth)
        for device in await api.async_get_all_devices():
            print(device.deviceId, device.deviceType, device.nickname)


def save_token(updated: dict) -> None:
    """Store the whole token dict, including refresh_token and expires_at."""


asyncio.run(main())
```

Keep the client secret on a server you control. Compare `state` with the value your application created before exchanging the code. `redirect_uri` must be the callback URL configured for the app. An authorization code is single-use and valid for 10 minutes.

Call `save_token` with the dict from `async_exchange_code`. `SmartHQAuth` calls it again after a refresh. That callback may be a function or a coroutine. It runs inside the refresh lock, so it must not call back into the client.

A device appears in the API after the user commissions it with the SmartHQ app. Authorization and registration do not commission a device.

## Authentication

`authorization_url` builds `GET /oauth2/auth`. `registration_url` builds `GET /oauth2/register`. Both return the SmartHQ web page. The authorization guide recommends sending every user to `GET /oauth2/auth`. That page links to registration, and the query carries over.

`logout_url` builds `GET /oauth2/applogout`. Open it in the same browser that ran authorization. It clears the SmartHQ browser session and redirects with `logout=success`. Access tokens and refresh tokens remain valid. Read the redirects with `parse_authorization_callback` and `parse_logout_callback`.

`authorization_url` defaults to `response_type=code` and `access_type=offline`. Offline access is what returns a refresh token. `access_type=online` leaves the user to authorize again when the access token expires.

`async_exchange_code` posts `grant_type=authorization_code` to `POST /oauth2/token`. The returned dict is the token response plus a local `expires_at` Unix time computed from `expires_in`. Store the whole dict. `expires_at` is local and is not sent back to SmartHQ. The authorization guide gives an access token one hour, and a refresh token until the next refresh. The refresh token in that next response is then the only valid refresh token.

`SmartHQAuth` posts `grant_type=refresh_token` when `expires_at` is missing or fewer than 60 seconds remain. A token with exactly 60 seconds left is still current. Pass `client_id`, `client_secret`, and a stored refresh token for the refresh to run. A refresh body that omits `refresh_token`, or sets it to `null` or `""`, keeps the previous refresh token in the dict handed to `token_updater`. Persist that dict before the process exits. If the process stops after SmartHQ has issued a new refresh token and before the save succeeds, the refresh token still on disk is rejected. If `token_updater` raises, the new token stays in memory and the next `async_get_access_token` retries the updater without another token request.

A Home Assistant install that refreshes tokens outside this package can subclass `AbstractAuth` and implement `async_get_access_token`. Override `token_expires_at` when that subclass does not keep a `token` dict. `SmartHQApi` and `EventStream` accept any `AbstractAuth`. `token_expires_at` returns `None` when the expiry is unknown.

Token requests, Digital Twin requests, and the WebSocket handshake each use a 30 second total timeout. Pass another `aiohttp.ClientTimeout` as `timeout` to `async_exchange_code`, `async_refresh_token`, or `SmartHQAuth` for that token call. `SmartHQAuth` uses its timeout when it refreshes. Digital Twin calls and the handshake stay at 30 seconds.

An HTTP 401 refreshes once and retries. A second 401, or a failed refresh, raises `SmartHQAuthError`. HTTP 403 raises `SmartHQApiError`.

## Devices

`async_get_devices` returns one page of `GET /v2/device`. Query names match the spec: `page`, `perpage`, `sort`, `order`, and the device filters (`deviceType`, `model`, `brand`, and the rest of the Digital Twin list). `sort` accepts `nickname`.

`async_get_all_devices` requests 100 devices per page. It stops when `total` is covered, a short page comes back, or every device on the page has an id already collected. A row with no device id is kept. The next request number is one more than the number of requests already made. The `page` field in the response is used when checking `total`, and it does not choose the next request. More than 100 requests raises `SmartHQError`. Filters other than `page` and `perpage` are sent on every page.

List payloads omit services. Load the device with `async_get_device` or `Device.async_update` before reading services.

Property names match the JSON fields (`device.deviceId`, `device.deviceType`). `raw_data` keeps the full payload. `Device.find_service` matches `serviceType` and any `domainType` or `serviceDeviceType` you pass. When more than one service matches those keys, `find_service` returns `None`.

```python
washer = await api.async_get_device(device_id)
await washer.async_update()
for service in washer.services or []:
    print(service.serviceType, service.domainType, service.state)
```

Other device reads are `async_get_presence`, `async_get_settings`, `async_get_setting`, and `async_get_alerts`. `async_remove` deletes the device.

## Commands

A single-device command is the `service#command` body for `POST /v2/command`. Service-specific command schemas are not generated. Pass the command object through. Fields stay as you set them.

```python
result = await device.async_send_command(
    serviceType="cloud.smarthq.service.dishwasher.state.v1",
    domainType="cloud.smarthq.domain.dishwasher",
    serviceDeviceType="cloud.smarthq.device.dishwasher",
    command={"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"},
)
print(result.correlationId)
```

`POST /v2/command` returns HTTP 200 for a processed command, including a body whose `success` field is false. `Device.async_send_command` and `Service.async_send_command` raise `SmartHQApiError` in that case. `SmartHQApi.async_send_command` returns the body so you can read `success` and `outcome`. A later `pubsub#command` event can still carry the device outcome when account configuration has `commands` enabled.

`async_send_commands` posts a `service#commands` body to `POST /v2/commands`. The body needs `kind`, `serviceType`, `domainType`, `serviceDeviceType`, and `command` with `commandType`. Device selection is the query string. At least one device filter is required (`deviceId`, `deviceType`, or another `GET /v2/device` filter). An empty filter set would match every device that has the service, so the client raises `SmartHQError` before sending.

```python
batch = await api.async_send_commands(
    {
        "kind": "service#commands",
        "serviceType": "cloud.smarthq.service.temperature",
        "domainType": "cloud.smarthq.domain.setpoint",
        "serviceDeviceType": "cloud.smarthq.device.refrigerator.freshfood",
        "command": {
            "commandType": "cloud.smarthq.command.temperature.set",
            "fahrenheit": 40,
        },
    },
    params={"deviceType": "cloud.smarthq.device.refrigerator"},
)
print(batch.total, batch.correlationId)
```

Follow-up calls are `async_get_command`, `async_get_command_summary`, `async_get_command_history`, and `async_get_batch_command_history`.

## Events

WebSocket preferences and HTTPS/SNS preferences are independent. Socket messages use `kind` `websocket#pubsub`. Account and device HTTPS/SNS preferences are `POST /v2/pubsub` and `POST /v2/device/{deviceId}/pubsub`, with `kind` `user#pubsub` or `device#pubsub`. Register an HTTPS callback URL with SmartHQ when you configure the app. These specs have no operation for that registration.

The WebSocket URL from `GET /v2/websocket` already contains the access token. Fetch a new URL for every connection. `async_connect` closes the current socket and sends the stored account and per-device configuration again. That stored configuration is replaced after the send completes. `socket_expires_at` is `auth.token_expires_at()` sampled when `GET /v2/websocket` returns, before the handshake. Schedule the next connect from it when it is set. The client does not reconnect on its own.

A background reader is the only caller of `receive`. `async_receive` returns events already queued, then raises `SmartHQStreamClosed` for that connection. The close code and reason are set when the peer sent them. The error stays on the connection that produced it, including after a later reconnect. `async for` raises that error. It does not end the iterator. `async_close` wakes a receiver waiting on that connection with `SmartHQStreamClosed`. A ping task that has already failed is not raised again from `async_close`. Cancelling `async_close` still propagates.

The buffer holds 1024 events. Another text frame fails the stream with `SmartHQStreamClosed`. Protocol PING and PONG frames take no slot. A protocol PONG counts as inbound traffic. A protocol PING is answered and does not count as inbound. A `websocket#pong` text frame is returned as an event.

SmartHQ closes a socket that stays idle for 10 minutes. The client sends `websocket#ping` after 60 seconds without other traffic. Pass `idle_ping_seconds=None` to disable that ping. A sent ping only proves the write was accepted. With pinging enabled, about two quiet ping intervals without an inbound frame raises `SmartHQStreamClosed`.

```python
from pysmarthq import EventStream, SmartHQStreamClosed

stream = EventStream(auth)
await stream.async_connect()
await stream.async_configure_account(
    pubsub=True,
    services=True,
    presence=True,
    alerts=True,
    commands=True,
)
try:
    async for event in stream:
        print(event.kind)
        device = devices_by_id.get(getattr(event, "deviceId", None))
        if device is not None:
            device.apply_event(event)
except SmartHQStreamClosed as err:
    print(err, err.code, err.reason)
finally:
    await stream.async_close()
```

`EventStream` is also an async context manager. `async_close` keeps the stored configuration for the next `async_connect`.

`Device.apply_event` copies `pubsub#service`, `pubsub#presence`, `pubsub#alert`, and `pubsub#device` fields onto the device. A payload whose `deviceId` differs from this device is left unchanged. A payload that omits `deviceId` is applied. `created` and `removed` are registry events. The device object does not add or remove itself. `pubsub#command`, `websocket#connect`, `websocket#pong`, and `websocket#pubsub` are ignored. Any other kind raises `SmartHQError`.

`GET` pubsub bodies omit `pubsub`. On `PubsubConfig`, `pubsub is None` means the field was absent.

## Errors

| Exception | When it is raised |
| --- | --- |
| `SmartHQError` | Base class. Also used when the client refuses a request, such as a batch command with no device filter or a device list past 100 pages. `status` and `body` are set when the failure came from an HTTP response. |
| `SmartHQAuthError` | The token endpoint rejected a request, the access token cannot be refreshed, or a Digital Twin call returns 401 after one refresh. `error` and `error_description` are the OAuth fields when the body has them. |
| `SmartHQApiError` | A Digital Twin call returned a status outside the success set, including HTTP 403. Also raised by `Device.async_send_command` and `Service.async_send_command` when HTTP 200 comes back with `success: false`. |
| `SmartHQStreamClosed` | The event stream closed, went silent, or filled its buffer. `code` and `reason` are set when the peer sent a close frame. Reconnect with a new `GET /v2/websocket` URL. `async_connect` sends the stored configuration again. |

An `access_token` query value in exception text is redacted.

## Public API

```python
from pysmarthq import (
    AbstractAuth,
    Device,
    EventStream,
    Service,
    SmartHQApi,
    SmartHQApiError,
    SmartHQAuth,
    SmartHQAuthError,
    SmartHQError,
    SmartHQStreamClosed,
    async_exchange_code,
    async_refresh_token,
    authorization_url,
    logout_url,
    parse_authorization_callback,
    parse_logout_callback,
    registration_url,
)
```

`SmartHQApi` methods:

| Method | Operation |
| --- | --- |
| `async_get_devices` | `GET /v2/device` (one page) |
| `async_get_all_devices` | `GET /v2/device` (every page, at most 100 requests) |
| `async_get_device` | `GET /v2/device/{deviceId}` |
| `async_get_device_count` | `GET /v2/device/count` |
| `async_send_command` | `POST /v2/command` |
| `async_send_commands` | `POST /v2/commands` |
| `async_get_command` | `GET /v2/command/{correlationId}` |
| `async_get_command_summary` | `GET /v2/command/{correlationId}/summary` |
| `async_get_command_history` | `GET /v2/command` |
| `async_get_batch_command_history` | `GET /v2/commands` |
| `async_get_pubsub` / `async_set_pubsub` / `async_delete_pubsub` | `GET`, `POST`, and `DELETE /v2/pubsub` |
| `async_get_websocket_endpoint` | `GET /v2/websocket` |

`async_receive` returns an event with `kind` and `raw_data`. Known kinds are `websocket#connect`, `websocket#pong`, `websocket#pubsub`, `pubsub#device`, `pubsub#presence`, `pubsub#service`, `pubsub#alert`, and `pubsub#command`.

The installed distribution includes a `py.typed` marker.

## Coverage

Wrapped operations are authorization URLs and token exchange, device list, detail, count, and remove, services, presence, settings, device alerts, single and batch commands, command history and outcome summary, account and device pubsub, and the WebSocket event stream.

The Digital Twin spec also defines favorites, gateways, tags, schema and policy routes, file download, alert reporting and history aggregates, and calculated or raw history. Those routes have no client methods.

## Specifications

The OpenAPI and AsyncAPI documents are the wire contract. They live in the [GitHub repository](https://github.com/RyanMorash/pysmarthq) and are not installed with the wheel. [SmartHQ docs](https://docs.smarthq.com) describe token lifetimes, WebSocket keep-alive, and the split between WebSocket and HTTPS/SNS delivery.

| Document | API |
| --- | --- |
| [Identity and Access Management](https://github.com/RyanMorash/pysmarthq/blob/main/specs/smarthq-identity-and-access-management-openapi.json) | OAuth 2.0 authorization, token, logout, registration |
| [Digital Twin](https://github.com/RyanMorash/pysmarthq/blob/main/specs/smarthq-digital-twin-openapi.json) | Devices, services, commands, pubsub, WebSocket endpoint |
| [Event Stream](https://github.com/RyanMorash/pysmarthq/blob/main/specs/smarthq-event-stream-asyncapi.json) | Event configuration and event messages |

Requests follow the specs where the narrative docs differ:

- Token refresh is `POST /oauth2/token` with `grant_type=refresh_token`. The authorization sequence diagram also names `POST /oauth2/refresh_token`, which is absent from the Identity spec.
- App logout is `GET /oauth2/applogout`. One sentence in the authorization guide calls that route `POST`.
- `POST /v2/device/{deviceId}/pubsub` sends `kind` `device#pubsub` and the required `pubsub` field from `DevicePubsubConfigRequest`. The guide's device example omits `pubsub` and describes that route as coming soon. The OpenAPI document defines it.

## Development

```bash
pip install -e ".[dev]"
pytest
```

To try an editable checkout inside Home Assistant:

```bash
pip3 install -e /path/to/pysmarthq
hass --skip-pip-packages pysmarthq
```

Publishing a GitHub Release runs the [publish workflow](https://github.com/RyanMorash/pysmarthq/blob/main/.github/workflows/publish.yml). That workflow builds the sdist and wheel and uploads them to PyPI with trusted publishing.

Issues and source are on GitHub: [RyanMorash/pysmarthq](https://github.com/RyanMorash/pysmarthq). Leave access tokens, refresh tokens, client secrets, and WebSocket URLs out of reports. Those URLs contain an access token.

## License

[MIT](https://github.com/RyanMorash/pysmarthq/blob/main/LICENSE). Copyright (c) 2026 Ryan Morash.
