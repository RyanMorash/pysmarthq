pysmarthq
=========

Async Python client for the `GE Appliances SmartHQ <https://docs.smarthq.com>`_ APIs.

The client covers three hosts:

* **Identity and Access Management** (``https://accounts.brillion.geappliances.com``) for OAuth 2.0 authorization and tokens.
* **Digital Twin** (``https://client.mysmarthq.com``) for devices, services, commands, and HTTPS/SNS pubsub.
* **Event stream** over the WebSocket URL returned by ``GET /v2/websocket``.

The OpenAPI and AsyncAPI documents in the repository ``specs/`` directory are the wire contract. The `SmartHQ documentation <https://docs.smarthq.com>`_ fills in flows those specs leave out, including token lifetimes, WebSocket keep-alive, and the difference between WebSocket and HTTPS/SNS delivery.

The package follows the `Home Assistant API library guidance <https://developers.home-assistant.io/docs/api_lib_index>`_: asyncio, aiohttp, no Home Assistant dependency, authentication separated from the API models, and model properties named after the API fields. The caller persists tokens. :meth:`~pysmarthq.events.EventStream.async_connect` opens one socket; the caller schedules the next connection.

.. toctree::
   :maxdepth: 2
   :caption: Guide

   installation
   quickstart
   authentication
   devices
   commands
   events
   errors
   coverage

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api/index

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
