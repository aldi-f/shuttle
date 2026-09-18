from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import certifi
import pytest

from shuttle_s3.updater import (
    UpdateClient,
    _ensure_macos_app_is_updatable,
    _installer_process_ids,
    _platform_asset,
    _restart_environment,
    _version_tuple,
    _write_unix_helper,
    _write_windows_helper,
    install_and_restart,
)


class Response(BytesIO):
    def __init__(self, content: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(content)
        self.headers = headers or {}

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


class FakeOpener:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses

    def __call__(self, _request: Any, **_kwargs: Any) -> Response:
        return Response(self.responses.pop(0))


def test_default_opener_uses_certifi_ca_bundle(monkeypatch: Any) -> None:
    context = object()
    context_calls: list[str] = []
    opener_calls: list[dict[str, Any]] = []

    def create_context(*, cafile: str) -> object:
        context_calls.append(cafile)
        return context

    def open_url(_request: Any, **kwargs: Any) -> Response:
        opener_calls.append(kwargs)
        return Response(b"response")

    monkeypatch.setattr("shuttle_s3.updater.ssl.create_default_context", create_context)
    monkeypatch.setattr("shuttle_s3.updater.urllib.request.urlopen", open_url)

    client = UpdateClient()

    assert client._get("https://example.test") == b"response"
    assert context_calls == [certifi.where()]
    assert opener_calls == [{"timeout": 15, "context": context}]


def release(checksum: str) -> bytes:
    return json.dumps(
        {
            "tag_name": "v0.2.2",
            "html_url": "https://github.com/aldi-f/shuttle/releases/tag/v0.2.2",
            "assets": [
                {
                    "name": "Shuttle-linux-amd64",
                    "browser_download_url": "https://example.test/Shuttle-linux-amd64",
                },
                {
                    "name": "SHA256SUMS",
                    "browser_download_url": "https://example.test/SHA256SUMS",
                },
            ],
        }
    ).encode()


def test_platform_asset_names() -> None:
    assert _platform_asset("linux", "x86_64") == "Shuttle-linux-amd64"
    assert _platform_asset("win32", "AMD64") == "Shuttle-windows-amd64.exe"
    assert _platform_asset("darwin", "arm64") == "Shuttle-macos-arm64.zip"
    with pytest.raises(RuntimeError, match="Intel macOS"):
        _platform_asset("darwin", "x86_64")


def test_version_comparison_parser() -> None:
    assert _version_tuple("v1.2.3") > _version_tuple("1.2.2")
    with pytest.raises(ValueError):
        _version_tuple("latest")


def test_update_check_and_verified_download(tmp_path: Any, monkeypatch: Any) -> None:
    content = b"new Shuttle executable"
    checksum = hashlib.sha256(content).hexdigest()
    checksums = f"{checksum}  Shuttle-linux-amd64\n".encode()
    client = UpdateClient(FakeOpener([release(checksum), checksums, content]))
    monkeypatch.setattr("tempfile.mkdtemp", lambda **_kwargs: str(tmp_path / "update"))

    update = client.check("0.1.0", system="linux", machine="amd64")
    assert update is not None
    downloaded = client.download(update)

    assert downloaded.read_bytes() == content


def test_current_release_needs_no_checksum_request() -> None:
    client = UpdateClient(FakeOpener([release("0" * 64)]))
    assert client.check("0.2.2", system="linux", machine="amd64") is None


def test_download_rejects_checksum_mismatch(tmp_path: Any, monkeypatch: Any) -> None:
    checksum = hashlib.sha256(b"expected").hexdigest()
    checksums = f"{checksum}  Shuttle-linux-amd64\n".encode()
    client = UpdateClient(FakeOpener([release(checksum), checksums, b"tampered"]))
    monkeypatch.setattr("tempfile.mkdtemp", lambda **_kwargs: str(tmp_path / "update"))
    update = client.check("0.1.0", system="linux", machine="amd64")

    with pytest.raises(RuntimeError, match="SHA-256"):
        client.download(update)


def test_restart_environment_resets_pyinstaller_and_restores_library_path(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/tmp/old-mei")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/old-mei")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")

    environment = _restart_environment()

    assert environment["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert environment["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in environment


def test_installer_waits_for_application_and_pyinstaller_parent(monkeypatch: Any) -> None:
    monkeypatch.setattr("os.getpid", lambda: 123)
    monkeypatch.setattr("os.getppid", lambda: 456)
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/tmp/pyinstaller")

    assert _installer_process_ids() == (123, 456)


def test_windows_updates_require_manual_download(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr("shuttle_s3.updater.sys.frozen", True, raising=False)
    monkeypatch.setattr("shuttle_s3.updater.sys.platform", "win32")

    with pytest.raises(RuntimeError, match="downloaded manually"):
        install_and_restart(tmp_path / "Shuttle-windows-amd64.exe")


def test_macos_translocated_app_cannot_be_updated() -> None:
    application = Path(
        "/private/var/folders/random/AppTranslocation/ABC/d/Shuttle.app"
    )

    with pytest.raises(RuntimeError, match="Move Shuttle.app"):
        _ensure_macos_app_is_updatable(application)


def test_linux_helper_restarts_with_clean_environment(
    tmp_path: Path, monkeypatch: Any
) -> None:
    popen_calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda arguments, **kwargs: popen_calls.append((arguments, kwargs)),
    )

    helper = _write_unix_helper(
        tmp_path / "Shuttle",
        tmp_path / "Shuttle-linux-amd64",
        macos=False,
        process_ids=(123, 456),
    )

    script = helper.read_text(encoding="utf-8")
    assert '"$current" >/dev/null 2>&1 &' in script
    assert "exec >>\"$log\" 2>&1" in script
    assert popen_calls[0][0][1] == "123 456"
    assert popen_calls[0][1]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert popen_calls[0][1]["start_new_session"] is True
    assert popen_calls[0][1]["stdin"] is not None
    assert popen_calls[0][1]["stdout"] is not None
    assert popen_calls[0][1]["stderr"] is not None


def test_windows_helper_waits_then_replaces_and_restarts_portable_app(
    tmp_path: Path, monkeypatch: Any
) -> None:
    popen_calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda arguments, **kwargs: popen_calls.append((arguments, kwargs)),
    )

    helper = _write_windows_helper(
        tmp_path / "Shuttle.exe",
        tmp_path / "Shuttle-windows-amd64.exe",
        process_ids=(123, 456),
        log_directory=tmp_path / "settings",
    )
    script = helper.read_text(encoding="utf-8")

    assert "$ProcessIds.Split(',')" in script
    assert "System.Windows.Forms.ProgressBar" in script
    assert "ProgressBarStyle]::Marquee" in script
    assert 'Waiting for Shuttle to close...' in script
    assert 'Installing Shuttle update...' in script
    assert "Copy-Item -Force -LiteralPath $Replacement -Destination $Current" in script
    assert "Start-Process -FilePath $Current" in script
    assert popen_calls[0][0][-4] == "123,456"
    assert popen_calls[0][0][-1] == str(tmp_path / "settings" / "Shuttle-update.log")
    assert popen_calls[0][1]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
