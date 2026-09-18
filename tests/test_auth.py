from __future__ import annotations

from pathlib import Path
from typing import Any

from shuttle_s3.auth import DEVICE_GRANT, SsoAuthenticator
from shuttle_s3.profiles import SsoProfile


class NeverCancelled:
    def wait(self, _timeout: float) -> bool:
        return False

    def is_set(self) -> bool:
        return False


class FakeOidc:
    class exceptions:
        class AuthorizationPendingException(Exception):
            pass

        class SlowDownException(Exception):
            pass

    def __init__(self) -> None:
        self.registration_count = 0

    def register_client(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["clientType"] == "public"
        self.registration_count += 1
        return {"clientId": "client", "clientSecret": "secret"}

    def start_device_authorization(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["startUrl"] == "https://example.awsapps.com/start"
        return {
            "deviceCode": "device",
            "userCode": "ABCD-EFGH",
            "verificationUri": "https://device.example",
            "verificationUriComplete": "https://device.example?code=ABCD-EFGH",
            "expiresIn": 60,
            "interval": 1,
        }

    def create_token(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["grantType"] == DEVICE_GRANT
        return {"accessToken": "access-token", "expiresIn": 3600}


class FakeSso:
    class exceptions:
        class UnauthorizedException(Exception):
            pass

    def __init__(self) -> None:
        self.requested_roles: list[str] = []

    def get_role_credentials(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["accountId"] == "123456789012"
        assert kwargs["accessToken"] == "access-token"
        self.requested_roles.append(kwargs["roleName"])
        return {
            "roleCredentials": {
                "accessKeyId": "ASIAEXAMPLE",
                "secretAccessKey": "secret",
                "sessionToken": "session",
                "expiration": 2_000_000_000_000,
            }
        }


class FakeBaseSession:
    def __init__(self) -> None:
        self.oidc = FakeOidc()
        self.sso = FakeSso()

    def client(self, service: str, **_kwargs: Any) -> Any:
        return {"sso-oidc": self.oidc, "sso": self.sso}[service]


def test_standalone_device_authorization(monkeypatch: Any) -> None:
    opened: list[str] = []
    monkeypatch.setattr("shuttle_s3.auth.webbrowser.open", opened.append)
    devices: list[Any] = []
    profile = SsoProfile(
        name="analyst",
        start_url="https://example.awsapps.com/start",
        sso_region="eu-west-1",
        account_id="123456789012",
        role_name="Analyst",
        region="eu-west-1",
    )

    authenticated = SsoAuthenticator(FakeBaseSession()).authenticate(
        profile,
        cancel=NeverCancelled(),
        on_device=devices.append,
    )

    assert authenticated.profile == profile
    assert authenticated.role_expiration_ms == 2_000_000_000_000
    assert devices[0].user_code == "ABCD-EFGH"
    assert opened == ["https://device.example?code=ABCD-EFGH"]


def test_reuses_login_for_profiles_in_same_identity_center(monkeypatch: Any) -> None:
    opened: list[str] = []
    monkeypatch.setattr("shuttle_s3.auth.webbrowser.open", opened.append)
    base_session = FakeBaseSession()
    authenticator = SsoAuthenticator(base_session)
    first = SsoProfile(
        name="reader",
        start_url="https://example.awsapps.com/start",
        sso_region="eu-west-1",
        account_id="123456789012",
        role_name="Reader",
        region="eu-west-1",
    )
    second = SsoProfile(
        name="analyst",
        start_url=first.start_url,
        sso_region=first.sso_region,
        account_id=first.account_id,
        role_name="Analyst",
        region=first.region,
    )

    authenticator.authenticate(first, cancel=NeverCancelled())
    authenticator.authenticate(second, cancel=NeverCancelled())

    assert base_session.oidc.registration_count == 1
    assert base_session.sso.requested_roles == ["Reader", "Analyst"]
    assert opened == ["https://device.example?code=ABCD-EFGH"]


def test_persists_login_until_its_expiry(monkeypatch: Any, tmp_path: Path) -> None:
    opened: list[str] = []
    monkeypatch.setattr("shuttle_s3.auth.webbrowser.open", opened.append)
    cache_path = tmp_path / "sso-session.json"
    profile = SsoProfile(
        name="reader",
        start_url="https://example.awsapps.com/start",
        sso_region="eu-west-1",
        account_id="123456789012",
        role_name="Reader",
        region="eu-west-1",
    )
    first_session = FakeBaseSession()

    first_authenticator = SsoAuthenticator(
        first_session,
        token_cache_path=cache_path,
    )
    first_authenticator.authenticate(profile, cancel=NeverCancelled())

    restored_session = FakeBaseSession()
    restored_authenticator = SsoAuthenticator(
        restored_session,
        token_cache_path=cache_path,
    )
    assert restored_authenticator.has_session(profile)
    restored_authenticator.authenticate(profile, cancel=NeverCancelled())

    assert cache_path.exists()
    assert first_session.oidc.registration_count == 1
    assert restored_session.oidc.registration_count == 0
    assert restored_session.sso.requested_roles == ["Reader"]
    assert opened == ["https://device.example?code=ABCD-EFGH"]
