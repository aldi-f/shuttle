from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from shuttle_s3.s3 import (
    RemoteEntry,
    S3Service,
    TransferCancelled,
    _safe_relative_path,
)


class FakePaginator:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.pages


class FakeClient:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        if Key not in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "404", "Message": "Not Found"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadObject",
            )
        return {"ContentLength": len(self.objects[Key])}

    def get_paginator(self, operation: str) -> FakePaginator:
        assert operation == "list_objects_v2"
        return FakePaginator(
            [
                {
                    "Contents": [
                        {"Key": key, "Size": len(value)}
                        for key, value in self.objects.items()
                    ]
                }
            ]
        )

    def download_file(
        self,
        bucket: str,
        key: str,
        filename: str,
        Callback: Any,
    ) -> None:
        del bucket
        content = self.objects[key]
        Path(filename).write_bytes(content)
        Callback(len(content))


class FailingDownloadClient(FakeClient):
    def download_file(
        self,
        bucket: str,
        key: str,
        filename: str,
        Callback: Any,
    ) -> None:
        del bucket, key, filename, Callback
        raise OSError("download failed")


class NoListingClient(FakeClient):
    def get_paginator(self, operation: str) -> FakePaginator:
        raise AssertionError(f"{operation} should not be called for a loaded browser listing")


def test_download_plan_skips_existing_file_by_default(tmp_path: Path) -> None:
    (tmp_path / "one.csv").write_text("local", encoding="utf-8")
    service = S3Service(FakeClient({"reports/one.csv": b"remote", "reports/two.csv": b"two"}))

    plan = service.plan(
        bucket="data",
        source="reports/",
        destination=tmp_path,
        mode="download",
        overwrite=False,
    )

    assert [item.path.name for item in plan.downloads] == ["two.csv"]
    assert [item.path.name for item in plan.skipped] == ["one.csv"]


def test_mirror_plan_deletes_only_extra_local_files(tmp_path: Path) -> None:
    (tmp_path / "keep.csv").write_text("local", encoding="utf-8")
    (tmp_path / "extra.csv").write_text("extra", encoding="utf-8")
    service = S3Service(FakeClient({"reports/keep.csv": b"remote"}))

    plan = service.plan(
        bucket="data",
        source="reports/",
        destination=tmp_path,
        mode="mirror",
        overwrite=False,
    )

    assert [item.path.name for item in plan.deletions] == ["extra.csv"]
    assert [item.path.name for item in plan.skipped] == ["keep.csv"]


def test_execute_uses_atomic_temporary_download(tmp_path: Path) -> None:
    service = S3Service(FakeClient({"reports/new.csv": b"content"}))
    activity: list[str] = []
    plan = service.plan(
        bucket="data",
        source="reports/",
        destination=tmp_path,
        mode="download",
        overwrite=False,
    )

    result = service.execute(plan, cancel=threading.Event(), on_log=activity.append)

    assert result.downloaded == 1
    assert (tmp_path / "new.csv").read_bytes() == b"content"
    assert not (tmp_path / ".new.csv.shuttle-part").exists()
    assert activity == ["Downloaded: reports/new.csv"]


def test_exact_object_download_uses_file_name(tmp_path: Path) -> None:
    service = S3Service(FakeClient({"reports/one.csv": b"content"}))
    plan = service.plan(
        bucket="data",
        source="reports/one.csv",
        destination=tmp_path,
        mode="download",
        overwrite=False,
    )
    assert plan.downloads[0].path == tmp_path / "one.csv"


def test_mirror_refuses_filesystem_root() -> None:
    service = S3Service(FakeClient({"reports/one.csv": b"content"}))
    root = Path(Path.cwd().anchor)
    with pytest.raises(ValueError, match="filesystem root"):
        service.plan(
            bucket="data",
            source="reports/",
            destination=root,
            mode="mirror",
            overwrite=False,
        )


def test_mirror_does_not_delete_local_files_after_download_failure(tmp_path: Path) -> None:
    extra = tmp_path / "extra.csv"
    extra.write_text("keep me", encoding="utf-8")
    service = S3Service(FailingDownloadClient({"reports/new.csv": b"content"}))
    plan = service.plan(
        bucket="data",
        source="reports/",
        destination=tmp_path,
        mode="mirror",
        overwrite=False,
    )

    result = service.execute(plan, cancel=threading.Event())

    assert result.deleted == 0
    assert extra.exists()
    assert result.failed[-1].startswith("Mirror deletions were skipped")


def test_preview_honors_cancellation(tmp_path: Path) -> None:
    service = S3Service(FakeClient({"reports/new.csv": b"content"}))
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(TransferCancelled):
        service.plan(
            bucket="data",
            source="reports/",
            destination=tmp_path,
            mode="download",
            overwrite=False,
            cancel=cancel,
        )


def test_preview_reuses_complete_browser_listing(tmp_path: Path) -> None:
    service = S3Service(NoListingClient({}))
    plan = service.plan(
        bucket="data",
        source="reports/",
        destination=tmp_path,
        mode="download",
        overwrite=False,
        known_entries=[
            RemoteEntry(
                key="reports/one.csv",
                name="one.csv",
                is_prefix=False,
                size=7,
            )
        ],
    )

    assert plan.downloads[0].key == "reports/one.csv"


def test_timestamp_folder_with_colons_is_valid_on_posix() -> None:
    key = "2025-12-13T03:11:07/document.pdf"
    assert _safe_relative_path(key, windows=False) == Path(key)


def test_windows_invalid_characters_are_encoded_without_collisions() -> None:
    colon = _safe_relative_path("03:11/file?.pdf", windows=True)
    literal_encoding = _safe_relative_path("03%3A11/file%3F.pdf", windows=True)
    assert colon == Path("03%3A11/file%3F.pdf")
    assert literal_encoding == Path("03%253A11/file%253F.pdf")
    assert colon != literal_encoding


def test_download_now_streams_without_building_plan(tmp_path: Path) -> None:
    service = S3Service(FakeClient({"reports/one.csv": b"content"}))
    statuses: list[str] = []

    result = service.download_now(
        bucket="data",
        source="reports/",
        destination=tmp_path,
        overwrite=False,
        cancel=threading.Event(),
        on_status=statuses.append,
    )

    assert result.downloaded == 1
    assert (tmp_path / "one.csv").read_bytes() == b"content"
    assert statuses[-1] == "Downloaded: reports/one.csv"
