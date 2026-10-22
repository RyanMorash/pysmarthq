Errors
======

:class:`~pysmarthq.errors.SmartHQError` is the base class. It carries ``status`` and ``body`` when the failure came from an HTTP response.

.. code-block:: text

   SmartHQError
   ├── SmartHQAuthError
   ├── SmartHQApiError
   └── SmartHQStreamClosed

:class:`~pysmarthq.errors.SmartHQAuthError`
   The Identity API rejected a token request, the access token is expired and no refresh credentials are available, or a Digital Twin call still returns HTTP 401 after one refresh. ``error`` and ``error_description`` are set when the token error body includes them.

:class:`~pysmarthq.errors.SmartHQApiError`
   A Digital Twin call returned a status outside the expected set. HTTP 403 uses this class. :meth:`~pysmarthq.models.CommandResponse.raise_for_outcome` also raises it when ``POST /v2/command`` returns HTTP 200 with ``success`` false. ``status`` is 200 in that case, and ``body`` is the response object.

:class:`~pysmarthq.errors.SmartHQStreamClosed`
   The event-stream WebSocket closed, the event queue passed :data:`~pysmarthq.const.EVENT_QUEUE_MAX_EVENTS`, or no inbound frame arrived within the ping grace period. ``code`` and ``reason`` are the WebSocket close code and reason when the peer sent a close frame. A network drop leaves them unset.

   ``async for`` raises this error after events already queued. Catch it to finish the read loop. :meth:`~pysmarthq.events.EventStream.async_close` raises it for a receiver waiting on that connection.

:class:`~pysmarthq.errors.SmartHQError` is also raised for client-side refusals before a request is sent: a device list that exceeds :data:`~pysmarthq.const.DEVICE_LIST_MAX_PAGES`, a batch command with no device filter, a command missing ``commandType``, a WebSocket payload over 32 KB, and :meth:`~pysmarthq.models.Device.apply_event` receiving an unsupported ``kind``.

:class:`ValueError` is raised by :func:`~pysmarthq.auth.authorization_url` and :func:`~pysmarthq.auth.registration_url` when ``response_type`` is other than ``code`` or ``access_type`` is other than ``offline`` or ``online``.
