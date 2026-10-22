from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from workers.analysis.auth import AuthenticationError, GitHubAppAuth


def _key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


def test_installation_token_is_signed_and_cached() -> None:
    private_pem, public_pem = _key_pair()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "token": "SENTINEL_FAKE_TOKEN",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        auth = GitHubAppAuth("123", private_pem, "456", http)
        token1 = auth.installation_token()
        token2 = auth.installation_token()

    assert token1 == token2 == "SENTINEL_FAKE_TOKEN"
    assert len(requests) == 1
    assert requests[0].url.path == "/app/installations/456/access_tokens"
    assertion = requests[0].headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(assertion, public_pem, algorithms=["RS256"])
    assert claims["iss"] == "123"
    assert claims["exp"] - claims["iat"] == 9 * 60


def test_missing_app_environment_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ID", "PRIVATE_KEY", "INSTALLATION_ID"):
        monkeypatch.delenv(name, raising=False)
    with httpx.Client() as http, pytest.raises(AuthenticationError, match="APP_ID"):
        GitHubAppAuth.from_environment(http)
