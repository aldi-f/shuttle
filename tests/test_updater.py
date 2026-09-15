from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Any

import pytest

from shuttle_s3.updater import UpdateClient, _platform_asset, _version_tuple


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


def release(checksum: str) -> bytes:
    return json.dumps(
        {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/aldi-f/shuttle/releases/tag/v0.2.0",
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
    assert client.check("0.2.0", system="linux", machine="amd64") is None


def test_download_rejects_checksum_mismatch(tmp_path: Any, monkeypatch: Any) -> None:
    checksum = hashlib.sha256(b"expected").hexdigest()
    checksums = f"{checksum}  Shuttle-linux-amd64\n".encode()
    client = UpdateClient(FakeOpener([release(checksum), checksums, b"tampered"]))
    monkeypatch.setattr("tempfile.mkdtemp", lambda **_kwargs: str(tmp_path / "update"))
    update = client.check("0.1.0", system="linux", machine="amd64")

    with pytest.raises(RuntimeError, match="SHA-256"):
        client.download(update)
