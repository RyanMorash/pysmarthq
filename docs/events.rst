Events
======

SmartHQ has two event channels. They do not change each other's preferences.

* **WebSocket.** :class:`~pysmarthq.events.EventStream` sends ``kind`` ``websocket#pubsub``. The socket carries live messages.
* **HTTPS/SNS.** :meth:`~pysmarthq.api.SmartHQApi.async_set_pubsub` sends ``kind`` ``user#pubsub`` to ``POST /v2/pubsub``. :meth:`~pysmarthq.models.Device.async_set_pubsub` sends ``kind`` ``device#pubsub`` to ``POST /v2/device/{deviceId}/pubsub``. Registering the callback URL is done with SmartHQ. These specs have no operation for that registration.

``GET`` pubsub bodies omit ``pubsub``. :attr:`~pysmarthq.models.PubsubConfig.pubsub` is ``None`` when the field was absent. That value does not mean pubsub is off. The booleans ``services``, ``presence``, ``alerts``, and ``commands`` are what a ``GET`` response reports.

Connect
-------

``GET /v2/websocket`` returns a URL that already includes the access token. The URL is per user and changes. Fetch it again for every connection. :meth:`~pysmarthq.events.EventStream.async_connect` does that fetch, then opens the socket.

.. code-block:: python

   stream = EventStream(auth)
   endpoint = await stream.async_connect()
   # endpoint.endpoint is the URL. Its repr redacts access_token.

:attr:`~pysmarthq.events.EventStream.socket_expires_at` is :meth:`~pysmarthq.auth.AbstractAuth.token_expires_at` sampled when ``GET /v2/websocket`` returns, before the handshake. Schedule the next connect from it when it is set. The client runs one connection at a time and leaves the reconnect loop to the caller.

:meth:`~pysmarthq.events.EventStream.async_connect` closes the current socket first. After the handshake it sends the last account configuration and the last configuration for each device again. Stored configuration changes only after the send that stored it completes. The connect acknowledgement stays on the queue. Read it with :meth:`~pysmarthq.events.EventStream.async_receive`. A failed connect leaves the stream disconnected.

The same object is an async context manager. Entering it calls ``async_connect``. Exiting it calls ``async_close``.

.. code-block:: python

   async with EventStream(auth) as stream:
       await stream.async_configure_account(pubsub=True, services=True, presence=True)
       event = await stream.async_receive()

Configure
---------

:meth:`~pysmarthq.events.EventStream.async_configure_account` sends an account-level WebSocket configuration message. ``kind`` is ``websocket#pubsub`` and ``action`` is ``pubsub``. Optional flags left as ``None`` are omitted from the payload.

.. code-block:: python

   await stream.async_configure_account(
       pubsub=True,
       services=True,
       presence=True,
       alerts=True,
       commands=True,
   )

:meth:`~pysmarthq.events.EventStream.async_configure_device` sends a device-level message. Account pubsub must already be enabled. This payload has no ``pubsub`` field. That field belongs to the account configuration and to the Digital Twin device pubsub body.

.. code-block:: python

   await stream.async_configure_device(
       device_id,
       services=True,
       presence=True,
   )

HTTPS/SNS preferences use the Digital Twin routes. Omitted booleans are left out so the service can apply its defaults. ``pubsub`` is required.

.. code-block:: python

   await api.async_set_pubsub(pubsub=True, services=True, presence=True)
   await device.async_set_pubsub(pubsub=True, alerts=True)
   await api.async_delete_pubsub()
   await device.async_delete_pubsub()

Read events
-----------

The library reads the socket on a background task. Take events from the queue with :meth:`~pysmarthq.events.EventStream.async_receive` or ``async for``. Each event is delivered once.

.. code-block:: python

   from pysmarthq.events import ServiceEvent

   async for event in stream:
       if isinstance(event, ServiceEvent):
           device.apply_event(event)

