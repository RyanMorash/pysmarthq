"""Digital Twin data models.

Property names match the OpenAPI schema fields. Values are returned as the API
sent them. ``raw_data`` keeps the full payload, including fields that do not
have a property.
"""

from __future__ import annotations

from typing import Any

from .auth import AbstractAuth
from ._http import api_path, async_api
from .errors import SmartHQError


class ApiModel:
    """Object built from one JSON object."""

    def __init__(self, raw_data: dict[str, Any], auth: AbstractAuth) -> None:
        self.raw_data = raw_data
        self.auth = auth

    def _value(self, key: str) -> Any:
        return self.raw_data.get(key)


class Device(ApiModel):
    """A device from ``Device`` or ``DeviceResponse``."""

    @property
    def deviceId(self) -> str | None:
        """Unique device id."""
        return self._value("deviceId")

    @property
    def deviceType(self) -> str | None:
        """Device type, such as ``cloud.smarthq.device.dryer``."""
        return self._value("deviceType")

    @property
    def nickname(self) -> str | None:
        """User-facing name."""
        return self._value("nickname")

    @property
    def adapterId(self) -> str | None:
        """Adapter id."""
        return self._value("adapterId")

    @property
    def gatewayId(self) -> str | None:
        """Gateway id."""
        return self._value("gatewayId")

    @property
    def presence(self) -> str | None:
        """Presence string from the payload, such as ``ONLINE``."""
        return self._value("presence")

    @property
    def lastPresenceTime(self) -> str | None:
        """Last presence timestamp."""
        return self._value("lastPresenceTime")

    @property
    def lastSyncTime(self) -> str | None:
        """Last sync timestamp."""
        return self._value("lastSyncTime")

    @property
    def createdDateTime(self) -> str | None:
        """Creation timestamp."""
        return self._value("createdDateTime")

    @property
    def icon(self) -> str | None:
        """Icon identifier."""
        return self._value("icon")

    @property
    def manufacturer(self) -> str | None:
        """Manufacturer."""
        return self._value("manufacturer")

    @property
    def model(self) -> str | None:
        """Model."""
        return self._value("model")

    @property
    def macAddress(self) -> str | None:
        """MAC address."""
        return self._value("macAddress")

    @property
    def room(self) -> str | None:
        """Room."""
        return self._value("room")

    @property
    def roomNumber(self) -> str | None:
        """Room number."""
        return self._value("roomNumber")

    @property
    def building(self) -> str | None:
        """Building."""
        return self._value("building")

    @property
    def floor(self) -> str | None:
        """Floor."""
        return self._value("floor")

    @property
    def unit(self) -> str | None:
        """Unit."""
        return self._value("unit")

    @property
    def brand(self) -> str | None:
        """Brand."""
        return self._value("brand")

    @property
    def serial(self) -> str | None:
        """Serial number."""
        return self._value("serial")

    @property
    def version(self) -> str | None:
        """Version."""
        return self._value("version")

    @property
    def location(self) -> str | None:
        """Location."""
        return self._value("location")

    @property
    def removable(self) -> bool | None:
        """Whether the device can be removed."""
        return self._value("removable")

    @property
    def kind(self) -> str | None:
        """Resource kind, such as ``device#item``."""
        return self._value("kind")

    @property
    def alertTypes(self) -> list[str] | None:
        """Alert types this device can emit. Absent on the list payload."""
        return self._value("alertTypes")

    @property
    def services(self) -> list[Service] | None:
        """Services on a device detail. ``None`` when the payload has no ``services``."""
        if "services" not in self.raw_data:
            return None
        return [
            Service(item, self.auth, deviceId=self.deviceId)
            for item in self.raw_data.get("services") or []
        ]

    async def async_update(self) -> None:
        """Replace this device with ``GET /v2/device/{deviceId}``."""
        self.raw_data = await async_api(self.auth, "GET", _device_path(self._require_device_id()))

    async def async_remove(self) -> None:
        """Remove the device with ``DELETE /v2/device/{deviceId}``."""
        await async_api(
            self.auth,
            "DELETE",
            _device_path(self._require_device_id()),
            ok=(204,),
        )

    async def async_get_service(self, service_id: str) -> Service:
        """Return ``GET /v2/device/{deviceId}/service/{serviceId}``."""
        device_id = self._require_device_id()
        data = await async_api(
            self.auth,
            "GET",
            _device_path(device_id, "service", service_id),
        )
        return Service(data, self.auth, deviceId=device_id)

    async def async_get_presence(self) -> DevicePresenceResponse:
        """Return ``GET /v2/device/{deviceId}/presence``."""
        data = await async_api(
            self.auth,
            "GET",
            _device_path(self._require_device_id(), "presence"),
        )
        return DevicePresenceResponse(data, self.auth)

    async def async_get_settings(self) -> DeviceSettingResponse:
        """Return ``GET /v2/device/{deviceId}/setting``."""
        data = await async_api(
            self.auth,
            "GET",
            _device_path(self._require_device_id(), "setting"),
        )
        return DeviceSettingResponse(data, self.auth)

    async def async_get_setting(self, rule_id: str) -> DeviceSetting:
        """Return ``GET /v2/device/{deviceId}/setting/{ruleId}``."""
        data = await async_api(
            self.auth,
            "GET",
            _device_path(self._require_device_id(), "setting", rule_id),
        )
        return DeviceSetting(data, self.auth)

    async def async_get_alerts(self, *, params: dict[str, Any] | None = None) -> DeviceAlertsResponse:
        """Return ``GET /v2/device/{deviceId}/alert``.

        ``params`` uses the query names from the spec: ``status``, ``fault``,
        ``clear``, and ``onlyTriggered``.
        """
        data = await async_api(
            self.auth,
            "GET",
            _device_path(self._require_device_id(), "alert"),
            params=params,
        )
        return DeviceAlertsResponse(data, self.auth)

    async def async_send_command(
        self,
        *,
        serviceType: str,
        domainType: str,
        serviceDeviceType: str,
        command: dict[str, Any],
    ) -> CommandResponse:
        """Send ``POST /v2/command`` for this device.

        The body is the ``service#command`` envelope required by ``CommandRequest``:
        ``kind``, ``deviceId``, ``serviceType``, ``domainType``, ``serviceDeviceType``,
        and ``command``. ``command`` must include ``commandType``. Other command
        fields are sent unchanged.
        """
        body = _command_body(
            deviceId=self._require_device_id(),
            serviceType=serviceType,
            domainType=domainType,
            serviceDeviceType=serviceDeviceType,
            command=command,
        )
        data = await async_api(self.auth, "POST", "v2/command", json_body=body)
        return CommandResponse(data, self.auth)

    async def async_get_pubsub(self) -> PubsubConfig:
        """Return ``GET /v2/device/{deviceId}/pubsub``."""
        data = await async_api(self.auth, "GET", _device_path(self._require_device_id(), "pubsub"))
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
        """Set HTTPS/SNS preferences with ``POST /v2/device/{deviceId}/pubsub``.

        ``kind`` is ``device#pubsub``. ``pubsub`` is required by
        ``DevicePubsubConfigRequest``. Omitted booleans are left out so the
        service can apply the documented defaults.
        """
        body = _pubsub_body(
            "device#pubsub",
            pubsub=pubsub,
            services=services,
            presence=presence,
            alerts=alerts,
            commands=commands,
        )
        data = await async_api(
            self.auth,
            "POST",
            _device_path(self._require_device_id(), "pubsub"),
            json_body=body,
        )
        return PubsubConfig(data, self.auth)

    async def async_delete_pubsub(self) -> None:
        """Remove device pubsub with ``DELETE /v2/device/{deviceId}/pubsub``."""
        await async_api(
            self.auth,
            "DELETE",
            _device_path(self._require_device_id(), "pubsub"),
            ok=(204,),
        )

    def _require_device_id(self) -> str:
        device_id = self.deviceId
        if not device_id:
            raise SmartHQError("Device payload did not include deviceId")
        return device_id

    def __repr__(self) -> str:
        return f"Device(deviceId={self.deviceId!r}, deviceType={self.deviceType!r})"


