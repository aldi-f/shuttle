from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shuttle_s3.profiles import SsoProfile

pytest.importorskip("PySide6.QtGui", exc_type=ImportError)

from shuttle_s3.ui import MainWindow


def profile(name: str, *, start_url: str = "https://example.awsapps.com/start") -> SsoProfile:
    return SsoProfile(
        name=name,
        start_url=start_url,
        sso_region="eu-west-1",
        account_id="123456789012",
        role_name=name.title(),
        region="eu-west-1",
    )


def test_sign_in_automatically_loads_buckets() -> None:
    selected = profile("reader")
    s3_client = object()
    boto_session = Mock()
    boto_session.client.return_value = s3_client
    authenticated = SimpleNamespace(boto_session=boto_session)
    authenticator = Mock()
    authenticator.authenticate.return_value = authenticated
    status_signal = Mock()
    device_signal = Mock()
    signals = SimpleNamespace(status=status_signal, device=device_signal)
    load_buckets = Mock()
    window = SimpleNamespace(
        profiles={selected.name: selected},
        profile_combo=Mock(),
        service=object(),
        authenticated_profile=None,
        bucket_combo=Mock(),
        authenticator=authenticator,
        cancel_event=threading.Event(),
        auth_status=Mock(),
        _load_buckets=load_buckets,
    )
    window.profile_combo.currentText.return_value = selected.name

    def start_worker(function: Mock, result: Mock) -> None:
        result(function(signals))

    window._start_worker = start_worker

    MainWindow._sign_in(window)

    assert window.authenticated_profile == selected
    boto_session.client.assert_called_once_with("s3")
    load_buckets.assert_called_once_with()


def test_profile_change_reauthenticates_when_sso_session_is_shared() -> None:
    first = profile("reader")
    second = profile("analyst")
    sign_in = Mock()
    window = SimpleNamespace(
        authenticated_profile=first,
        service=object(),
        profiles={first.name: first, second.name: second},
        cancel_event=threading.Event(),
        bucket_combo=Mock(),
        auth_status=Mock(),
        _sign_in=sign_in,
    )

    MainWindow._profile_changed(window, second.name)

    assert window.service is None
    assert window.authenticated_profile is None
    window.bucket_combo.clear.assert_called_once_with()
    sign_in.assert_called_once_with()


def test_profile_change_requires_sign_in_for_a_different_sso_session() -> None:
    first = profile("reader")
    second = profile("analyst", start_url="https://other.awsapps.com/start")
    sign_in = Mock()
    window = SimpleNamespace(
        authenticated_profile=first,
        service=object(),
        profiles={first.name: first, second.name: second},
        cancel_event=threading.Event(),
        bucket_combo=Mock(),
        auth_status=Mock(),
        _sign_in=sign_in,
    )

    MainWindow._profile_changed(window, second.name)

    sign_in.assert_not_called()
    window.auth_status.setText.assert_called_once_with(
        "Profile changed; sign in to continue"
    )
