from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
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


class _TokenCache:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.tokens = self._load()

    @staticmethod
    def _key(session_key: tuple[str, str, tuple[str, ...]]) -> str:
        serialized = json.dumps(session_key, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(
        self, session_key: tuple[str, str, tuple[str, ...]]
    ) -> _CachedAccessToken | None:
        return self.tokens.get(self._key(session_key))

    def set(
        self,
        session_key: tuple[str, str, tuple[str, ...]],
        token: _CachedAccessToken,
    ) -> None:
        self.tokens[self._key(session_key)] = token
        self._save()

    def remove(self, session_key: tuple[str, str, tuple[str, ...]]) -> None:
        if self.tokens.pop(self._key(session_key), None) is not None:
            self._save()

    def clear_memory(self) -> None:
        self.tokens.clear()

    def _load(self) -> dict[str, _CachedAccessToken]:
        if self.path is None:
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}
            return {
                key: _CachedAccessToken(
                    value=str(value["access_token"]),
                    expires_at=float(value["expires_at"]),
                )
                for key, value in payload.items()
                if isinstance(value, dict)
            }
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            key: {
                "access_token": token.value,
                "expires_at": token.expires_at,
            }
            for key, token in self.tokens.items()
            if token.expires_at > time.time()
        }
        descriptor = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as cache_file:
            json.dump(payload, cache_file)
        temporary_path.replace(self.path)


StatusCallback = Callable[[str], None]
DeviceCallback = Callable[[DeviceAuthorization], None]


class SsoAuthenticator:
    """Authenticate using Shuttle's private, expiry-bound SSO token cache."""

    def __init__(
        self,
        boto_session: boto3.Session | None = None,
        *,
        token_cache_path: Path | None = None,
    ) -> None:
        self._base_session = boto_session or boto3.Session()
        self._token_cache = _TokenCache(token_cache_path)

    def clear(self) -> None:
        """Forget loaded tokens without deleting unexpired persisted sessions."""
        self._token_cache.clear_memory()

    def has_session(self, profile: SsoProfile) -> bool:
        token = self._token_cache.get(profile.session_key)
        return token is not None and token.expires_at > time.time() + 60

    def authenticate(
        self,
        profile: SsoProfile,
        *,
        cancel: threading.Event,
        on_status: StatusCallback | None = None,
        on_device: DeviceCallback | None = None,
    ) -> AuthenticatedSession:
        status = on_status or (lambda _message: None)
        cache_key = profile.session_key
        cached_token = self._token_cache.get(cache_key)
        if cached_token is not None and cached_token.expires_at > time.time() + 60:
            access_token = cached_token.value
            status("Reusing this session’s IAM Identity Center sign-in…")
        else:
            self._token_cache.remove(cache_key)
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
            self._token_cache.remove(cache_key)
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
        cache_key = profile.session_key
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
        self._token_cache.set(
            cache_key,
            _CachedAccessToken(
                value=access_token,
                expires_at=time.time() + int(token["expiresIn"]),
            ),
        )
        return access_token