class DeviceListResponse(ApiModel):
    """``GET /v2/device`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def page(self) -> int | None:
        """Page number."""
        return self._value("page")

    @property
    def perpage(self) -> int | None:
        """Page size."""
        return self._value("perpage")

    @property
    def total(self) -> int | None:
        """Total device count reported with the page."""
        return self._value("total")

    @property
    def userId(self) -> str | None:
        """User id, when the response includes one."""
        return self._value("userId")

    @property
    def devices(self) -> list[Device]:
        """Devices on this page."""
        return [Device(item, self.auth) for item in self.raw_data.get("devices") or []]

    def __iter__(self):
        return iter(self.devices)


class DeviceCountResponse(ApiModel):
    """``GET /v2/device/count`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def userId(self) -> str | None:
        """User id."""
        return self._value("userId")

    @property
    def devices(self) -> list[dict[str, Any]]:
        """``deviceType`` and ``count`` pairs, as returned."""
        return list(self.raw_data.get("devices") or [])


class Service(ApiModel):
    """A service from ``DeviceService`` or ``ServiceDetailsResponse``."""

    def __init__(
        self,
        raw_data: dict[str, Any],
        auth: AbstractAuth,
        *,
        deviceId: str | None = None,
    ) -> None:
        super().__init__(raw_data, auth)
        self._deviceId = deviceId or raw_data.get("deviceId")

    @property
    def serviceId(self) -> str | None:
        """Service id."""
        return self._value("serviceId")

    @property
    def serviceType(self) -> str | None:
        """Service type."""
        return self._value("serviceType")

    @property
    def domainType(self) -> str | None:
        """Domain type."""
        return self._value("domainType")

    @property
    def serviceDeviceType(self) -> str | None:
        """Device type of the service."""
        return self._value("serviceDeviceType")

    @property
    def deviceId(self) -> str | None:
        """Device id when the payload or parent device has one."""
        return self._deviceId

    @property
    def kind(self) -> str | None:
        """Resource kind on a service detail."""
        return self._value("kind")

    @property
    def supportedCommands(self) -> list[str] | None:
        """Command types this service accepts."""
        return self._value("supportedCommands")

    @property
    def state(self) -> dict[str, Any] | None:
        """Service state object, unchanged."""
        return self._value("state")

    @property
    def config(self) -> dict[str, Any] | None:
        """Service config object, unchanged."""
        return self._value("config")

    @property
    def lastSyncTime(self) -> str | None:
        """Last sync timestamp."""
        return self._value("lastSyncTime")

    @property
    def lastStateTime(self) -> str | None:
        """Last state timestamp."""
        return self._value("lastStateTime")

    async def async_update(self) -> None:
        """Replace this service with ``GET /v2/device/{deviceId}/service/{serviceId}``."""
        data = await async_api(self.auth, "GET", self._detail_path())
        device_id = self._deviceId
        self.raw_data = data
        self._deviceId = device_id or data.get("deviceId")

    async def async_send_command(self, command: dict[str, Any]) -> CommandResponse:
        """Send ``POST /v2/command`` using this service's type fields."""
        device_id = self.deviceId
        service_type = self.serviceType
        domain_type = self.domainType
        service_device_type = self.serviceDeviceType
        if not device_id or not service_type or not domain_type or not service_device_type:
            raise SmartHQError(
                "Service payload needs deviceId, serviceType, domainType, and serviceDeviceType"
            )
        body = _command_body(
            deviceId=device_id,
            serviceType=service_type,
            domainType=domain_type,
            serviceDeviceType=service_device_type,
            command=command,
        )
        data = await async_api(self.auth, "POST", "v2/command", json_body=body)
        return CommandResponse(data, self.auth)

    def _detail_path(self) -> str:
        device_id = self.deviceId
        service_id = self.serviceId
        if not device_id or not service_id:
            raise SmartHQError("Service payload needs deviceId and serviceId")
        return _device_path(device_id, "service", service_id)

    def __repr__(self) -> str:
        return f"Service(serviceId={self.serviceId!r}, serviceType={self.serviceType!r})"


class DevicePresenceResponse(ApiModel):
    """``GET /v2/device/{deviceId}/presence`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self._value("deviceId")

    @property
    def presence(self) -> str | None:
        """Current presence, ``ONLINE`` or ``OFFLINE``."""
        return self._value("presence")

    @property
    def history(self) -> list[dict[str, Any]]:
        """Presence history entries."""
        return list(self.raw_data.get("history") or [])


