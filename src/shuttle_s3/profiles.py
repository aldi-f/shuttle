from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


class ProfileError(ValueError):
    """Raised when an IAM Identity Center profile is incomplete."""


@dataclass(frozen=True, slots=True)
class SsoProfile:
    name: str
    start_url: str
    sso_region: str
    account_id: str
    role_name: str
    region: str
    scopes: tuple[str, ...] = ("sso:account:access",)

    @property
    def session_key(self) -> tuple[str, str, tuple[str, ...]]:
        """Identify profiles that can share an Identity Center access token."""
        return (self.start_url, self.sso_region, self.scopes)


def default_config_path() -> Path:
    return Path.home() / ".aws" / "config"


def load_sso_profiles(path: Path | None = None) -> list[SsoProfile]:
    config_path = path or default_config_path()
    parser = configparser.RawConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")

    profiles: list[SsoProfile] = []
    for section in parser.sections():
        if section == "default":
            name = "default"
        elif section.startswith("profile "):
            name = section.removeprefix("profile ").strip()
        else:
            continue

        values = parser[section]
        session_name = values.get("sso_session", "").strip()
        session_section = f"sso-session {session_name}"
        session_values = parser[session_section] if session_name and parser.has_section(
            session_section
        ) else None

        def setting(
            key: str,
            default: str = "",
            *,
            profile_values: configparser.SectionProxy = values,
            linked_values: configparser.SectionProxy | None = session_values,
        ) -> str:
            value = profile_values.get(key, "").strip()
            if value:
                return value
            if linked_values is not None:
                return linked_values.get(key, default).strip()
            return default

        start_url = setting("sso_start_url")
        sso_region = setting("sso_region")
        account_id = setting("sso_account_id")
        role_name = setting("sso_role_name")
        if not any((start_url, sso_region, account_id, role_name, session_name)):
            continue
        missing = [
            label
            for label, value in (
                ("sso_start_url", start_url),
                ("sso_region", sso_region),
                ("sso_account_id", account_id),
                ("sso_role_name", role_name),
            )
            if not value
        ]
        if missing:
            # Ignore login-only profiles but identify partially configured SSO profiles.
            raise ProfileError(f"Profile {name!r} is missing: {', '.join(missing)}")

        raw_scopes = setting("sso_registration_scopes", "sso:account:access")
        scopes = tuple(scope.strip() for scope in raw_scopes.split(",") if scope.strip())
        profiles.append(
            SsoProfile(
                name=name,
                start_url=start_url,
                sso_region=sso_region,
                account_id=account_id,
                role_name=role_name,
                region=values.get("region", sso_region).strip() or sso_region,
                scopes=scopes or ("sso:account:access",),
            )
        )
    return sorted(profiles, key=lambda profile: profile.name.casefold())

