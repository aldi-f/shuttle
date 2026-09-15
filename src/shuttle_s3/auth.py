from __future__ import annotations

import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config

from .profiles import SsoProfile

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
USER_AGENT = Config(user_agent_extra="Shuttle/0.1")


class AuthenticationCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    profile: SsoProfile
    boto_session: boto3.Session
    role_expiration_ms: int


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    verification_url: str
    user_code: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class _CachedAccessToken:
    value: str
    expires_at: float


StatusCallback = Callable[[str], None]
DeviceCallback = Callable[[DeviceAuthorization], None]


class SsoAuthenticator:
    """Authenticate without reading or writing the AWS CLI SSO token cache."""

    def __init__(self, boto_session: boto3.Session | None = None) -> None:
        self._base_session = boto_session or boto3.Session()
        self._access_tokens: dict[tuple[str, str, tuple[str, ...]], _CachedAccessToken] = {}

    def clear(self) -> None:
        """Forget all in-memory Identity Center sessions."""
        self._access_tokens.clear()

    def authenticate(
        self,
        profile: SsoProfile,
        *,
        cancel: threading.Event,
        on_status: StatusCallback | None = None,
        on_device: DeviceCallback | None = None,
    ) -> AuthenticatedSession:
        status = on_status or (lambda _message: None)
        cache_key = (profile.start_url, profile.sso_region, profile.scopes)
        cached_token = self._access_tokens.get(cache_key)
        if cached_token is not None and cached_token.expires_at > time.monotonic() + 60:
            access_token = cached_token.value
            status("Reusing this session’s IAM Identity Center sign-in…")
        else:
            self._access_tokens.pop(cache_key, None)
            access_token = self._authorize_device(
                profile,
                cancel=cancel,
                status=status,
                on_device=on_device,
            )

        if cancel.is_set():
            raise AuthenticationCancelled("Sign-in cancelled")

        status("Requesting temporary AWS credentials…")
        sso = self._base_session.client(
            "sso", region_name=profile.sso_region, config=USER_AGENT
        )
        try:
            response = sso.get_role_credentials(
                roleName=profile.role_name,
                accountId=profile.account_id,
                accessToken=access_token,
            )
        except sso.exceptions.UnauthorizedException:
            self._access_tokens.pop(cache_key, None)
            raise RuntimeError(
                "The IAM Identity Center session is no longer valid. Sign in again."
            ) from None
        credentials = response["roleCredentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["accessKeyId"],
            aws_secret_access_key=credentials["secretAccessKey"],
            aws_session_token=credentials["sessionToken"],
            region_name=profile.region,
        )
        status("Signed in")
        return AuthenticatedSession(
            profile=profile,
            boto_session=session,
            role_expiration_ms=int(credentials["expiration"]),
        )

    def _authorize_device(
        self,
        profile: SsoProfile,
        *,
        cancel: threading.Event,
        status: StatusCallback,
        on_device: DeviceCallback | None,
    ) -> str:
        cache_key = (profile.start_url, profile.sso_region, profile.scopes)
        oidc = self._base_session.client(
            "sso-oidc", region_name=profile.sso_region, config=USER_AGENT
        )
        status("Preparing secure browser sign-in…")
        registration = oidc.register_client(
            clientName="Shuttle",
            clientType="public",
            scopes=list(profile.scopes),
        )
        authorization = oidc.start_device_authorization(
            clientId=registration["clientId"],
            clientSecret=registration["clientSecret"],
            startUrl=profile.start_url,
        )
        verification_url = authorization.get("verificationUriComplete") or authorization[
            "verificationUri"
        ]
        device = DeviceAuthorization(
            verification_url=verification_url,
            user_code=authorization["userCode"],
            expires_in=int(authorization["expiresIn"]),
        )
        if on_device:
            on_device(device)
        webbrowser.open(verification_url)
        status(f"Complete sign-in in your browser. Code: {device.user_code}")

        interval = max(int(authorization.get("interval", 5)), 1)
        deadline = time.monotonic() + device.expires_in
        token: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if cancel.wait(interval):
                raise AuthenticationCancelled("Sign-in cancelled")
            try:
                token = oidc.create_token(
                    clientId=registration["clientId"],
                    clientSecret=registration["clientSecret"],
                    grantType=DEVICE_GRANT,
                    deviceCode=authorization["deviceCode"],
                )
                break
            except oidc.exceptions.AuthorizationPendingException:
                continue
            except oidc.exceptions.SlowDownException:
                interval += 5
        if token is None:
            raise TimeoutError("The IAM Identity Center sign-in request expired")
        if cancel.is_set():
            raise AuthenticationCancelled("Sign-in cancelled")
        access_token = token["accessToken"]
        self._access_tokens[cache_key] = _CachedAccessToken(
            value=access_token,
            expires_at=time.monotonic() + int(token["expiresIn"]),
        )
        return access_token

