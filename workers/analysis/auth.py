"""GitHub App installation-token authentication."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

API_VERSION = "2022-11-28"
GITHUB_API = "https://api.github.com"


class AuthenticationError(RuntimeError):
    """Raised when a GitHub App token cannot be created or refreshed."""


class GitHubAppAuth:
    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: str,
        http: httpx.Client,
    ) -> None:
        if not re.fullmatch(r"[0-9]+", app_id):
            raise AuthenticationError("APP_ID must be numeric")
        if not re.fullmatch(r"[0-9]+", installation_id):
            raise AuthenticationError("INSTALLATION_ID must be numeric")
        self._app_id = app_id
        self._private_key = private_key.replace("\\n", "\n")
        self._installation_id = installation_id
        self._http = http
        self._token: str | None = None
        self._expires_at: datetime | None = None

    @classmethod
    def from_environment(cls, http: httpx.Client) -> GitHubAppAuth:
        names = ("APP_ID", "PRIVATE_KEY", "INSTALLATION_ID")
        values = {name: os.environ.get(name) for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise AuthenticationError(
                "Missing required environment variable(s): " + ", ".join(missing)
            )
        return cls(
            app_id=values["APP_ID"] or "",
            private_key=values["PRIVATE_KEY"] or "",
            installation_id=values["INSTALLATION_ID"] or "",
            http=http,
        )

    def installation_token(self) -> str:
        now = datetime.now(UTC)
        if (
            self._token is not None
            and self._expires_at is not None
            and now < self._expires_at - timedelta(minutes=1)
        ):
            return self._token

        issued_at = int(now.timestamp()) - 60
        try:
            assertion = jwt.encode(
                {
                    "iat": issued_at,
                    "exp": issued_at + 9 * 60,
                    "iss": self._app_id,
                },
                self._private_key,
                algorithm="RS256",
            )
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise AuthenticationError("GitHub App assertion could not be signed") from exc
        try:
            response = self._http.post(
                f"{GITHUB_API}/app/installations/{self._installation_id}/access_tokens",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {assertion}",
                    "X-GitHub-Api-Version": API_VERSION,
                },
            )
        except httpx.HTTPError as exc:
            raise AuthenticationError("GitHub installation token request failed") from exc
        if response.status_code != 201:
            raise AuthenticationError(
                f"GitHub installation token request failed with HTTP {response.status_code}"
            )
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise AuthenticationError("GitHub returned invalid token response data") from exc
        if not isinstance(payload, dict):
            raise AuthenticationError("GitHub returned an invalid installation token response")
        token = payload.get("token")
        expires_at = payload.get("expires_at")
        if not isinstance(token, str) or not token or not isinstance(expires_at, str):
            raise AuthenticationError("GitHub returned an invalid installation token response")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AuthenticationError("GitHub returned an invalid token expiry") from exc
        if expiry.tzinfo is None:
            raise AuthenticationError("GitHub returned a token expiry without a timezone")
        self._token = token
        self._expires_at = expiry.astimezone(UTC)
        return token
