Devices
=======

:class:`~pysmarthq.api.SmartHQApi` is the Digital Twin entry point. Construct it with the :class:`~pysmarthq.auth.AbstractAuth` for the user.

.. code-block:: python

   api = SmartHQApi(auth)
   page = await api.async_get_devices()
   for device in page:
       print(device.deviceId, device.deviceType, device.nickname)

:meth:`~pysmarthq.api.SmartHQApi.async_get_devices` returns one page as a :class:`~pysmarthq.models.DeviceListResponse`. Iterating the response yields the :class:`~pysmarthq.models.Device` objects on that page. ``params`` uses the query names from the spec, including ``page``, ``perpage``, ``sort``, and ``order``. ``nickname`` is a sort key, and it is absent from the device filters.

:meth:`~pysmarthq.api.SmartHQApi.async_get_device_count` calls ``GET /v2/device/count`` and returns ``deviceType`` and ``count`` pairs.

List pages and device detail
----------------------------

List payloads omit services. Load ``GET /v2/device/{deviceId}`` before creating entities or reading :attr:`~pysmarthq.models.Device.services`.

.. code-block:: python

   device = await api.async_get_device(device_id)
   await device.async_update()

:meth:`~pysmarthq.models.Device.async_update` replaces ``raw_data`` on the same object. :meth:`~pysmarthq.api.SmartHQApi.async_get_device` returns a new :class:`~pysmarthq.models.Device`.

Every model keeps the JSON object on ``raw_data``, including fields that have no property. Property names match the OpenAPI schema. Values are returned as the API sent them. ``auth`` on the model is the object used for follow-up calls.

Every device
------------

:meth:`~pysmarthq.api.SmartHQApi.async_get_all_devices` asks for :data:`~pysmarthq.const.DEVICE_LIST_PAGE_SIZE` (100) devices per page. It follows ``page`` until any of these is true:

* ``page * perpage`` covers ``total``
* a page comes back shorter than the page size
* every device on a page has an id already collected
* the page is empty

The page number sent on the next request is one more than the number of requests made. The ``page`` field in the response is used for the ``total`` check, and the next request keeps the client's own counter. Other query parameters, including device filters, are sent on every page. ``page`` and ``perpage`` in ``params`` are replaced.

More than :data:`~pysmarthq.const.DEVICE_LIST_MAX_PAGES` (100) requests raises :class:`~pysmarthq.errors.SmartHQError`.

Services
--------

:attr:`~pysmarthq.models.Device.services` is ``None`` when the payload has no ``services`` key. The :class:`~pysmarthq.models.Service` objects are cached. :meth:`~pysmarthq.models.Service.async_update` writes the new detail back into ``raw_data["services"]`` and into that cache.

:meth:`~pysmarthq.models.Device.find_service` matches ``serviceType`` plus optional ``domainType`` and ``serviceDeviceType``. Several services share a service type, including temperature domains and more than one toggle. When zero services match, or more than one matches the keys that were passed, the method returns ``None``.

.. code-block:: python

   cycle = device.find_service(
       "cloud.smarthq.service.dishwasher.state.v1",
       domainType="cloud.smarthq.domain.dishwasher",
       serviceDeviceType="cloud.smarthq.device.dishwasher",
   )

:meth:`~pysmarthq.models.Device.async_get_service` calls ``GET /v2/device/{deviceId}/service/{serviceId}``.

Presence, settings, and alerts
------------------------------

* :meth:`~pysmarthq.models.Device.async_get_presence` calls ``GET /v2/device/{deviceId}/presence``.
* :meth:`~pysmarthq.models.Device.async_get_settings` and :meth:`~pysmarthq.models.Device.async_get_setting` call the device setting routes.
* :meth:`~pysmarthq.models.Device.async_get_alerts` calls ``GET /v2/device/{deviceId}/alert``. ``params`` uses ``status``, ``fault``, ``clear``, and ``onlyTriggered``.

:meth:`~pysmarthq.models.Device.async_remove` calls ``DELETE /v2/device/{deviceId}``. :attr:`~pysmarthq.models.Device.removable` reports whether the payload says the device can be removed.

Account and device HTTPS/SNS preferences are documented with the :doc:`event stream <events>`.