:func:`~pysmarthq.events.parse_event` picks a subclass from ``kind``. An unknown kind is a plain :class:`~pysmarthq.events.Event`. ``raw_data`` is the decoded JSON object.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Kind
     - Class
   * - ``websocket#connect``
     - :class:`~pysmarthq.events.ConnectionEvent`
   * - ``websocket#pong``
     - :class:`~pysmarthq.events.PongEvent`
   * - ``websocket#pubsub``
     - :class:`~pysmarthq.events.PubsubAckEvent`
   * - ``pubsub#device``
     - :class:`~pysmarthq.events.DeviceEvent`
   * - ``pubsub#presence``
     - :class:`~pysmarthq.events.PresenceEvent`
   * - ``pubsub#service``
     - :class:`~pysmarthq.events.ServiceEvent`
   * - ``pubsub#alert``
     - :class:`~pysmarthq.events.AlertEvent`
   * - ``pubsub#command``
     - :class:`~pysmarthq.events.CommandEvent`

``websocket#pubsub`` here is the acknowledgement described in the real-time updates guide (``kind`` and ``success``). It is separate from the configuration message the client sends, which uses the same ``kind``.

Queued events are returned before a close error. ``async for`` raises :class:`~pysmarthq.errors.SmartHQStreamClosed` when the socket closes, with the close code and reason when the peer sent them. The iterator raises that error on the next step. Catch it around the loop. The error stays with the connection that produced it.

At most :data:`~pysmarthq.const.EVENT_QUEUE_MAX_EVENTS` (1024) events are buffered. Another text frame fails the stream with :class:`~pysmarthq.errors.SmartHQStreamClosed`. Protocol PING and PONG frames are not buffered. A protocol PONG counts as inbound traffic. A protocol PING is answered and does not count as inbound. A ``websocket#pong`` text frame is returned as :class:`~pysmarthq.events.PongEvent`.

Keepalive and close
-------------------

The real-time updates guide closes idle sockets after 10 minutes and suggests a ping after 60 seconds without other traffic. ``idle_ping_seconds`` defaults to :data:`~pysmarthq.const.WEBSOCKET_IDLE_PING_SECONDS`. Pass ``None`` to leave the ping off.

.. code-block:: python

   stream = EventStream(auth, idle_ping_seconds=None)
   await stream.async_ping(id="1")

With pinging enabled, the socket fails when no inbound frame arrives within about two ping intervals (:data:`~pysmarthq.const.WEBSOCKET_INBOUND_GRACE_INTERVALS`). A ping only proves the write was accepted. JSON payloads larger than :data:`~pysmarthq.const.WEBSOCKET_MAX_PAYLOAD_BYTES` (32 KB) raise :class:`~pysmarthq.errors.SmartHQError` before they are sent.

:meth:`~pysmarthq.events.EventStream.async_close` stops the reader and the idle ping, then closes the socket. The socket is closed even when the ping task has already failed. ``async_close`` does not re-raise that failure. Cancellation of ``async_close`` still propagates. A receiver waiting on that connection raises :class:`~pysmarthq.errors.SmartHQStreamClosed`. Stored event configuration is kept for the next ``async_connect``.

Reconnect
---------

SmartHQ closes the socket when the access token expires. On :class:`~pysmarthq.errors.SmartHQStreamClosed`:

1. Let the next Digital Twin call refresh the access token, or refresh it yourself.
2. Call :meth:`~pysmarthq.events.EventStream.async_connect` again. That fetches a new WebSocket URL and sends the stored account and device configuration.

Apply an event to a device
--------------------------

:meth:`~pysmarthq.models.Device.apply_event` copies fields onto the device without renaming them.

* ``pubsub#service`` updates ``state``, ``config``, ``lastSyncTime``, and ``lastStateTime`` on the matching service when those keys are present.
* ``pubsub#presence`` sets ``presence`` and ``lastSyncTime``.
* ``pubsub#alert`` stores the alert fields the payload has (``clear`` stays a string) and applies each nested service the same way as a service event.
* ``pubsub#device`` copies ``config`` and ``supportedCommands`` from the embedded services and leaves ``state`` in place when the event omits it.
* ``pubsub#command``, ``websocket#connect``, ``websocket#pong``, and ``websocket#pubsub`` are ignored.
* Any other ``kind`` raises :class:`~pysmarthq.errors.SmartHQError`.

A payload whose ``deviceId`` differs from this device is ignored. A payload that omits ``deviceId`` is still applied. ``created`` and ``removed`` are device-registry events. ``apply_event`` does not add or remove the :class:`~pysmarthq.models.Device` object itself.
