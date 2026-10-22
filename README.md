# pysmarthq

Async Python client for the [GE Appliances SmartHQ](https://docs.smarthq.com) APIs:

- Identity and Access Management (`https://accounts.brillion.geappliances.com`)
- Digital Twin (`https://client.mysmarthq.com`)
- Event Stream over the WebSocket URL from `GET /v2/websocket`

The OpenAPI and AsyncAPI documents in [`specs/`](specs/) are the wire contract. [SmartHQ docs](https://docs.smarthq.com) fill in flows those specs do not describe, including token lifetimes, WebSocket keep-alive, and the difference between WebSocket and HTTPS/SNS event delivery.

The package follows the [Home Assistant API library guidance](https://developers.home-assistant.io/docs/api_lib_index): asyncio, aiohttp, no Home Assistant dependency, authentication separated from the API models, and model properties named after the API fields.

## Install

```bash
pip install .
```

For local development:

```bash
pip install -e ".[dev]"
```

To try an editable checkout inside Home Assistant:

```bash
pip3 install -e /path/to/pysmarthq
hass --skip-pip-packages pysmarthq
```

## Usage

Create an app in the SmartHQ Developer Portal to get a client id, client secret, and callback URL. Send the user to the authorization URL in a browser. SmartHQ redirects back with `code`, `expires_in`, and your `state`.

```python
import asyncio

import aiohttp

from pysmarthq import (
    EventStream,
    SmartHQApi,
    SmartHQAuth,
    async_exchange_code,
    authorization_url,
    parse_authorization_callback,
)

CLIENT_ID = "your-client-id"
CLIENT_SECRET = "your-client-secret"
REDIRECT_URI = "https://example.com/callback"


async def main() -> None:
    print(
        authorization_url(
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            state="state-from-your-app",
        )
    )
    # After the browser returns to your callback:
    callback = parse_authorization_callback(
        "https://example.com/callback?code=AUTH_CODE&state=state-from-your-app&expires_in=600"
    )

    async with aiohttp.ClientSession() as session:
        token = await async_exchange_code(
            session,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            code=callback["code"],
            redirect_uri=REDIRECT_URI,
        )

        def save_token(updated: dict) -> None:
            # Persist this dict yourself. The library does not store it.
            print(updated["access_token"], updated["expires_at"])

        auth = SmartHQAuth(
            session,
            token,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_updater=save_token,
        )
        api = SmartHQApi(auth)
        devices = await api.async_get_devices()
        for device in devices.devices:
            print(device.deviceId, device.deviceType, device.nickname)

        washer = next(
            device
            for device in devices.devices
            if device.deviceType == "cloud.smarthq.device.washer"
        )
        await washer.async_update()
        for service in washer.services or []:
            print(service.serviceType, service.domainType, service.state)

        stream = EventStream(auth)
        await stream.async_connect()
        await stream.async_configure_account(pubsub=True, services=True, presence=True)
        event = await stream.async_receive()
        print(event.kind, event.raw_data)
        await stream.async_close()


asyncio.run(main())
```

`GET /oauth2/auth` and `GET /oauth2/register` return a SmartHQ web page. `GET /oauth2/applogout` clears that browser session and does not revoke tokens. Build those URLs with `authorization_url`, `registration_url`, and `logout_url`.

Access tokens are bearer tokens for the Digital Twin API. `SmartHQAuth` calls `POST /oauth2/token` with `grant_type=refresh_token` when `expires_at` is missing or fewer than 60 seconds remain. A token with exactly 60 seconds left is still current. `expires_at` is computed from `expires_in` when the token response arrives. A refresh response that omits `refresh_token`, or sets it to null or `""`, keeps the previous value. If `token_updater` raises, the new token stays in memory and the next `async_get_access_token` retries the updater without another token request. Do not call the client from `token_updater`; it runs inside the refresh lock. A Home Assistant install that refreshes tokens through account linking can subclass `AbstractAuth` and implement `async_get_access_token` instead. Override `token_expires_at` when that subclass does not keep a `token` dict.

An HTTP 401 refreshes once and retries. A second 401, or a failed refresh, raises `SmartHQAuthError`. HTTP 403 stays `SmartHQApiError`.

`async_get_devices` returns one page. `async_get_all_devices` asks for 100 devices per page and follows `page` until `total` is covered, a short page comes back, or every device on a page has an id already collected. The next page is one more than the number of requests, not the `page` field in the response. More than 100 requests raises `SmartHQError`. List payloads do not include services; load `GET /v2/device/{deviceId}` before creating entities.

A single-device command uses the `service#command` body from `POST /v2/command`:

```python
await device.async_send_command(
    serviceType="cloud.smarthq.service.dishwasher.state.v1",
    domainType="cloud.smarthq.domain.dishwasher",
    serviceDeviceType="cloud.smarthq.device.dishwasher",
    command={"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"},
)
```

`Device.async_send_command` and `Service.async_send_command` raise `SmartHQApiError` when HTTP 200 comes back with `success: false` (`CommandResponse.raise_for_outcome`). `SmartHQApi.async_send_command` returns that body unchanged. `POST /v2/commands` requires at least one device filter (`deviceId`, `deviceType`, or the other device-list filters). With none set, the call would match every device that has the service.

WebSocket event preferences are messages on the socket (`kind` `websocket#pubsub`). HTTPS/SNS preferences are `POST /v2/pubsub` and `POST /v2/device/{deviceId}/pubsub` (`kind` `user#pubsub` or `device#pubsub`). The two channels do not affect each other. The WebSocket URL from `GET /v2/websocket` already includes the access token; fetch it again for every connection. `async_connect` closes the previous socket and sends the last account and per-device configuration again. That stored configuration changes only after the send completes. `socket_expires_at` is `token_expires_at()` sampled when `GET /v2/websocket` returns, before the handshake; schedule the next connect from it when it is set. The client does not run a reconnect loop. A background reader is the only `receive` caller. `async for` raises `SmartHQStreamClosed` when the socket closes, with the close code and reason when the peer sent them, after events already queued. That error stays with the connection that produced it. `async_close` raises `SmartHQStreamClosed` for a receiver waiting on that connection. At most 1024 events are buffered; another text frame fails the stream with `SmartHQStreamClosed`. Protocol PING and PONG frames are not buffered. A protocol PONG counts as inbound. A protocol PING is answered and does not. A ping only proves the write was accepted: if no inbound frame arrives within about two ping intervals, the stream raises `SmartHQStreamClosed`. `async_close` finishes when the ping task has already failed and does not re-raise that error.

`Device.apply_event` copies `pubsub#service`, `pubsub#presence`, `pubsub#alert`, and `pubsub#device` fields onto the device. A payload with a different `deviceId` is ignored. A payload that omits `deviceId` is still applied. `Device.find_service` matches `serviceType` plus optional `domainType` and `serviceDeviceType`. `GET` pubsub bodies omit `pubsub`; `PubsubConfig.pubsub is None` means the field was absent, not that pubsub is off.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Specifications

| File | API |
| --- | --- |
| `specs/smarthq-identity-and-access-management-openapi.json` | OAuth 2.0 authorization, token, logout, registration |
| `specs/smarthq-digital-twin-openapi.json` | Devices, services, commands, pubsub, WebSocket endpoint |
| `specs/smarthq-event-stream-asyncapi.json` | Event configuration and event messages |

## Coverage and differences

Wrapped operations are authorization URLs and token exchange, device list/detail/count/remove, services, presence, settings, device alerts, single and batch commands plus command history and outcome summary, account and device pubsub, and the WebSocket event stream (connect, account and device configuration, ping, and the event messages in the AsyncAPI).

Not wrapped, and still defined in the Digital Twin spec: favorites, gateways, tags, schema and policy routes, file download, alert reporting and history aggregates, and calculated or raw history. Service-specific command schemas (the `CommandRequest` `oneOf`) are not generated as classes. Pass the command object through; fields are not renamed or converted.

Where the docs and the specs disagree, requests follow the specs:

- Refreshing a token is `POST /oauth2/token` with `grant_type=refresh_token`. The authorization sequence diagram also mentions `POST /oauth2/refresh_token`, which is not in the Identity spec.
- App logout is `GET /oauth2/applogout`. One sentence in the authorization guide calls it `POST`.
- `POST /v2/device/{deviceId}/pubsub` sends `kind` `device#pubsub` and the required `pubsub` field from `DevicePubsubConfigRequest`. The guide's device example omits `pubsub` and describes that route as coming soon; the OpenAPI document already defines it.

`expires_at` on the token dict is added locally from `expires_in`. It is not sent back to SmartHQ.
