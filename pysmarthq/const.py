"""Hosts and limits taken from the SmartHQ specifications and docs."""

IAM_HOST = "https://accounts.brillion.geappliances.com"
"""Identity and Access Management OpenAPI server."""

DIGITAL_TWIN_HOST = "https://client.mysmarthq.com"
"""Digital Twin OpenAPI server."""

ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS = 60
"""Refresh an access token this many seconds before ``expires_at``.

A call that starts in the last moments of the token, or a host clock slightly
ahead of SmartHQ, would otherwise send a bearer token the server already
rejects. A token with exactly this many seconds left is still current.
"""

REQUEST_TIMEOUT_SECONDS = 30
"""Bound one token or Digital Twin call when the caller's aiohttp session has no total timeout.

Pass another ``ClientTimeout`` to override.
"""

DEVICE_LIST_PAGE_SIZE = 100
"""``GET /v2/device`` allows at most this many rows per page."""

DEVICE_LIST_MAX_PAGES = 100
"""Stop ``async_get_all_devices`` after this many pages.

A huge ``total`` cannot be followed forever. 100 pages is 10,000 devices.
"""

DEVICE_QUERY_FILTERS = (
    "deviceId",
    "deviceType",
    "adapterId",
    "gatewayId",
    "model",
    "serial",
    "version",
    "manufacturer",
    "brand",
    "macAddress",
    "updId",
    "room",
    "roomNumber",
    "unit",
    "floor",
    "building",
    "location",
    "personality",
)
"""Query filters shared by ``GET /v2/device`` and ``POST /v2/commands``."""

WEBSOCKET_IDLE_PING_SECONDS = 60
"""Quiet period before a ``websocket#ping``.

The real-time updates guide closes idle sockets after 10 minutes and suggests
a ping after 60 seconds without other traffic.
"""

WEBSOCKET_INBOUND_GRACE_INTERVALS = 2
"""Close the socket when no inbound frame arrives for this many ping intervals.

A sent ping only proves that the write was accepted.
"""

WEBSOCKET_MAX_PAYLOAD_BYTES = 32 * 1024
"""Individual JSON payloads are limited to 32 KB."""

EVENT_QUEUE_MAX_EVENTS = 1024
"""Events waiting for ``async_receive``.

One extra slot is reserved so the terminal error can still be queued when this
limit is reached. Protocol PING and PONG frames do not use a slot.
"""
