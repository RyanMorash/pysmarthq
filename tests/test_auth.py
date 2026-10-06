"""Identity and access management tests."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from pysmarthq import (
    SmartHQAuth,
    SmartHQAuthError,
    async_exchange_code,
    async_refresh_token,
    authorization_url,
    logout_url,
    parse_authorization_callback,
    parse_logout_callback,
    registration_url,
)
from pysmarthq.auth import AbstractAuth

from .conftest import MockSession, Response, form_body


def test_authorization_url_matches_the_spec() -> None:
    url = authorization_url(
        client_id="client",
        redirect_uri="https://example.com/callback",
        state="abc",
    )
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.brillion.geappliances.com"
    assert parsed.path == "/oauth2/auth"
    query = parse_qs(parsed.query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client"]
    assert query["redirect_uri"] == ["https://example.com/callback"]
    assert query["access_type"] == ["offline"]
    assert query["state"] == ["abc"]


def test_registration_url_uses_the_same_query() -> None:
    url = registration_url(
        client_id="client",
        redirect_uri="https://example.com/callback",
        access_type="online",
    )
    parsed = urlparse(url)
    assert parsed.path == "/oauth2/register"
    assert parse_qs(parsed.query)["access_type"] == ["online"]


def test_invalid_access_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        authorization_url(client_id="client", access_type="token")


def test_logout_url_is_a_get_with_optional_state() -> None:
    assert logout_url() == "https://accounts.brillion.geappliances.com/oauth2/applogout"
    parsed = urlparse(logout_url(state="abc"))
    assert parsed.path == "/oauth2/applogout"
    assert parse_qs(parsed.query)["state"] == ["abc"]


def test_callback_parsers_keep_spec_fields() -> None:
    granted = parse_authorization_callback(
        "https://example.com/callback?code=someauthcode&state=somestate&expires_in=600"
    )
    assert granted == {"code": "someauthcode", "state": "somestate", "expires_in": "600"}
    cancelled = parse_authorization_callback(
        "https://example.com/redirect?error=invalid_request&error_description=User+did+not+authorize+access."
    )
    assert cancelled["error"] == "invalid_request"
    assert cancelled["error_description"] == "User did not authorize access."
    assert parse_logout_callback("https://some-app-redirect-uri.com?logout=success&state=somestate") == {
        "logout": "success",
        "state": "somestate",
    }


@pytest.mark.asyncio
async def test_exchange_code_posts_form_to_the_token_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pysmarthq.auth.time.time", lambda: 1_700_000_000)
    session = MockSession()
    session.routes[("POST", "/oauth2/token")] = Response(
        200,
        {
            "token_type": "Bearer",
            "expires_in": 3600,
            "access_token": "access-1",
            "refresh_token": "refresh-1",
        },
    )
    token = await async_exchange_code(
        session,  # type: ignore[arg-type]
        client_id="client",
        client_secret="secret",
        code="someauthcode",
        redirect_uri="https://example.com/callback",
    )
    request = session.requests[0]
    assert request["url"] == "https://accounts.brillion.geappliances.com/oauth2/token"
    assert form_body(request) == {
        "grant_type": "authorization_code",
        "client_id": "client",
        "client_secret": "secret",
        "code": "someauthcode",
        "redirect_uri": "https://example.com/callback",
    }
    assert token["access_token"] == "access-1"
    assert token["expires_at"] == 1_700_000_000 + 3600
    assert session.routes[("POST", "/oauth2/token")].released  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_token_request_is_form_urlencoded() -> None:
    from aiohttp import ClientSession, web
    from aiohttp.test_utils import TestServer

    seen: dict[str, object] = {}

    async def handler(request: web.Request) -> web.Response:
        form = await request.post()
        seen["content_type"] = request.content_type
        seen["grant_type"] = form["grant_type"]
        seen["code"] = form["code"]
        return web.json_response(
            {"token_type": "Bearer", "expires_in": 3600, "access_token": "access-1"}
        )

    app = web.Application()
    app.router.add_post("/oauth2/token", handler)
    server = TestServer(app)
    await server.start_server()
    try:
        async with ClientSession() as session:
            host = str(server.make_url("/")).rstrip("/")
            token = await async_exchange_code(
                session,
                client_id="client",
                client_secret="secret",
                code="someauthcode",
                redirect_uri="https://example.com/callback",
                host=host,
            )
    finally:
        await server.close()
    assert seen["content_type"] == "application/x-www-form-urlencoded"
    assert seen["grant_type"] == "authorization_code"
    assert seen["code"] == "someauthcode"
    assert token["access_token"] == "access-1"


@pytest.mark.asyncio
async def test_token_error_exposes_the_spec_fields() -> None:
    session = MockSession()
    session.routes[("POST", "/oauth2/token")] = Response(
        401,
        {"error": "invalid_request", "error_description": "ClientSecret is Invalid"},
    )
    with pytest.raises(SmartHQAuthError) as caught:
        await async_refresh_token(
            session,  # type: ignore[arg-type]
            client_id="client",
            client_secret="wrong",
            refresh_token="refresh-1",
        )
    assert caught.value.status == 401
    assert caught.value.error == "invalid_request"
    assert caught.value.error_description == "ClientSecret is Invalid"
    assert form_body(session.requests[0])["grant_type"] == "refresh_token"


@pytest.mark.asyncio
async def test_non_json_token_error() -> None:
    session = MockSession()
    session.routes[("POST", "/oauth2/token")] = Response(400, text="bad gateway")
    with pytest.raises(SmartHQAuthError) as caught:
        await async_exchange_code(
            session,  # type: ignore[arg-type]
            client_id="client",
            client_secret="secret",
            code="code",
            redirect_uri="https://example.com/callback",
        )
    assert caught.value.status == 400
    assert caught.value.body == "bad gateway"


@pytest.mark.asyncio
async def test_bearer_requests_use_the_digital_twin_host() -> None:
    session = MockSession()
    session.routes[("GET", "/v2/device")] = Response(200, {"devices": []})

    class FixedAuth(AbstractAuth):
        async def async_get_access_token(self) -> str:
            return "access-1"

    auth = FixedAuth(session, host="https://twin.example")  # type: ignore[arg-type]
    response = await auth.request("GET", "/v2/device")
    assert response.status == 200
    request = session.requests[0]
    assert request["url"] == "https://twin.example/v2/device"
    assert request["headers"]["Authorization"] == "Bearer access-1"


@pytest.mark.asyncio
async def test_refresh_runs_once_and_reports_a_serializable_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pysmarthq.auth.time.time", lambda: 1_700_000_000)
    session = MockSession()
    started = asyncio.Event()
    release = asyncio.Event()
    original = session.request

    async def blocking_request(method: str, url: str, **kwargs):
        if url.endswith("/oauth2/token"):
            session.requests.append({"method": method.upper(), "url": url, **kwargs})
            started.set()
            await release.wait()
            return Response(
                200,
                {
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "access_token": "access-2",
                    "refresh_token": "refresh-2",
                },
            )
        return await original(method, url, **kwargs)

    session.request = blocking_request  # type: ignore[method-assign]
    seen: list[dict] = []

    def updater(token: dict) -> None:
        seen.append(token)

    auth = SmartHQAuth(
        session,  # type: ignore[arg-type]
        {"access_token": "access-1", "refresh_token": "refresh-1", "expires_at": 0},
        client_id="client",
        client_secret="secret",
        token_updater=updater,
        iam_host="https://iam.example",
    )
    first = asyncio.create_task(auth.async_get_access_token())
    await started.wait()
    second = asyncio.create_task(auth.async_get_access_token())
    await asyncio.sleep(0)
    release.set()
    assert await first == "access-2"
    assert await second == "access-2"
    assert len(seen) == 1
    assert seen[0]["refresh_token"] == "refresh-2"
    assert seen[0]["expires_at"] == 1_700_000_000 + 3600
    assert all(isinstance(value, (str, int)) for value in seen[0].values())
    token_calls = [item for item in session.requests if item["url"].endswith("/oauth2/token")]
    assert len(token_calls) == 1
    assert "expires_at" not in form_body(token_calls[0])


@pytest.mark.asyncio
async def test_current_token_is_not_refreshed() -> None:
    session = MockSession()
    auth = SmartHQAuth(
        session,  # type: ignore[arg-type]
        {"access_token": "access-1", "expires_at": 9_999_999_999},
        client_id="client",
        client_secret="secret",
    )
    assert await auth.async_get_access_token() == "access-1"
    assert session.requests == []


@pytest.mark.asyncio
async def test_expired_token_without_refresh_material_fails() -> None:
    session = MockSession()
    auth = SmartHQAuth(
        session,  # type: ignore[arg-type]
        {"access_token": "access-1", "expires_at": 0},
    )
    with pytest.raises(SmartHQAuthError):
        await auth.async_get_access_token()
