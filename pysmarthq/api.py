"""Entry points for the SmartHQ Digital Twin API."""

from __future__ import annotations

from typing import Any

from .auth import AbstractAuth
from ._http import api_path, async_api
from .const import DEVICE_LIST_MAX_PAGES, DEVICE_LIST_PAGE_SIZE, DEVICE_QUERY_FILTERS
from .models import (
    AccountCommandHistoryResponse,
    BatchCommandHistoryResponse,
    CommandOutcomeSummaryResponse,
    CommandResponse,
    Device,
    DeviceCountResponse,
    DeviceListResponse,
    GetCommandOutcomeResponse,
    PubsubConfig,
    SendCommandsSuccessResponse,
    WebsocketEndpoint,
    _pubsub_body,
)
from .errors import SmartHQError


class SmartHQApi:
    """Call the Digital Twin API for the user represented by ``auth``."""

    def __init__(self, auth: AbstractAuth) -> None:
        """Initialize the API and store the auth so we can make requests."""
        self.auth = auth

    async def async_get_devices(self, *, params: dict[str, Any] | None = None) -> DeviceListResponse:
        """Return ``GET /v2/device``.

        ``params`` uses the query names from the spec, including ``page``,
        ``perpage``, ``sort``, ``order``, and the device filters (``deviceType``,
        ``nickname`` is not a filter; ``sort`` may be ``nickname``).
        """
        data = await async_api(self.auth, "GET", "v2/device", params=params)
        return DeviceListResponse(data, self.auth)

    async def async_get_all_devices(self, *, params: dict[str, Any] | None = None) -> list[Device]:
        """Return every device from ``GET /v2/device``.

        Requests ``perpage`` of 100 and follows ``page`` until ``page * perpage``
        reaches ``total``, a short page comes back, or a page repeats device
        ids already collected. ``async_get_devices`` still returns one page.
        More than ``DEVICE_LIST_MAX_PAGES`` pages raises ``SmartHQError``.
        Other query parameters, including device filters, are sent on every page.
        """
        filters = {
            key: value
            for key, value in (params or {}).items()
            if key not in ("page", "perpage") and value is not None
        }
        page = 1
        devices: list[Device] = []
        seen: set[str] = set()
        while True:
            if page > DEVICE_LIST_MAX_PAGES:
                raise SmartHQError(f"Device list exceeded {DEVICE_LIST_MAX_PAGES} pages")
            listed = await self.async_get_devices(
                params={**filters, "page": page, "perpage": DEVICE_LIST_PAGE_SIZE}
            )
            batch = listed.devices
            ids = [device.deviceId for device in batch if device.deviceId]
            if ids and all(device_id in seen for device_id in ids):
                return devices
            seen.update(ids)
            devices.extend(batch)
            size = listed.perpage if isinstance(listed.perpage, int) and listed.perpage > 0 else DEVICE_LIST_PAGE_SIZE
            current = listed.page if isinstance(listed.page, int) and listed.page > 0 else page
            total = listed.total
            if (
                not batch
                or len(batch) < size
                or (isinstance(total, int) and not isinstance(total, bool) and current * size >= total)
            ):
                return devices
            page = current + 1

    async def async_get_device(self, device_id: str) -> Device:
        """Return ``GET /v2/device/{deviceId}``, including services."""
        data = await async_api(self.auth, "GET", api_path("v2", "device", device_id))
        return Device(data, self.auth)

    async def async_get_device_count(self) -> DeviceCountResponse:
        """Return ``GET /v2/device/count``."""
        data = await async_api(self.auth, "GET", "v2/device/count")
        return DeviceCountResponse(data, self.auth)

    async def async_send_command(self, body: dict[str, Any]) -> CommandResponse:
        """Send ``POST /v2/command`` with a ``CommandRequest`` body.

        The body is sent as given so service-specific command fields are not
        rewritten. ``Device.async_send_command`` builds the common envelope.
        """
        data = await async_api(self.auth, "POST", "v2/command", json_body=dict(body))
        return CommandResponse(data, self.auth)

    async def async_send_commands(
        self,
        body: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
    ) -> SendCommandsSuccessResponse:
        """Send ``POST /v2/commands``.

        ``SendCommandsRequest`` requires ``kind``, ``serviceType``, ``domainType``,
        ``serviceDeviceType``, and ``command``. Device selection is the query
        string. At least one spec filter (``deviceId``, ``deviceType``, and the
        other ``GET /v2/device`` filters) is required so an empty filter set
        cannot match every device that has the service.
        """
        _require_batch_command(body)
        filters = _batch_filters(params)
        data = await async_api(self.auth, "POST", "v2/commands", params=filters, json_body=dict(body))
        return SendCommandsSuccessResponse(data, self.auth)

    async def async_get_command(
        self,
        correlation_id: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> GetCommandOutcomeResponse:
        """Return ``GET /v2/command/{correlationId}``."""
        data = await async_api(
            self.auth,
            "GET",
            api_path("v2", "command", correlation_id),
            params=params,
        )
        return GetCommandOutcomeResponse(data, self.auth)

    async def async_get_command_summary(self, correlation_id: str) -> CommandOutcomeSummaryResponse:
        """Return ``GET /v2/command/{correlationId}/summary``."""
        data = await async_api(
            self.auth,
            "GET",
            api_path("v2", "command", correlation_id, "summary"),
        )
        return CommandOutcomeSummaryResponse(data, self.auth)

    async def async_get_command_history(
        self,
        *,
        params: dict[str, Any] | None = None,
    ) -> AccountCommandHistoryResponse:
        """Return ``GET /v2/command``."""
        data = await async_api(self.auth, "GET", "v2/command", params=params)
        return AccountCommandHistoryResponse(data, self.auth)

    async def async_get_batch_command_history(
        self,
        *,
        params: dict[str, Any] | None = None,
    ) -> BatchCommandHistoryResponse:
        """Return ``GET /v2/commands``."""
        data = await async_api(self.auth, "GET", "v2/commands", params=params)
        return BatchCommandHistoryResponse(data, self.auth)

    async def async_get_pubsub(self) -> PubsubConfig:
        """Return ``GET /v2/pubsub``."""
        data = await async_api(self.auth, "GET", "v2/pubsub")
        return PubsubConfig(data, self.auth)

    async def async_set_pubsub(
        self,
        *,
        pubsub: bool,
        services: bool | None = None,
        presence: bool | None = None,
        alerts: bool | None = None,
        commands: bool | None = None,
    ) -> PubsubConfig:
        """Set account HTTPS/SNS preferences with ``POST /v2/pubsub``.

        ``kind`` is ``user#pubsub``. These preferences do not change WebSocket
        event configuration.
        """
        body = _pubsub_body(
            "user#pubsub",
            pubsub=pubsub,
            services=services,
            presence=presence,
            alerts=alerts,
            commands=commands,
        )
        data = await async_api(self.auth, "POST", "v2/pubsub", json_body=body)
        return PubsubConfig(data, self.auth)

    async def async_delete_pubsub(self) -> None:
        """Disable account pubsub with ``DELETE /v2/pubsub``."""
        await async_api(self.auth, "DELETE", "v2/pubsub", ok=(204,), expect_object=False)

    async def async_get_websocket_endpoint(self) -> WebsocketEndpoint:
        """Return ``GET /v2/websocket``.

        The URL is per user and changes. Fetch it again for each connection.
        """
        data = await async_api(self.auth, "GET", "v2/websocket")
        return WebsocketEndpoint(data, self.auth)


def _require_batch_command(body: dict[str, Any]) -> None:
    required = ("kind", "serviceType", "domainType", "serviceDeviceType", "command")
    missing = [key for key in required if key not in body]
    if missing:
        raise SmartHQError(f"Batch command requires {', '.join(missing)}")
    command = body.get("command")
    if not isinstance(command, dict) or "commandType" not in command:
        raise SmartHQError("Batch command.command requires commandType")


def _batch_filters(params: dict[str, Any] | None) -> dict[str, Any]:
    filters = {
        key: value
        for key, value in (params or {}).items()
        if key in DEVICE_QUERY_FILTERS and value is not None
    }
    if not filters:
        names = ", ".join(DEVICE_QUERY_FILTERS)
        raise SmartHQError(f"Batch command requires at least one device filter: {names}")
    return filters
