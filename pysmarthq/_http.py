"""Shared Digital Twin request helper."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from aiohttp import ClientTimeout

from .auth import AbstractAuth
from .const import REQUEST_TIMEOUT_SECONDS
from .errors import SmartHQApiError, SmartHQAuthError

_BODY_SNIPPET_LIMIT = 180
_ACCESS_TOKEN_QUERY = re.compile(r"(access_token=)[^&\s'\"<>]+", re.IGNORECASE)


def request_timeout(timeout: ClientTimeout | None = None) -> ClientTimeout:
    """Return ``timeout`` or the default total timeout for one API call."""
    if timeout is not None:
        return timeout
    return ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)


def redact_access_token(text: str) -> str:
    """Remove an ``access_token`` query value from a URL or error string."""
    return _ACCESS_TOKEN_QUERY.sub(r"\1REDACTED", text)


async def async_api(
    auth: AbstractAuth,
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    ok: tuple[int, ...] = (200,),
    timeout: ClientTimeout | None = None,
    expect_object: bool = True,
) -> Any:
    """Send one Digital Twin request and return the JSON object.

    A 204 response returns ``None`` when ``expect_object`` is false. Statuses
    outside ``ok`` raise ``SmartHQApiError``. HTTP 401 refreshes once and
    retries; a second 401, or a failed refresh, raises ``SmartHQAuthError``.
    HTTP 403 stays ``SmartHQApiError``.
    """
    kwargs: dict[str, Any] = {"timeout": request_timeout(timeout)}
    if params:
        kwargs["params"] = _query_params(params)
    if json_body is not None:
        kwargs["json"] = json_body
    refreshed = False
    while True:
        response = await auth.request(method, path, **kwargs)
        status, body = await _read_body(response)
        if status == 401 and not refreshed:
            refreshed = True
            try:
                await auth.async_force_refresh()
            except SmartHQAuthError as err:
                raise SmartHQAuthError(
                    str(err),
                    status=err.status if err.status is not None else status,
                    error=err.error,
                    error_description=err.error_description,
                    body=err.body if err.body is not None else body,
                ) from err
            continue
        if status == 401:
            raise SmartHQAuthError(
                _status_message(method, path, status, body),
                status=status,
                body=body,
            )
        if status not in ok:
            raise SmartHQApiError(
                _status_message(method, path, status, body),
                status=status,
                body=body,
            )
        if expect_object and not isinstance(body, dict):
            raise SmartHQApiError(
                _status_message(method, path, status, body)
                + " (response was not a JSON object)",
                status=status,
                body=body,
            )
        return body


def api_path(*parts: str) -> str:
    """Join path segments, quoting each one."""
    return "/".join(quote(part, safe="") for part in parts)


def _query_params(params: Mapping[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            query[key] = "true" if value else "false"
        else:
            query[key] = value
    return query


async def _read_body(response: Any) -> tuple[int, Any]:
    try:
        text = await response.text()
    finally:
        release = getattr(response, "release", None)
        if release is not None:
            release()
    if not text:
        return response.status, None
    try:
        return response.status, json.loads(text)
    except json.JSONDecodeError:
        return response.status, text


def _status_message(method: str, path: str, status: int, body: Any) -> str:
    message = f"{method.upper()} {path} failed with status {status}"
    snippet = _body_snippet(body)
    if snippet:
        return f"{message}: {snippet}"
    return message


def _body_snippet(body: Any) -> str:
    if body is None or body == "":
        return ""
    if isinstance(body, str):
        text = body
    else:
        text = json.dumps(body, default=str)
    text = " ".join(text.split())
    if len(text) > _BODY_SNIPPET_LIMIT:
        return text[:_BODY_SNIPPET_LIMIT] + "..."
    return text
