Coverage
========

Wrapped operations are authorization URLs and token exchange, device list, detail, count, and remove, services, presence, settings, device alerts, single and batch commands plus command history and outcome summary, account and device pubsub, and the WebSocket event stream (connect, account and device configuration, ping, and the event messages in the AsyncAPI).

Routes that remain defined only in the Digital Twin spec:

* favorites
* gateways
* tags
* schema and policy routes
* file download
* alert reporting and history aggregates
* calculated or raw history

Service-specific command schemas (the ``CommandRequest`` ``oneOf``) are passed through as dictionaries. Fields are left as the API named them.

Specifications
--------------

.. list-table::
   :header-rows: 1
   :widths: 62 38

   * - File
     - API
   * - ``specs/smarthq-identity-and-access-management-openapi.json``
     - OAuth 2.0 authorization, token, logout, registration
   * - ``specs/smarthq-digital-twin-openapi.json``
     - Devices, services, commands, pubsub, WebSocket endpoint
   * - ``specs/smarthq-event-stream-asyncapi.json``
     - Event configuration and event messages

Where the SmartHQ guides and the specs disagree, requests follow the specs.

* Refreshing a token is ``POST /oauth2/token`` with ``grant_type=refresh_token``. The authorization sequence diagram also mentions ``POST /oauth2/refresh_token``, which is absent from the Identity spec.
* App logout is ``GET /oauth2/applogout``. One sentence in the authorization guide calls it ``POST``.
* ``POST /v2/device/{deviceId}/pubsub`` sends ``kind`` ``device#pubsub`` and the required ``pubsub`` field from ``DevicePubsubConfigRequest``. The guide's device example omits ``pubsub`` and describes that route as coming soon. The OpenAPI document already defines it.

``expires_at`` on the token dict is added locally from ``expires_in``. It is left off requests to SmartHQ.