class DeviceSetting(ApiModel):
    """One device setting."""

    @property
    def ruleId(self) -> str | None:
        """Rule id."""
        return self._value("ruleId")

    @property
    def title(self) -> str | None:
        """Setting title."""
        return self._value("title")

    @property
    def description(self) -> str | None:
        """Setting description."""
        return self._value("description")

    @property
    def ruleEnabled(self) -> bool | None:
        """Whether the rule is enabled."""
        return self._value("ruleEnabled")

    @property
    def kind(self) -> str | None:
        """Resource kind on a single setting."""
        return self._value("kind")


class DeviceSettingResponse(ApiModel):
    """``GET /v2/device/{deviceId}/setting`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def settings(self) -> list[DeviceSetting]:
        """Settings on the device."""
        return [DeviceSetting(item, self.auth) for item in self.raw_data.get("settings") or []]


class AlertInfo(ApiModel):
    """One alert from ``AlertInfo``."""

    @property
    def alertType(self) -> str | None:
        """Alert type."""
        return self._value("alertType")

    @property
    def alertId(self) -> str | None:
        """Alert id for a triggered alert."""
        return self._value("alertId")

    @property
    def lastAlertTime(self) -> str | None:
        """Last trigger time."""
        return self._value("lastAlertTime")

    @property
    def lastClearTime(self) -> str | None:
        """Last clear time."""
        return self._value("lastClearTime")

    @property
    def clear(self) -> str | None:
        """Clear flag as returned by the API."""
        return self._value("clear")


class DeviceAlertsResponse(ApiModel):
    """``GET /v2/device/{deviceId}/alert`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self._value("deviceId")

    @property
    def totalTriggeredAlerts(self) -> int | None:
        """Triggered alert count."""
        return self._value("totalTriggeredAlerts")

    @property
    def totalTriggeredFaults(self) -> int | None:
        """Triggered fault count."""
        return self._value("totalTriggeredFaults")

    @property
    def alerts(self) -> list[AlertInfo]:
        """Alerts on the device."""
        return [AlertInfo(item, self.auth) for item in self.raw_data.get("alerts") or []]


class CommandResponse(ApiModel):
    """``POST /v2/command`` response."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def success(self) -> bool | None:
        """Whether the command was accepted."""
        return self._value("success")

    @property
    def correlationId(self) -> str | None:
        """Correlation id for the command."""
        return self._value("correlationId")

    @property
    def outcome(self) -> str | None:
        """Outcome string."""
        return self._value("outcome")

    @property
    def services(self) -> list[str] | None:
        """Service ids included on the response."""
        return self._value("services")


class SendCommandsSuccessResponse(ApiModel):
    """``POST /v2/commands`` success response."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def total(self) -> int | None:
        """Number of devices the command was sent to."""
        return self._value("total")

    @property
    def correlationId(self) -> str | None:
        """Correlation id for the batch."""
        return self._value("correlationId")


class CommandRecord(ApiModel):
    """One command history object."""

    @property
    def serviceType(self) -> str | None:
        """Service type."""
        return self._value("serviceType")

    @property
    def domainType(self) -> str | None:
        """Domain type."""
        return self._value("domainType")

    @property
    def serviceDeviceType(self) -> str | None:
        """Service device type."""
        return self._value("serviceDeviceType")

    @property
    def serviceId(self) -> str | None:
        """Service id."""
        return self._value("serviceId")

    @property
    def deviceId(self) -> str | None:
        """Device id."""
        return self._value("deviceId")

    @property
    def deviceType(self) -> str | None:
        """Device type."""
        return self._value("deviceType")

    @property
    def appId(self) -> str | None:
        """Application id."""
        return self._value("appId")

    @property
    def correlationId(self) -> str | None:
        """Correlation id."""
        return self._value("correlationId")

    @property
    def command(self) -> dict[str, Any] | None:
        """Command object, unchanged."""
        return self._value("command")

    @property
    def commandDateTime(self) -> str | None:
        """Command timestamp."""
        return self._value("commandDateTime")

    @property
    def outcome(self) -> str | None:
        """Outcome string."""
        return self._value("outcome")

    @property
    def outcomeDateTime(self) -> str | None:
        """Outcome timestamp."""
        return self._value("outcomeDateTime")


class _PagedCommands(ApiModel):
    def __init__(self, raw_data: dict[str, Any], auth: AbstractAuth, *, item_key: str) -> None:
        super().__init__(raw_data, auth)
        self._item_key = item_key

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def page(self) -> int | None:
        """Page number."""
        return self._value("page")

    @property
    def perpage(self) -> int | None:
        """Page size."""
        return self._value("perpage")

    @property
    def total(self) -> int | None:
        """Total matching the query."""
        return self._value("total")

    @property
    def correlationId(self) -> str | None:
        """Correlation id, on a single-command outcome page."""
        return self._value("correlationId")

    @property
    def command(self) -> dict[str, Any] | None:
        """Command object on a single-command outcome page."""
        return self._value("command")

    @property
    def items(self) -> list[CommandRecord]:
        """Command or outcome records on this page."""
        return [CommandRecord(item, self.auth) for item in self.raw_data.get(self._item_key) or []]


class GetCommandOutcomeResponse(_PagedCommands):
    """``GET /v2/command/{correlationId}`` payload."""

    def __init__(self, raw_data: dict[str, Any], auth: AbstractAuth) -> None:
        super().__init__(raw_data, auth, item_key="outcomes")

    @property
    def outcomes(self) -> list[CommandRecord]:
        """Outcomes on this page."""
        return self.items


class AccountCommandHistoryResponse(_PagedCommands):
    """``GET /v2/command`` payload."""

    def __init__(self, raw_data: dict[str, Any], auth: AbstractAuth) -> None:
        super().__init__(raw_data, auth, item_key="commands")

    @property
    def commands(self) -> list[CommandRecord]:
        """Commands on this page."""
        return self.items


class BatchCommandHistoryResponse(_PagedCommands):
    """``GET /v2/commands`` payload."""

    def __init__(self, raw_data: dict[str, Any], auth: AbstractAuth) -> None:
        super().__init__(raw_data, auth, item_key="commands")

    @property
    def commands(self) -> list[CommandRecord]:
        """Batch commands on this page."""
        return self.items


class CommandOutcomeSummaryResponse(ApiModel):
    """``GET /v2/command/{correlationId}/summary`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def correlationId(self) -> str | None:
        """Correlation id."""
        return self._value("correlationId")

    @property
    def serviceType(self) -> str | None:
        """Service type."""
        return self._value("serviceType")

    @property
    def domainType(self) -> str | None:
        """Domain type."""
        return self._value("domainType")

    @property
    def serviceDeviceType(self) -> str | None:
        """Service device type."""
        return self._value("serviceDeviceType")

    @property
    def command(self) -> dict[str, Any] | None:
        """Command object."""
        return self._value("command")

    @property
    def commandDateTime(self) -> str | None:
        """Command timestamp."""
        return self._value("commandDateTime")

    @property
    def total(self) -> int | None:
        """Total outcomes."""
        return self._value("total")

    @property
    def success(self) -> int | None:
        """Successful outcome count."""
        return self._value("success")

    @property
    def failed(self) -> int | None:
        """Failed outcome count."""
        return self._value("failed")

    @property
    def timeout(self) -> int | None:
        """Timed-out outcome count."""
        return self._value("timeout")

    @property
    def unknown(self) -> int | None:
        """Unknown outcome count."""
        return self._value("unknown")

    @property
    def outcomes(self) -> list[dict[str, Any]]:
        """Outcome counts as returned."""
        return list(self.raw_data.get("outcomes") or [])


