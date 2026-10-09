"""Async client for the unofficial Fröling Connect cloud API.

Implements the endpoints used by the official Fröling Connect app: login
(JWT returned in the `Authorization` response header, userId inside the JWT
payload), facility/component data, and notifications. The client is read-only
by design: there is deliberately no method to set parameter values (see
PRODUCT.md).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import aiohttp

from .const import (
    COMPONENT_LIST_URL,
    COMPONENT_URL,
    FACILITY_LIST_URL,
    LOGIN_URL,
    NOTIFICATION_COUNT_URL,
    NOTIFICATION_LIST_URL,
    OVERVIEW_URL,
    USER_URL,
)
from .exceptions import (
    AuthenticationError,
    NetworkError,
    ParsingError,
    RateLimitError,
)
from .models import (
    Component,
    Facility,
    FacilityOverview,
    Notification,
    UserProfile,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


def decode_jwt_user_id(token: str) -> int:
    """Extract the userId claim from a JWT payload.

    Raises ValueError when the token is not a decodable JWT with a userId.
    """
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(claims["userId"])
    except (IndexError, KeyError, TypeError, ValueError) as err:
        raise ValueError("Token is not a valid JWT with a userId claim.") from err


class FroelingClient:
    """Read-only async client for the Fröling Connect cloud API."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        language: str = "en",
    ) -> None:
        """Initialize with account credentials and an aiohttp session."""
        self._username = username
        self._password = password
        self._session = session
        self._language = language
        self._token: str | None = None
        self.user_id: int | None = None

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Accept-Language": self._language}
        if self._token:
            headers["Authorization"] = self._token
        return headers

    async def _safe_text(self, response: aiohttp.ClientResponse) -> str:
        """Best-effort response body as text for error messages."""
        try:
            return await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return ""

    async def login(self) -> None:
        """Authenticate and store the session token and user id.

        Raises AuthenticationError when the service rejects the credentials
        or returns an unusable token.
        """
        try:
            response = await self._session.post(
                LOGIN_URL,
                json={
                    "osType": "web",
                    "username": self._username,
                    "password": self._password,
                },
                headers={"Accept-Language": self._language},
                timeout=REQUEST_TIMEOUT,
            )
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise NetworkError(f"Login request failed: {err}") from err

        if response.status in (401, 403):
            detail = await self._safe_text(response)
            raise AuthenticationError(f"Login rejected ({response.status}): {detail}")
        token = response.headers.get("Authorization")
        if not token:
            detail = await self._safe_text(response)
            if response.status >= 300:
                raise NetworkError(f"Login failed with HTTP {response.status}: {detail}")
            raise ParsingError(f"Login response carries no Authorization header: {detail}")
        try:
            self.user_id = decode_jwt_user_id(token)
        except ValueError as err:
            self._token = None
            raise AuthenticationError("Login returned a malformed token") from err
        self._token = token

    async def _request_json(self, method: str, url: str) -> Any:
        """Perform one API request and return the parsed JSON body."""
        try:
            response = await self._session.request(
                method, url, headers=self._headers, timeout=REQUEST_TIMEOUT
            )
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise NetworkError(f"{method} {url} failed: {err}") from err

        if response.status == 429:
            retry_after = _as_float(response.headers.get("Retry-After"))
            raise RateLimitError(retry_after)
        if response.status == 401:
            raise AuthenticationError(f"Session expired ({url})")
        if response.status >= 300:
            detail = await self._safe_text(response)
            raise NetworkError(f"{method} {url} returned HTTP {response.status}: {detail}")
        try:
            return await response.json()
        except (aiohttp.ContentTypeError, ValueError) as err:
            raise ParsingError(f"Non-JSON response from {url}") from err

    async def _authed_request(self, method: str, url: str) -> Any:
        """Request with one transparent re-login when the session expired."""
        if self.user_id is None:
            raise AuthenticationError("Not logged in")
        try:
            return await self._request_json(method, url)
        except AuthenticationError:
            _LOGGER.debug("Session expired, re-logging in")
            await self.login()
            try:
                return await self._request_json(method, url)
            except AuthenticationError as err:
                raise AuthenticationError(
                    f"Re-login did not restore the session ({url})"
                ) from err

    async def get_user(self) -> UserProfile:
        """Fetch the account profile."""
        data = await self._authed_request("GET", USER_URL.format(user_id=self.user_id))
        profile = UserProfile.from_dict(data)
        if profile is None:
            raise ParsingError(f"Unexpected user response: {data!r}")
        return profile

    async def get_facilities(self) -> list[Facility]:
        """Fetch the facilities managed by the account."""
        data = await self._authed_request("GET", FACILITY_LIST_URL.format(user_id=self.user_id))
        if not isinstance(data, list):
            raise ParsingError(f"Unexpected facility list response: {data!r}")
        return [facility for facility in map(Facility.from_dict, data) if facility]

    async def get_component_list(self, facility_id: int) -> list[Component]:
        """Fetch the identity of every component of a facility."""
        data = await self._authed_request(
            "GET", COMPONENT_LIST_URL.format(user_id=self.user_id, facility_id=facility_id)
        )
        if not isinstance(data, list):
            raise ParsingError(f"Unexpected component list response: {data!r}")
        return [component for component in map(Component.from_dict, data) if component]

    async def get_component(self, facility_id: int, component_id: str) -> Component:
        """Fetch one component with its full parameter schema."""
        data = await self._authed_request(
            "GET",
            COMPONENT_URL.format(
                user_id=self.user_id, facility_id=facility_id, component_id=component_id
            ),
        )
        component = Component.from_dict(data, detailed=True)
        if component is None:
            raise ParsingError(f"Unexpected component response: {data!r}")
        return component

    async def get_overview(self, facility_id: int) -> FacilityOverview:
        """Fetch the whole-facility snapshot of current values."""
        data = await self._authed_request(
            "GET", OVERVIEW_URL.format(user_id=self.user_id, facility_id=facility_id)
        )
        overview = FacilityOverview.from_dict(data)
        if overview is None:
            raise ParsingError(f"Unexpected overview response: {data!r}")
        return overview

    async def get_notification_count(self) -> int | None:
        """Fetch the unread notification count, or None when unparseable."""
        data = await self._authed_request(
            "GET", NOTIFICATION_COUNT_URL.format(user_id=self.user_id)
        )
        if not isinstance(data, dict):
            return None
        try:
            return int(data.get("unreadNotifications"))
        except (TypeError, ValueError):
            _LOGGER.debug("Unparseable notification count: %r", data)
            return None

    async def get_notifications(self) -> list[Notification]:
        """Fetch the account's notifications."""
        data = await self._authed_request(
            "GET", NOTIFICATION_LIST_URL.format(user_id=self.user_id)
        )
        if not isinstance(data, list):
            raise ParsingError(f"Unexpected notification list response: {data!r}")
        return [
            notification
            for notification in map(Notification.from_dict, data)
            if notification is not None
        ]


def _as_float(value: str | None) -> float | None:
    """Parse a Retry-After header value, or None when absent/unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
