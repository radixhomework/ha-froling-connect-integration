"""Tests for the read-only Fröling Connect API client.

Requests are exercised against a scripted stub session replaying the recorded
fixtures; no network is involved.
"""

import asyncio
import base64
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.froling_connect import const
from custom_components.froling_connect.client import FroelingClient
from custom_components.froling_connect.const import (
    COMPONENT_LIST_URL,
    COMPONENT_URL,
    FACILITY_LIST_URL,
    LOGIN_URL,
    NOTIFICATION_COUNT_URL,
    NOTIFICATION_LIST_URL,
    OVERVIEW_URL,
    USER_URL,
)
from custom_components.froling_connect.exceptions import (
    AuthenticationError,
    NetworkError,
    ParsingError,
    RateLimitError,
)

USER_ID = 12345
FACILITY_ID = 12345


def run(coro):
    return asyncio.run(coro)


def make_jwt(user_id: int = USER_ID) -> str:
    """Build a JWT-shaped token carrying the given userId."""

    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'userId': user_id})}.signature"


class StubResponse:
    def __init__(self, status: int = 200, headers: dict | None = None, payload: Any = None):
        self.status = status
        self.headers = headers or {}
        self._payload = payload

    async def json(self):
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload

    async def text(self):
        return json.dumps(self._payload) if self._payload is not None else ""


class StubSession:
    """Scripted aiohttp session: responses are consumed in order."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.requests: list[tuple[str, str]] = []

    def _next(self):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url))
        return self._next()

    async def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        return self._next()


def login_ok(payload: Any) -> StubResponse:
    return StubResponse(headers={"Authorization": make_jwt()}, payload=payload)


def logged_in_client(load_fixture) -> tuple[FroelingClient, StubSession]:
    session = StubSession([login_ok(load_fixture("login.json"))])
    client = FroelingClient("user@example.com", "secret", session)
    run(client.login())
    session.requests.clear()
    return client, session


#
# 2.2 — login
#
def test_login_success(load_fixture):
    session = StubSession([login_ok(load_fixture("login.json"))])
    client = FroelingClient("user@example.com", "secret", session)

    run(client.login())

    assert client.user_id == USER_ID
    assert session.requests == [("POST", LOGIN_URL)]


def test_login_bad_credentials(load_fixture):
    session = StubSession(
        [StubResponse(status=401, payload=load_fixture("login_bad_creds.json"))]
    )
    client = FroelingClient("user@example.com", "wrong", session)

    with pytest.raises(AuthenticationError) as err:
        run(client.login())
    assert "Falscher Benutzername oder Passwort" in str(err.value)


def test_request_before_login_raises():
    client = FroelingClient("user@example.com", "secret", StubSession([]))

    with pytest.raises(AuthenticationError, match="Not logged in"):
        run(client.get_facilities())


#
# 2.3 — 401 → re-login once → retry; second 401 → auth error
#
def test_reauth_on_401_retries_once(load_fixture):
    client, session = logged_in_client(load_fixture)
    session._responses = [
        StubResponse(status=401, payload={}),
        login_ok(load_fixture("login.json")),
        StubResponse(payload=load_fixture("facility.json")),
    ]

    facilities = run(client.get_facilities())

    assert [f.facility_id for f in facilities] == [12345, 54321]
    assert session.requests == [
        ("GET", FACILITY_LIST_URL.format(user_id=USER_ID)),
        ("POST", LOGIN_URL),
        ("GET", FACILITY_LIST_URL.format(user_id=USER_ID)),
    ]


def test_second_401_after_relogin_raises(load_fixture):
    client, session = logged_in_client(load_fixture)
    session._responses = [
        StubResponse(status=401, payload={}),
        login_ok(load_fixture("login.json")),
        StubResponse(status=401, payload={}),
    ]

    with pytest.raises(AuthenticationError, match="Re-login did not restore"):
        run(client.get_facilities())


#
# error handling on the request path
#
def test_429_raises_rate_limit_error_with_retry_after(load_fixture):
    client, session = logged_in_client(load_fixture)
    session._responses = [StubResponse(status=429, headers={"Retry-After": "300"})]

    with pytest.raises(RateLimitError) as err:
        run(client.get_facilities())
    assert err.value.retry_after == 300


def test_http_500_raises_network_error(load_fixture):
    client, session = logged_in_client(load_fixture)
    session._responses = [StubResponse(status=500, payload={"message": "boom"})]

    with pytest.raises(NetworkError, match="500"):
        run(client.get_facilities())


def test_non_json_body_raises_parsing_error(load_fixture):
    client, session = logged_in_client(load_fixture)
    session._responses = [StubResponse(status=200, payload=None)]

    with pytest.raises(ParsingError):
        run(client.get_facilities())


#
# 2.4 — data fetches against the recorded fixtures
#
def test_all_fetches_return_typed_models(load_fixture):
    client, session = logged_in_client(load_fixture)
    session._responses = [
        StubResponse(payload=load_fixture("facility.json")),
        StubResponse(payload=load_fixture("component_list.json")),
        StubResponse(payload=load_fixture("component.json")),
        StubResponse(payload=load_fixture("overview.json")),
        StubResponse(payload=load_fixture("notification_count.json")),
        StubResponse(payload=load_fixture("notification_list.json")),
        StubResponse(payload=load_fixture("user.json")),
    ]

    facilities = run(client.get_facilities())
    components = run(client.get_component_list(FACILITY_ID))
    component = run(client.get_component(FACILITY_ID, "1_100"))
    overview = run(client.get_overview(FACILITY_ID))
    count = run(client.get_notification_count())
    notifications = run(client.get_notifications())
    profile = run(client.get_user())

    assert [f.facility_id for f in facilities] == [12345, 54321]
    assert len(components) == 5
    assert component.parameters["boilerTemp"].value == 78.0
    assert overview.components["1_100"].values["boilerTemp"].raw_value == "76"
    assert count == 123
    assert len(notifications) == 3
    assert profile.user_id == USER_ID

    facility_url = FACILITY_LIST_URL.format(user_id=USER_ID)
    assert session.requests == [
        ("GET", facility_url),
        ("GET", COMPONENT_LIST_URL.format(user_id=USER_ID, facility_id=FACILITY_ID)),
        ("GET", COMPONENT_URL.format(user_id=USER_ID, facility_id=FACILITY_ID, component_id="1_100")),
        ("GET", OVERVIEW_URL.format(user_id=USER_ID, facility_id=FACILITY_ID)),
        ("GET", NOTIFICATION_COUNT_URL.format(user_id=USER_ID)),
        ("GET", NOTIFICATION_LIST_URL.format(user_id=USER_ID)),
        ("GET", USER_URL.format(user_id=USER_ID)),
    ]


#
# 2.6 — the client surface is read-only
#
def test_client_public_surface_is_read_only():
    public = {
        name
        for name, member in inspect.getmembers(FroelingClient, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public == {
        "login",
        "get_user",
        "get_facilities",
        "get_component_list",
        "get_component",
        "get_overview",
        "get_notification_count",
        "get_notifications",
    }
    assert not [name for name in public if name.startswith(("set", "put", "write", "post", "update", "delete", "send"))]


def test_no_write_endpoint_constant_exists():
    const_source = Path(const.__file__).read_text(encoding="utf-8")
    # the write endpoint path must not appear anywhere in the constants module
    assert "/parameter/" not in const_source
