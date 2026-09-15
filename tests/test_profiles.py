from pathlib import Path

import pytest

from shuttle_s3.profiles import ProfileError, load_sso_profiles


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_modern_and_legacy_profiles(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
[profile modern]
sso_session = company
sso_account_id = 123456789012
sso_role_name = Analyst
region = us-east-2

[sso-session company]
sso_start_url = https://example.awsapps.com/start
sso_region = eu-west-1
sso_registration_scopes = sso:account:access

[profile legacy]
sso_start_url = https://legacy.awsapps.com/start
sso_region = us-west-2
sso_account_id = 210987654321
sso_role_name = Reader
""",
    )

    profiles = load_sso_profiles(path)

    assert [profile.name for profile in profiles] == ["legacy", "modern"]
    modern = profiles[1]
    assert modern.start_url == "https://example.awsapps.com/start"
    assert modern.sso_region == "eu-west-1"
    assert modern.region == "us-east-2"
    assert modern.account_id == "123456789012"


def test_ignores_non_sso_profile(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
[profile static]
region = us-east-1
aws_access_key_id = not-read-by-shuttle
""",
    )
    assert load_sso_profiles(path) == []


def test_reports_incomplete_sso_profile(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
[profile broken]
sso_session = missing
sso_account_id = 123456789012
""",
    )
    with pytest.raises(ProfileError, match="sso_start_url"):
        load_sso_profiles(path)

