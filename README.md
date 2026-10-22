# pysmarthq

[![PyPI](https://img.shields.io/pypi/v/pysmarthq)](https://pypi.org/project/pysmarthq/)
[![Python versions](https://img.shields.io/pypi/pyversions/pysmarthq)](https://pypi.org/project/pysmarthq/)
[![Tests](https://github.com/RyanMorash/pysmarthq/actions/workflows/test.yml/badge.svg)](https://github.com/RyanMorash/pysmarthq/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/RyanMorash/pysmarthq/blob/main/LICENSE)

Async Python client for the [GE Appliances SmartHQ](https://docs.smarthq.com) APIs:

- Identity and Access Management (`https://accounts.brillion.geappliances.com`)
- Digital Twin (`https://client.mysmarthq.com`)
- Event Stream over the WebSocket URL from `GET /v2/websocket`

The client is asyncio-only, depends on [aiohttp](https://docs.aiohttp.org/), and does not depend on Home Assistant. It follows the [Home Assistant API library guidance](https://developers.home-assistant.io/docs/api_lib_index): authentication is separate from the API models, and model properties use the API field names.

pysmarthq is an unofficial client. It is not published by GE Appliances. GE, GE Appliances, and SmartHQ are trademarks of their owners.

The package is in alpha. Import names and behavior can change before 1.0. The supported surface is the names exported from `pysmarthq` (see [Public API](#public-api)).

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

Requires Python 3.11 or newer. The only runtime dependency is `aiohttp` 3.9 or newer.

Continuous integration runs the test suite on Python 3.11 and 3.12.

## Quick start

Create an application in the SmartHQ Developer Portal and note the client id, client secret, and callback URL. Send the user to the authorization URL in a browser. SmartHQ redirects back to your callback with `code`, `expires_in`, and the `state` you sent.

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
    # After the browser returns to your callback:
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

Keep the client secret on a server you control. Compare `state` with the value your application generated before exchanging the code. `redirect_uri` on the token request must be the same URI as the callback URL configured for the app. The authorization code is single-use and valid for 10 minutes.

`save_token` may be a normal function or an async function. Call it yourself with the dict from `async_exchange_code`. `SmartHQAuth` calls it again after a refresh. That callback runs inside the refresh lock, so it must not call back into the client.

Devices show up in the API after the user commissions them with the SmartHQ app. Completing authorization or registration does not commission a device.

## Authentication

`GET /oauth2/auth` and `GET /oauth2/register` return the SmartHQ web page. The authorization guide recommends sending every user to `GET /oauth2/auth`. That page links to registration, and the query parameters carry over. `registration_url` builds `GET /oauth2/register` when you do need the register page directly.

`GET /oauth2/applogout` clears that browser session and redirects with `logout=success`. App logout does not revoke access or refresh tokens. Build the three URLs with `authorization_url`, `registration_url`, and `logout_url`, then read the redirects with `parse_authorization_callback` and `parse_logout_callback`.

`authorization_url` defaults to `response_type=code` and `access_type=offline`. Offline access is what returns a refresh token. `access_type` may also be `online`. With online access, the user has to authorize again when the access token expires.

`async_exchange_code` posts `grant_type=authorization_code` to `POST /oauth2/token`. The returned dict is the token response plus a local `expires_at` (Unix time) computed from `expires_in`. Store that whole dict. `expires_at` is added locally and is not sent back to SmartHQ. Documented lifetimes are one hour for an access token and until the next refresh for a refresh token.

`SmartHQAuth` calls `POST /oauth2/token` with `grant_type=refresh_token` when `expires_at` is missing or fewer than 60 seconds remain. Pass `client_id`, `client_secret`, and a stored refresh token for that to work. A refresh response that omits `refresh_token` keeps the previous value. The authorization guide says the refresh token returned by a refresh is then the only valid refresh token, so persist the dict from `token_updater` before the process exits. If the process stops after SmartHQ has rotated the refresh token and before that save succeeds, the refresh token still on disk is no longer accepted. If `token_updater` raises, the new token stays in memory and the next `async_get_access_token` retries the updater without another token request.

A Home Assistant install that refreshes tokens through account linking can subclass `AbstractAuth` and implement `async_get_access_token`. `SmartHQApi` and `EventStream` accept any `AbstractAuth`.

Digital Twin requests, token requests, and the WebSocket handshake use a 30 second total timeout. Pass another `aiohttp.ClientTimeout` as `timeout` to `async_exchange_code`, `async_refresh_token`, or `SmartHQAuth` to change that token call. `SmartHQAuth` uses its timeout when it refreshes. Digital Twin calls and the WebSocket handshake stay at 30 seconds.

An HTTP 401 refreshes once and retries. A second 401, or a failed refresh, raises `SmartHQAuthError`. HTTP 403 stays `SmartHQApiError`.

## Devices

`async_get_devices` returns one page of `GET /v2/device`. Pass spec query names in `params`, including `page`, `perpage`, `sort`, `order`, and the device filters (`deviceType`, `model`, `brand`, and the rest listed in the Digital Twin spec). `sort` accepts `nickname`.

`async_get_all_devices` asks for 100 devices per page and follows `page` until `total` is covered or a short page comes back. Extra filters are sent on every page.

List payloads do not include services. Load `GET /v2/device/{deviceId}` with `async_get_device`, or `Device.async_update`, before reading services or creating entities.

Property names match the JSON fields (`device.deviceId`, `device.deviceType`). `raw_data` keeps the full payload, including fields that have no property. `Device.find_service` matches `serviceType` plus optional `domainType` and `serviceDeviceType`. Several services can share a service type. When more than one service matches the keys you passed, `find_service` returns `None`.

```python
washer = await api.async_get_device(device_id)
await washer.async_update()
for service in washer.services or []:
    print(service.serviceType, service.domainType, service.state)
```

Other device reads are `async_get_presence`, `async_get_settings`, `async_get_setting`, and `async_get_alerts`. `async_remove` deletes the device.

## Commands

A single-device command uses the `service#command` body from `POST /v2/command`. Service-specific command schemas are not generated as classes. Pass the command object through; fields are not renamed or converted.

```python
result = await device.async_send_command(
    serviceType="cloud.smarthq.service.dishwasher.state.v1",
    domainType="cloud.smarthq.domain.dishwasher",
    serviceDeviceType="cloud.smarthq.device.dishwasher",
    command={"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"},
)
print(result.correlationId)
```

`POST /v2/command` returns HTTP 200 for a processed command, including commands whose `success` field is false. `Device.async_send_command` and `Service.async_send_command` raise `SmartHQApiError` in that case (`CommandResponse.raise_for_outcome`). `SmartHQApi.async_send_command` returns the body unchanged so you can inspect `success` and `outcome` yourself. A later `pubsub#command` event can still carry the device outcome when account configuration has `commands` enabled.

`async_send_commands` posts a `service#commands` body to `POST /v2/commands`. The body needs `kind`, `serviceType`, `domainType`, `serviceDeviceType`, and `command` (with `commandType`). Device selection is the query string, and at least one device filter is required (`deviceId`, `deviceType`, or another `GET /v2/device` filter). With none set, the call would match every device that has the service.

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

Command follow-up calls are `async_get_command`, `async_get_command_summary`, `async_get_command_history`, and `async_get_batch_command_history`.

## Events

WebSocket preferences and HTTPS/SNS preferences are separate. Messages on the socket use `kind` `websocket#pubsub`. Account and device HTTPS/SNS preferences are `POST /v2/pubsub` and `POST /v2/device/{deviceId}/pubsub` (`kind` `user#pubsub` or `device#pubsub`). Changing one channel leaves the other as it was. Registering an HTTPS callback URL is done with SmartHQ when you configure the app. There is no API operation in these specs for that registration.

The WebSocket URL from `GET /v2/websocket` already includes the access token. Fetch it again for every connection. `async_connect` closes the previous socket and sends the last account and per-device configuration again. `socket_expires_at` is the `expires_at` of the token used to fetch that URL, when the auth object carries a token dict. Schedule the next connect from it. The client does not run a reconnect loop.

`async for` raises `SmartHQStreamClosed` when the socket closes, with the close code and reason when the peer sent them. It does not end the iterator. SmartHQ closes a socket that stays idle for 10 minutes. The client sends `websocket#ping` after 60 seconds without other traffic (`idle_ping_seconds`). A ping only proves the write was accepted. If no inbound frame arrives within about two ping intervals, the stream raises `SmartHQStreamClosed`. Pass `idle_ping_seconds=None` to disable that ping.

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

`Device.apply_event` copies `pubsub#service`, `pubsub#presence`, `pubsub#alert`, and `pubsub#device` fields onto the device. `created` and `removed` are device-registry events; the device object does not add or remove itself. `pubsub#command`, `websocket#connect`, `websocket#pong`, and `websocket#pubsub` are ignored. Any other kind raises `SmartHQError`.

`GET` pubsub bodies omit `pubsub`. `PubsubConfig.pubsub is None` means the field was absent, not that pubsub is off.

## Errors

| Exception | When it is raised |
| --- | --- |
| `SmartHQError` | Base class. Also used for a request the client refuses to send, such as a batch command with no device filter. `status` and `body` are set when the failure came from an HTTP response. |
| `SmartHQAuthError` | The token endpoint rejected a request, the access token cannot be refreshed, or a Digital Twin call returns 401 after one refresh. `error` and `error_description` are the OAuth fields when the body has them. |
| `SmartHQApiError` | A Digital Twin call returned a status outside the success set, including HTTP 403. Also raised by `Device.async_send_command` and `Service.async_send_command` when HTTP 200 comes back with `success: false`. |
| `SmartHQStreamClosed` | The event-stream WebSocket closed or went silent. `code` and `reason` are set when the peer sent a close frame. Reconnect with a new `GET /v2/websocket` URL and send the configuration messages again. |

Access tokens that appear in exception text as an `access_token` query parameter are redacted.

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
| `async_get_all_devices` | `GET /v2/device` (every page) |
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

`async_receive` returns an event object with `kind` and `raw_data`. Known kinds are `websocket#connect`, `websocket#pong`, `websocket#pubsub`, `pubsub#device`, `pubsub#presence`, `pubsub#service`, `pubsub#alert`, and `pubsub#command`.

The installed distribution includes a `py.typed` marker.

## Coverage

Wrapped operations are authorization URLs and token exchange, device list, detail, count, and remove, services, presence, settings, device alerts, single and batch commands plus command history and outcome summary, account and device pubsub, and the WebSocket event stream (connect, account and device configuration, ping, and the event messages in the AsyncAPI).

The Digital Twin spec also defines favorites, gateways, tags, schema and policy routes, file download, alert reporting and history aggregates, and calculated or raw history. Those routes are not wrapped.

## Specifications

The OpenAPI and AsyncAPI documents are the wire contract. They ship in the [GitHub repository](https://github.com/RyanMorash/pysmarthq) and are not installed with the wheel. [SmartHQ docs](https://docs.smarthq.com) fill in flows those specs do not describe, including token lifetimes, WebSocket keep-alive, and the difference between WebSocket and HTTPS/SNS event delivery.

| File | API |
| --- | --- |
| [Identity and Access Management](https://github.com/RyanMorash/pysmarthq/blob/main/specs/smarthq-identity-and-access-management-openapi.json) | OAuth 2.0 authorization, token, logout, registration |
| [Digital Twin](https://github.com/RyanMorash/pysmarthq/blob/main/specs/smarthq-digital-twin-openapi.json) | Devices, services, commands, pubsub, WebSocket endpoint |
| [Event Stream](https://github.com/RyanMorash/pysmarthq/blob/main/specs/smarthq-event-stream-asyncapi.json) | Event configuration and event messages |

Where the docs and the specs disagree, requests follow the specs:

- Refreshing a token is `POST /oauth2/token` with `grant_type=refresh_token`. The authorization sequence diagram also mentions `POST /oauth2/refresh_token`, which is not in the Identity spec.
- App logout is `GET /oauth2/applogout`. One sentence in the authorization guide calls it `POST`.
- `POST /v2/device/{deviceId}/pubsub` sends `kind` `device#pubsub` and the required `pubsub` field from `DevicePubsubConfigRequest`. The guide's device example omits `pubsub` and describes that route as coming soon; the OpenAPI document already defines it.

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

Publishing a GitHub Release runs the [publish workflow](https://github.com/RyanMorash/pysmarthq/blob/main/.github/workflows/publish.yml), which builds the sdist and wheel and uploads them to PyPI with trusted publishing.

Issues and source live on GitHub: [RyanMorash/pysmarthq](https://github.com/RyanMorash/pysmarthq). Omit access tokens, refresh tokens, client secrets, and WebSocket URLs from reports. Those URLs contain an access token.

## License

[MIT](https://github.com/RyanMorash/pysmarthq/blob/main/LICENSE). Copyright (c) 2026 Ryan Morash.
