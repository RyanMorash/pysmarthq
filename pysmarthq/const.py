"""Hosts and limits taken from the SmartHQ specifications and docs."""

# Identity and Access Management OpenAPI server.
IAM_HOST = "https://accounts.brillion.geappliances.com"

# Digital Twin OpenAPI server.
DIGITAL_TWIN_HOST = "https://client.mysmarthq.com"

# Real-time updates guide: idle sockets are closed after 10 minutes, and a
# ping is suggested after 60 seconds without other traffic.
WEBSOCKET_IDLE_PING_SECONDS = 60

# Real-time updates guide: individual JSON payloads are limited to 32 KB.
WEBSOCKET_MAX_PAYLOAD_BYTES = 32 * 1024
