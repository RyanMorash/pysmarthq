Commands
========

A single-device command uses the ``service#command`` body from ``POST /v2/command``. :meth:`~pysmarthq.models.Device.async_send_command` builds that envelope. ``command`` must include ``commandType``. Other command fields are sent unchanged. Service-specific command schemas are passed through as dictionaries; this client has no generated class per command.

.. code-block:: python

   response = await device.async_send_command(
       serviceType="cloud.smarthq.service.dishwasher.state.v1",
       domainType="cloud.smarthq.domain.dishwasher",
       serviceDeviceType="cloud.smarthq.device.dishwasher",
       command={"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"},
   )
   print(response.correlationId, response.outcome)

:meth:`~pysmarthq.models.Service.async_send_command` uses the type fields already stored on the service:

.. code-block:: python

   await service.async_send_command(
       {"commandType": "cloud.smarthq.command.dishwasher.state.v1.start"}
   )

``POST /v2/command`` returns HTTP 200 for a processed command, including one whose ``success`` field is false. :meth:`~pysmarthq.models.Device.async_send_command` and :meth:`~pysmarthq.models.Service.async_send_command` call :meth:`~pysmarthq.models.CommandResponse.raise_for_outcome`, which raises :class:`~pysmarthq.errors.SmartHQApiError` when ``success`` is false. The outcome string, including ``cloud.smarthq.outcome.timeout``, is part of the message.

:meth:`~pysmarthq.api.SmartHQApi.async_send_command` posts the body you pass and returns the :class:`~pysmarthq.models.CommandResponse` with ``success`` left for the caller to read.

A later ``pubsub#command`` event can still carry the device outcome. Set ``commands=True`` on the account configuration to receive it. See :doc:`events`.

Batch commands
--------------

:meth:`~pysmarthq.api.SmartHQApi.async_send_commands` posts ``POST /v2/commands``. The body is a ``SendCommandsRequest``. The spec example uses ``kind`` ``service#commands`` (plural). Required keys are ``kind``, ``serviceType``, ``domainType``, ``serviceDeviceType``, and ``command``. ``command`` must include ``commandType``. A missing key raises :class:`~pysmarthq.errors.SmartHQError` before the request is sent.

Device selection is the query string. At least one filter from :data:`~pysmarthq.const.DEVICE_QUERY_FILTERS` is required. With none set, the call would match every device that has the service, so the client refuses it.

.. code-block:: python

   result = await api.async_send_commands(
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
   print(result.total, result.correlationId)

History and outcomes
--------------------

These methods return one page. Follow ``page`` yourself when ``total`` is larger than the page.

* :meth:`~pysmarthq.api.SmartHQApi.async_get_command` calls ``GET /v2/command/{correlationId}``.
* :meth:`~pysmarthq.api.SmartHQApi.async_get_command_summary` calls ``GET /v2/command/{correlationId}/summary``.
* :meth:`~pysmarthq.api.SmartHQApi.async_get_command_history` calls ``GET /v2/command``.
* :meth:`~pysmarthq.api.SmartHQApi.async_get_batch_command_history` calls ``GET /v2/commands``.

Summary counts are ``success``, ``failed``, ``timeout``, and ``unknown`` on :class:`~pysmarthq.models.CommandOutcomeSummaryResponse`. Per-device rows are :class:`~pysmarthq.models.CommandRecord` objects. Command dictionaries on those records are returned unchanged.
