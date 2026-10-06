"""Hosts and limits taken from the SmartHQ specifications and docs."""

# Identity and Access Management OpenAPI server.
IAM_HOST = "https://accounts.brillion.geappliances.com"

# Digital Twin OpenAPI server.
DIGITAL_TWIN_HOST = "https://client.mysmarthq.com"

# Refresh an access token this many seconds before ``expires_at``. A call that
# starts in the last moments of the token, or a host clock slightly ahead of
# SmartHQ, would otherwise send a bearer token the server already rejects.
ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS = 60

# Bound one token or Digital Twin call when the caller's aiohttp session has
# no total timeout. Pass another ``ClientTimeout`` to override.
REQUEST_TIMEOUT_SECONDS = 30

# ``GET /v2/device`` allows at most 100 rows per page.
DEVICE_LIST_PAGE_SIZE = 100

# Query filters shared by ``GET /v2/device`` and ``POST /v2/commands``.
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

# Real-time updates guide: idle sockets are closed after 10 minutes, and a
# ping is suggested after 60 seconds without other traffic.
WEBSOCKET_IDLE_PING_SECONDS = 60

# Close the socket when no inbound frame arrives for this many ping intervals.
# A sent ping only proves that ``send_str`` returned.
WEBSOCKET_INBOUND_GRACE_INTERVALS = 2

# Real-time updates guide: individual JSON payloads are limited to 32 KB.
WEBSOCKET_MAX_PAYLOAD_BYTES = 32 * 1024
