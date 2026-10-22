Quickstart
==========

Create an app in the SmartHQ Developer Portal to get a client id, client secret, and callback URL. Send the user to the authorization URL in a browser. SmartHQ redirects back with ``code``, ``expires_in``, and your ``state``.

Public names are imported from :mod:`pysmarthq`.

.. code-block:: python

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

The sections below explain each step. List payloads omit services, so :meth:`~pysmarthq.models.Device.async_update` loads ``GET /v2/device/{deviceId}`` before the example reads ``washer.services``. :class:`~pysmarthq.events.EventStream` fetches a new WebSocket URL on every :meth:`~pysmarthq.events.EventStream.async_connect` and leaves reconnection to the caller.

Keep the client secret out of source control. Pass it through the environment or the host application's secret store.
