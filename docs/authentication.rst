Authentication
==============

The Identity and Access Management API is OAuth 2.0 authorization code. Token requests are ``POST /oauth2/token`` with ``application/x-www-form-urlencoded`` bodies. Browser steps return HTML. This library represents those steps as URLs.

``GET /oauth2/auth`` and ``GET /oauth2/register`` return a SmartHQ web page. ``GET /oauth2/applogout`` clears that browser session and redirects with ``logout=success``. It leaves access and refresh tokens untouched.

Browser URLs
------------

:func:`~pysmarthq.auth.authorization_url` builds ``GET /oauth2/auth``. Open it in a browser or webview. The default ``access_type`` is ``offline``, which is the value that yields a refresh token. ``response_type`` must be ``code``. ``access_type`` must be ``offline`` or ``online``; any other value raises :class:`ValueError`.

.. code-block:: python

   from pysmarthq import authorization_url, registration_url, logout_url

   authorization_url(
       client_id=CLIENT_ID,
       redirect_uri=REDIRECT_URI,
       state="state-from-your-app",
   )

:func:`~pysmarthq.auth.registration_url` builds ``GET /oauth2/register`` with the same query parameters. The authorization guide recommends sending users to ``/oauth2/auth`` and letting that page link to registration when they need an account.

:func:`~pysmarthq.auth.logout_url` builds ``GET /oauth2/applogout``. Open it in the same browser or webview that ran authorization. The redirect carries ``logout=success``. Pass ``state`` when the redirect should echo a value your app already knows.

.. code-block:: python

   from pysmarthq import parse_authorization_callback, parse_logout_callback

   callback = parse_authorization_callback(returned_url)
   if callback.get("error"):
       raise RuntimeError(callback.get("error_description") or callback["error"])
   code = callback["code"]

:func:`~pysmarthq.auth.parse_authorization_callback` returns the query fields defined for ``GET /oauth2/auth``: ``code``, ``state``, ``expires_in``, ``error``, and ``error_description``. A cancelled authorization includes ``error`` and ``error_description``. :func:`~pysmarthq.auth.parse_logout_callback` returns ``logout`` and optional ``state``.

Exchange the code
-----------------

:func:`~pysmarthq.auth.async_exchange_code` posts the code to ``POST /oauth2/token``. ``redirect_uri`` must be the same URI sent to ``GET /oauth2/auth``.

.. code-block:: python

   token = await async_exchange_code(
       session,
       client_id=CLIENT_ID,
       client_secret=CLIENT_SECRET,
       code=callback["code"],
       redirect_uri=REDIRECT_URI,
   )

The helpers require ``token_type``, ``expires_in``, and ``access_token``. When ``expires_in`` is an integer, they set ``expires_at`` to the local Unix time at which that interval elapses. ``expires_at`` is local bookkeeping. It is left off later requests to SmartHQ.

A failed token request raises :class:`~pysmarthq.errors.SmartHQAuthError`. ``error`` and ``error_description`` are the fields from the ``/oauth2/token`` and ``/oauth2/auth`` error responses when the body includes them.

Keep the token
--------------

:class:`~pysmarthq.auth.SmartHQAuth` holds the token dict for one user. Pass ``token_updater`` to receive the replacement dict after a refresh. The updater may be a normal function or a coroutine function. Persist the dict in the updater. The next process starts by constructing ``SmartHQAuth`` with the saved dict.

.. code-block:: python

   async def save_token(updated: dict) -> None:
       await store.write(updated)

   auth = SmartHQAuth(
       session,
       token,
       client_id=CLIENT_ID,
       client_secret=CLIENT_SECRET,
       token_updater=save_token,
   )

The updater runs inside the refresh lock. Calling back into the client from the updater deadlocks on that lock. Limit the updater to storing the token.

When the updater raises, the new token stays in memory. The next :meth:`~pysmarthq.auth.SmartHQAuth.async_get_access_token` retries the updater and skips another token request while the in-memory token is still current.

Refresh
-------

:meth:`~pysmarthq.auth.SmartHQAuth.async_get_access_token` calls ``POST /oauth2/token`` with ``grant_type=refresh_token`` when ``expires_at`` is missing or fewer than :data:`~pysmarthq.const.ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS` (60) seconds remain. A token with exactly 60 seconds left is still current.

The authorization guide describes the returned refresh token as the only valid refresh token after this call. A refresh response that omits ``refresh_token``, or sets it to ``null`` or ``""``, keeps the previous value on :class:`~pysmarthq.auth.SmartHQAuth`. :func:`~pysmarthq.auth.async_refresh_token` returns the response body as SmartHQ sent it and leaves that merge to ``SmartHQAuth``.

Refreshing a token is ``POST /oauth2/token`` with ``grant_type=refresh_token``. The authorization sequence diagram also mentions ``POST /oauth2/refresh_token``, which is absent from the Identity spec. This client follows the spec.

Requests
--------

:class:`~pysmarthq.api.SmartHQApi` and :class:`~pysmarthq.events.EventStream` send ``Authorization: Bearer`` through :meth:`~pysmarthq.auth.AbstractAuth.request`. Digital Twin helpers refresh once after HTTP 401 and retry the call. A second 401, or a refresh that fails, raises :class:`~pysmarthq.errors.SmartHQAuthError`. HTTP 403 stays :class:`~pysmarthq.errors.SmartHQApiError`.

One token or Digital Twin call is bounded by :data:`~pysmarthq.const.REQUEST_TIMEOUT_SECONDS` (30 seconds) when the aiohttp session has no total timeout. Pass ``timeout`` as an :class:`aiohttp.ClientTimeout` to use another budget.

Home Assistant and other hosts
------------------------------

A Home Assistant install that refreshes tokens through account linking can subclass :class:`~pysmarthq.auth.AbstractAuth` and implement :meth:`~pysmarthq.auth.AbstractAuth.async_get_access_token`. Override :meth:`~pysmarthq.auth.AbstractAuth.token_expires_at` when that subclass keeps the expiry somewhere other than a ``token`` dict. :attr:`~pysmarthq.events.EventStream.socket_expires_at` is that timestamp sampled when ``GET /v2/websocket`` returns.

:meth:`~pysmarthq.auth.AbstractAuth.async_force_refresh` runs after the server rejects the access token. The default asks for a token again. ``SmartHQAuth`` drops the "still current" check first so a token that still looks current is exchanged again.
