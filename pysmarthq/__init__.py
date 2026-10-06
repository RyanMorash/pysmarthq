"""Async client for the GE Appliances SmartHQ APIs."""

from importlib.metadata import PackageNotFoundError, version

from .api import SmartHQApi
from .auth import (
    AbstractAuth,
    SmartHQAuth,
    async_exchange_code,
    async_refresh_token,
    authorization_url,
    logout_url,
    parse_authorization_callback,
    parse_logout_callback,
    registration_url,
)
from .errors import SmartHQApiError, SmartHQAuthError, SmartHQError, SmartHQStreamClosed
from .events import EventStream
from .models import Device, Service

try:
    __version__ = version("pysmarthq")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = [
    "AbstractAuth",
    "Device",
    "EventStream",
    "Service",
    "SmartHQApi",
    "SmartHQApiError",
    "SmartHQAuth",
    "SmartHQAuthError",
    "SmartHQError",
    "SmartHQStreamClosed",
    "async_exchange_code",
    "async_refresh_token",
    "authorization_url",
    "logout_url",
    "parse_authorization_callback",
    "parse_logout_callback",
    "registration_url",
]
