"""Shared Digital Twin request helper."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from .auth import AbstractAuth
from .errors import SmartHQApiError


async def async_api(
    auth: AbstractAuth,
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    ok: tuple[int, ...] = (200,),
) -> Any:
    """Send one Digital Twin request and return the JSON body.

    A 204 response returns ``None``. Statuses outside ``ok`` raise
    ``SmartHQApiError``. The body is the parsed JSON value when the response
    has one, otherwise the response text.
    """
    kwargs: dict[str, Any] = {}
    if params:
        kwargs["params"] = {key: value for key, value in params.items() if value is not None}
    if json_body is not None:
        kwargs["json"] = json_body
    response = await auth.request(method, path, **kwargs)
    try:
        text = await response.text()
    finally:
        release = getattr(response, "release", None)
        if release is not None:
            release()
    body: Any = None
    if text:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = text
    if response.status not in ok:
        raise SmartHQApiError(
            f"{method.upper()} {path} failed with status {response.status}",
            status=response.status,
            body=body,
        )
    return body


def api_path(*parts: str) -> str:
    """Join path segments, quoting each one."""
    return "/".join(quote(part, safe="") for part in parts)
