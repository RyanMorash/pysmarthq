"""Authentication for SmartHQ.

The Identity and Access Management API is OAuth 2.0 authorization code. Token
requests are ``POST /oauth2/token`` with ``application/x-www-form-urlencoded``
bodies. Browser steps (``GET /oauth2/auth``, ``GET /oauth2/register``, and
``GET /oauth2/applogout``) return HTML and are represented here as URLs.

This module makes authenticated Digital Twin requests. It does not persist
tokens. A refreshed token is returned to the caller as a JSON-serializable
dict through ``token_updater``.

``expires_at`` is not a field on the token response. When ``expires_in`` is an
integer, the exchange and refresh helpers set ``expires_at`` to the local Unix
time at which that ``expires_in`` elapses so a later call can refresh. The
access token is treated as stale when ``expires_at`` is missing and when fewer
than ``ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS`` remain.

``token_updater`` runs inside the refresh lock. It must not call back into the
client. If it raises, the new token stays in memory and the next
``async_get_access_token`` retries the updater without another token request.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

from aiohttp import ClientResponse, ClientSession, ClientTimeout

from .const import ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS, DIGITAL_TWIN_HOST, IAM_HOST, REQUEST_TIMEOUT_SECONDS
from .errors import SmartHQAuthError

TokenUpdater = Callable[[dict[str, Any]], Awaitable[None] | None]
"""Callable that stores a refreshed token.

