"""HTTP stand-in for aiohttp.ClientSession."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse


class Response:
    """Minimal response that matches the methods the client uses."""

    def __init__(self, status: int, body: Any = None, text: str | None = None) -> None:
        self.status = status
        self._body = body
        self._text = text
        self.released = False

    async def text(self) -> str:
        if self._text is not None:
            return self._text
        if self._body is None:
            return ""
        return json.dumps(self._body)

    def release(self) -> None:
        self.released = True


class MockSession:
    """Records requests and returns scripted responses."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.routes: dict[tuple[str, str], Response | Callable[..., Response]] = {}
        self.ws: Any = None

    async def request(self, method: str, url: str, **kwargs: Any) -> Response:
        self.requests.append({"method": method.upper(), "url": url, **kwargs})
        path = urlparse(url).path
        handler = self.routes.get((method.upper(), path))
        if handler is None:
            return Response(404, {"message": f"no route for {method} {path}"})
        if callable(handler):
            return handler(method, url, kwargs)
        return handler

    async def ws_connect(self, url: str, **kwargs: Any) -> Any:
        self.requests.append({"method": "WS", "url": url, **kwargs})
        if self.ws is None:
            raise RuntimeError("no websocket scripted")
        return self.ws


def json_body(request: dict[str, Any]) -> Any:
    return request.get("json")


def form_body(request: dict[str, Any]) -> dict[str, Any]:
    return dict(request.get("data") or {})