class PubsubConfig(ApiModel):
    """Account or device pubsub configuration."""

    @property
    def kind(self) -> str | None:
        """``user#pubsub`` or ``device#pubsub``."""
        return self._value("kind")

    @property
    def pubsub(self) -> bool | None:
        """Whether account or device pubsub is enabled."""
        return self._value("pubsub")

    @property
    def services(self) -> bool | None:
        """Whether service events are enabled."""
        return self._value("services")

    @property
    def presence(self) -> bool | None:
        """Whether presence events are enabled."""
        return self._value("presence")

    @property
    def alerts(self) -> bool | None:
        """Whether alert events are enabled."""
        return self._value("alerts")

    @property
    def commands(self) -> bool | None:
        """Whether command outcomes are enabled."""
        return self._value("commands")

    @property
    def success(self) -> bool | None:
        """Whether a configuration write was accepted."""
        return self._value("success")


class WebsocketEndpoint(ApiModel):
    """``GET /v2/websocket`` payload."""

    @property
    def kind(self) -> str | None:
        """Resource kind."""
        return self._value("kind")

    @property
    def endpoint(self) -> str | None:
        """WebSocket URL. The access token is already part of this URL."""
        return self._value("endpoint")


def _device_path(device_id: str, *rest: str) -> str:
    return api_path("v2", "device", device_id, *rest)


def _command_body(
    *,
    deviceId: str,
    serviceType: str,
    domainType: str,
    serviceDeviceType: str,
    command: dict[str, Any],
) -> dict[str, Any]:
    if "commandType" not in command:
        raise SmartHQError("command requires commandType")
    return {
        "kind": "service#command",
        "deviceId": deviceId,
        "serviceType": serviceType,
        "domainType": domainType,
        "serviceDeviceType": serviceDeviceType,
        "command": dict(command),
    }


def _pubsub_body(
    kind: str,
    *,
    pubsub: bool,
    services: bool | None,
    presence: bool | None,
    alerts: bool | None,
    commands: bool | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"kind": kind, "pubsub": pubsub}
    if services is not None:
        body["services"] = services
    if presence is not None:
        body["presence"] = presence
    if alerts is not None:
        body["alerts"] = alerts
    if commands is not None:
        body["commands"] = commands
    return body