``SmartHQAuth`` passes a JSON-serializable dict. The callable may return
``None`` or an awaitable. It runs inside the refresh lock and must not call
back into the client.
"""

_AUTH_QUERY_KEYS = ("code", "state", "expires_in", "error", "error_description")
_LOGOUT_QUERY_KEYS = ("logout", "state")


def authorization_url(
    *,
    client_id: str,
    redirect_uri: str | None = None,
    state: str | None = None,
    access_type: str = "offline",
    response_type: str = "code",
    host: str = IAM_HOST,
) -> str:
    """Return the ``GET /oauth2/auth`` URL.

    Open this in a browser or webview. The server responds with the SmartHQ
    login page, then redirects to ``redirect_uri`` with ``code``, ``expires_in``,
    and the optional ``state``.
    """
    return _oauth_page_url(
        "oauth2/auth",
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        access_type=access_type,
        response_type=response_type,
        host=host,
    )


def registration_url(
    *,
    client_id: str,
    redirect_uri: str | None = None,
    state: str | None = None,
    access_type: str = "offline",
    response_type: str = "code",
    host: str = IAM_HOST,
) -> str:
    """Return the ``GET /oauth2/register`` URL.

    The query parameters match ``GET /oauth2/auth``. The authorization guide
    recommends sending users to ``/oauth2/auth`` and letting that page link
    here when they need an account.
    """
    return _oauth_page_url(
        "oauth2/register",
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        access_type=access_type,
        response_type=response_type,
        host=host,
    )


def logout_url(*, state: str | None = None, host: str = IAM_HOST) -> str:
    """Return the ``GET /oauth2/applogout`` URL.

    Open this in the same browser or webview that ran authorization. It clears
    the SmartHQ browser session and redirects with ``logout=success``. It does
    not revoke access or refresh tokens.
    """
    url = f"{host.rstrip('/')}/oauth2/applogout"
    if state is None:
        return url
    return f"{url}?{urlencode({'state': state})}"


def parse_authorization_callback(url: str) -> dict[str, str]:
    """Return callback query fields defined for ``GET /oauth2/auth``.

    Success redirects include ``code``, ``expires_in``, and optional ``state``.
    A cancelled authorization includes ``error`` and ``error_description``.
    """
    return _query_fields(url, _AUTH_QUERY_KEYS)


def parse_logout_callback(url: str) -> dict[str, str]:
    """Return ``logout`` and optional ``state`` from an applogout redirect."""
    return _query_fields(url, _LOGOUT_QUERY_KEYS)


async def async_exchange_code(
    websession: ClientSession,
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    host: str = IAM_HOST,
    timeout: ClientTimeout | None = None,
) -> dict[str, Any]:
    """Exchange an authorization code at ``POST /oauth2/token``.

    ``redirect_uri`` must be the same URI sent to ``GET /oauth2/auth``.
    """
    return await _async_token(
        websession,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        host=host,
        timeout=timeout,
    )


async def async_refresh_token(
    websession: ClientSession,
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    host: str = IAM_HOST,
    timeout: ClientTimeout | None = None,
) -> dict[str, Any]:
    """Exchange a refresh token at ``POST /oauth2/token``.

    The grant type is ``refresh_token``. The authorization guide describes the
    returned refresh token as the only valid refresh token after this call.
    """
    return await _async_token(
        websession,
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        host=host,
        timeout=timeout,
    )


class AbstractAuth(ABC):
    """Make Digital Twin requests with a bearer access token.

    Subclasses supply the token. Home Assistant account linking can refresh
    tokens outside this package and implement ``async_get_access_token``.
    """

    def __init__(
        self,
        websession: ClientSession,
        host: str = DIGITAL_TWIN_HOST,
        *,
        timeout: ClientTimeout | None = None,
    ) -> None:
        """Initialize the auth."""
        self.websession = websession
        self.host = host.rstrip("/")
        self.timeout = timeout if timeout is not None else ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""

    def token_expires_at(self) -> float | None:
        """Return the access token expiry as a Unix timestamp, when known.

        ``SmartHQAuth`` reads ``token["expires_at"]``. A Home Assistant auth
        object that keeps the token elsewhere can override this so
        ``EventStream.socket_expires_at`` can be scheduled. ``None`` means this
        object does not know the expiry.
        """
        token = getattr(self, "token", None)
        if not isinstance(token, Mapping):
            return None
        expires_at = token.get("expires_at")
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            return None
        return float(expires_at)

    async def async_force_refresh(self) -> None:
        """Refresh after the server rejected the access token.

        The default asks for a token again. ``SmartHQAuth`` drops ``expires_at``
        first so a token that still looks current is not reused.
        """
        await self.async_get_access_token()

    async def request(self, method: str, url: str, **kwargs: Any) -> ClientResponse:
        """Make a request to the Digital Twin host.

        ``url`` is a path such as ``v2/device``. An absolute URL is used as
        given. The access token is sent as ``Authorization: Bearer``.
        """
        headers_in = kwargs.pop("headers", None)
        headers = dict(headers_in) if headers_in else {}
        access_token = await self.async_get_access_token()
        headers["Authorization"] = f"Bearer {access_token}"
        if url.startswith(("http://", "https://")):
            full_url = url
        else:
            full_url = f"{self.host}/{url.lstrip('/')}"
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout
        return await self.websession.request(method, full_url, **kwargs, headers=headers)


class SmartHQAuth(AbstractAuth):
    """Digital Twin auth that refreshes an OAuth token dict when it expires.

    The dict is the token response plus a local ``expires_at``. This object
    does not write the token anywhere. Pass ``token_updater`` to receive the
    replacement dict after a refresh.
    """

    def __init__(
        self,
        websession: ClientSession,
        token: Mapping[str, Any],
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        token_updater: TokenUpdater | None = None,
        host: str = DIGITAL_TWIN_HOST,
        iam_host: str = IAM_HOST,
        timeout: ClientTimeout | None = None,
    ) -> None:
        """Initialize the auth."""
        super().__init__(websession, host, timeout=timeout)
        self.token = dict(token)
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_updater = token_updater
        self._iam_host = iam_host
        self._lock = asyncio.Lock()
        self._persist_pending = False
        self._force_refresh = False

    async def async_force_refresh(self) -> None:
        """Refresh even when ``expires_at`` still looks current.

        Used after HTTP 401. The flag is consumed by the next
        ``async_get_access_token``, which exchanges the refresh token.
        """
        async with self._lock:
            self._force_refresh = True
        await self.async_get_access_token()

    async def async_get_access_token(self) -> str:
        """Return the current access token, refreshing it shortly before ``expires_at``."""
        async with self._lock:
            force = self._force_refresh
            self._force_refresh = False
            if self._persist_pending and not force and _token_is_current(self.token):
                await self._persist_token()
                return str(self.token["access_token"])
            if not force and _token_is_current(self.token):
                return str(self.token["access_token"])
            refresh_token = self.token.get("refresh_token")
            if not refresh_token or not self._client_id or not self._client_secret:
                raise SmartHQAuthError(
                    "Access token is expired and no refresh token and client credentials are available"
                )
            refreshed = await async_refresh_token(
                self.websession,
                client_id=self._client_id,
                client_secret=self._client_secret,
                refresh_token=str(refresh_token),
                host=self._iam_host,
                timeout=self.timeout,
            )
            # A missing, null, or blank refresh token leaves the previous one in place.
            new_refresh = refreshed.get("refresh_token")
            if not isinstance(new_refresh, str) or not new_refresh:
                refreshed["refresh_token"] = refresh_token
            self.token = refreshed
            await self._persist_token()
            access_token = self.token.get("access_token")
            if not access_token:
                raise SmartHQAuthError("Token response did not include access_token")
            return str(access_token)

    async def _persist_token(self) -> None:
        """Hand the token dict to ``token_updater``.

        On failure the rotated token stays in ``self.token`` and the next
        ``async_get_access_token`` retries this method without another refresh.
        """
        updater = self._token_updater
        if updater is None:
            self._persist_pending = False
            return
        try:
            result = updater(dict(self.token))
            if result is not None:
                await result
        except Exception:
            self._persist_pending = True
            raise
        self._persist_pending = False


def _oauth_page_url(
    path: str,
    *,
    client_id: str,
    redirect_uri: str | None,
    state: str | None,
    access_type: str,
    response_type: str,
    host: str,
) -> str:
    if response_type != "code":
        raise ValueError("response_type must be 'code'")
    if access_type not in ("offline", "online"):
        raise ValueError("access_type must be 'offline' or 'online'")
    query: dict[str, str] = {
        "response_type": response_type,
        "client_id": client_id,
        "access_type": access_type,
    }
    if redirect_uri is not None:
        query["redirect_uri"] = redirect_uri
    if state is not None:
        query["state"] = state
    return f"{host.rstrip('/')}/{path}?{urlencode(query)}"


def _query_fields(url: str, keys: tuple[str, ...]) -> dict[str, str]:
    found = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    return {key: found[key] for key in keys if key in found}


async def _async_token(
    websession: ClientSession,
    form: Mapping[str, str],
    *,
    host: str,
    timeout: ClientTimeout | None = None,
) -> dict[str, Any]:
    url = f"{host.rstrip('/')}/oauth2/token"
    response = await websession.request(
        "POST",
        url,
        data=dict(form),
        timeout=timeout if timeout is not None else ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
    )
    try:
        text = await response.text()
    finally:
        release = getattr(response, "release", None)
        if release is not None:
            release()
    body: Any
    if text:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = None
    else:
        body = None
    if response.status >= 400 or not isinstance(body, dict):
        error = body.get("error") if isinstance(body, dict) else None
        description = body.get("error_description") if isinstance(body, dict) else None
        message = description or error or text or f"Token request failed with status {response.status}"
        raise SmartHQAuthError(
            message,
            status=response.status,
            error=error,
            error_description=description,
            body=body if body is not None else text,
        )
    missing = [key for key in ("token_type", "expires_in", "access_token") if key not in body]
    if missing:
        raise SmartHQAuthError(
            f"Token response did not include {', '.join(missing)}",
            status=response.status,
            body=body,
        )
    token = dict(body)
    expires_in = token.get("expires_in")
    if isinstance(expires_in, int) and not isinstance(expires_in, bool) and "expires_at" not in token:
        token["expires_at"] = int(time.time()) + expires_in
    return token


def _token_is_current(token: Mapping[str, Any]) -> bool:
    access_token = token.get("access_token")
    if not access_token:
        return False
    expires_at = token.get("expires_at")
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
        return False
    return time.time() <= float(expires_at) - ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS
