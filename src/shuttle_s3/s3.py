from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from botocore.exceptions import ClientError

TransferAction = Literal["download", "skip", "delete"]
PlanStatusCallback = Callable[[str], None]


class TransferCancelled(RuntimeError):
    pass


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise TransferCancelled("Operation cancelled")


@dataclass(frozen=True, slots=True)
class RemoteEntry:
    key: str
    name: str
    is_prefix: bool
    size: int = 0
    modified: datetime | None = None


@dataclass(frozen=True, slots=True)
class PlanItem:
    action: TransferAction
    path: Path
    key: str | None = None
    size: int = 0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class TransferPlan:
    bucket: str
    source: str
    destination: Path
    mode: str
    items: tuple[PlanItem, ...]

    @property
    def downloads(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if item.action == "download")

    @property
    def deletions(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if item.action == "delete")

    @property
    def skipped(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if item.action == "skip")

    @property
    def download_bytes(self) -> int:
        return sum(item.size for item in self.downloads)


@dataclass(frozen=True, slots=True)
class TransferResult:
    downloaded: int
    skipped: int
    deleted: int
    failed: tuple[str, ...]


def _windows_safe_component(component: str) -> str:
    invalid = '<>:"\\|?*%'
    trailing_start = len(component.rstrip(" ."))
    encoded = "".join(
        f"%{ord(character):02X}"
        if character in invalid
        or ord(character) < 32
        or index >= trailing_start
        else character
        for index, character in enumerate(component)
    )
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
    if encoded.partition(".")[0].upper() in reserved:
        encoded = f"%5F{encoded}"
    return encoded


def _safe_relative_path(key: str, *, windows: bool | None = None) -> Path:
    parts = PurePosixPath(key).parts
    if not parts or any("\x00" in part for part in parts):
        raise ValueError(f"Unsafe object key cannot be written locally: {key!r}")
    use_windows_rules = os.name == "nt" if windows is None else windows
    safe_parts = [
        (
            _windows_safe_component(part)
            if use_windows_rules
            else "%2E" if part == "." else "%2E%2E" if part == ".." else part
        )
        for part in parts
    ]
    return Path(*safe_parts)


def _local_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for directory, subdirectories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        symlink_directories = [
            name for name in subdirectories if (directory_path / name).is_symlink()
        ]
        subdirectories[:] = [
            name for name in subdirectories if name not in symlink_directories
        ]
        for name in [*files, *symlink_directories]:
            yield directory_path / name


class S3Service:
    def __init__(self, client: Any) -> None:
        self.client = client

    def list_buckets(self, cancel: threading.Event | None = None) -> list[str]:
        _check_cancel(cancel)
        response = self.client.list_buckets()
        _check_cancel(cancel)
        return sorted(bucket["Name"] for bucket in response.get("Buckets", []))

    def list_prefix(
        self,
        bucket: str,
        prefix: str,
        cancel: threading.Event | None = None,
    ) -> list[RemoteEntry]:
        prefix = prefix.lstrip("/")
        paginator = self.client.get_paginator("list_objects_v2")
        entries: list[RemoteEntry] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
            _check_cancel(cancel)
            for item in page.get("CommonPrefixes", []):
                _check_cancel(cancel)
                key = item["Prefix"]
                name = key.removeprefix(prefix).rstrip("/")
                entries.append(RemoteEntry(key=key, name=name, is_prefix=True))
            for item in page.get("Contents", []):
                _check_cancel(cancel)
                key = item["Key"]
                if key == prefix or key.endswith("/"):
                    continue
                entries.append(
                    RemoteEntry(
                        key=key,
                        name=key.removeprefix(prefix),
                        is_prefix=False,
                        size=int(item.get("Size", 0)),
                        modified=item.get("LastModified"),
                    )
                )
        return sorted(entries, key=lambda item: (not item.is_prefix, item.name.casefold()))

    def _exact_object(self, bucket: str, key: str) -> dict[str, Any] | None:
        if not key or key.endswith("/"):
            return None
        try:
            return self.client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = error.response.get("Error", {}).get("Code")
            if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def _objects(
        self,
        bucket: str,
        prefix: str,
        cancel: threading.Event | None = None,
        on_status: PlanStatusCallback | None = None,
    ) -> Iterator[dict[str, Any]]:
        paginator = self.client.get_paginator("list_objects_v2")
        object_count = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            _check_cancel(cancel)
            page_objects = [
                item
                for item in page.get("Contents", [])
                if not item["Key"].endswith("/")
            ]
            object_count += len(page_objects)
            if on_status is not None:
                on_status(f"Listed {object_count} S3 object(s)…")
            for item in page_objects:
                _check_cancel(cancel)
                yield item

    def plan(
        self,
        *,
        bucket: str,
        source: str,
        destination: Path,
        mode: str,
        overwrite: bool,
        cancel: threading.Event | None = None,
        known_entries: list[RemoteEntry] | None = None,
        on_status: PlanStatusCallback | None = None,
    ) -> TransferPlan:
        status = on_status or (lambda _message: None)
        _check_cancel(cancel)
        source = source.lstrip("/")
        if not bucket:
            raise ValueError("Select a bucket")
        if not source:
            raise ValueError("Enter an object key or folder prefix")
        if mode not in {"download", "mirror"}:
            raise ValueError(f"Unknown transfer mode: {mode}")
        destination = destination.expanduser()
        if destination.exists() and not destination.is_dir():
            raise ValueError("The local destination must be a folder")
        if mode == "mirror":
            resolved_destination = destination.resolve()
            filesystem_root = Path(resolved_destination.anchor)
            if resolved_destination in {filesystem_root, Path.home().resolve()}:
                raise ValueError(
                    "For safety, mirror mode cannot target your home folder or a filesystem root"
                )

        status("Checking the selected S3 path…")
        exact = self._exact_object(bucket, source)
        _check_cancel(cancel)
        if exact is not None:
            if mode == "mirror":
                raise ValueError("Mirror mode requires a folder prefix, not a single object")
            objects = [{"Key": source, "Size": int(exact.get("ContentLength", 0))}]
            prefix = ""
            single = True
        else:
            prefix = source if source.endswith("/") else f"{source}/"
            if known_entries is not None and all(
                not entry.is_prefix and entry.key.startswith(prefix)
                for entry in known_entries
            ):
                status("Using the objects already loaded in the S3 browser…")
                objects = [
                    {"Key": entry.key, "Size": entry.size}
                    for entry in known_entries
                ]
            else:
                status("Listing all S3 objects under the selected folder…")
                objects = list(self._objects(bucket, prefix, cancel, status))
            single = False
            if not objects:
                raise ValueError("No object or folder was found at that S3 path")

        items: list[PlanItem] = []
        remote_paths: set[Path] = set()
        status(f"Comparing {len(objects)} remote object(s) with local files…")
        for item in objects:
            _check_cancel(cancel)
            key = item["Key"]
            relative_key = PurePosixPath(key).name if single else key.removeprefix(prefix)
            relative = _safe_relative_path(relative_key)
            remote_paths.add(relative)
            local_path = destination / relative
            if local_path.exists() and not overwrite:
                items.append(
                    PlanItem(
                        action="skip",
                        path=local_path,
                        key=key,
                        size=int(item.get("Size", 0)),
                        reason="Local file already exists",
                    )
                )
            else:
                items.append(
                    PlanItem(
                        action="download",
                        path=local_path,
                        key=key,
                        size=int(item.get("Size", 0)),
                    )
                )

        if mode == "mirror":
            status("Scanning the local destination for mirror deletions…")
            for local_path in _local_files(destination):
                _check_cancel(cancel)
                relative = local_path.relative_to(destination)
                if relative not in remote_paths:
                    items.append(
                        PlanItem(
                            action="delete",
                            path=local_path,
                            reason="Not present in S3",
                        )
                    )
        _check_cancel(cancel)
        status("Finalizing transfer preview…")
        return TransferPlan(
            bucket=bucket,
            source=source,
            destination=destination,
            mode=mode,
            items=tuple(items),
        )

    def execute(
        self,
        plan: TransferPlan,
        *,
        cancel: threading.Event,
        on_progress: Callable[[int, int, str], None] | None = None,
        on_log: PlanStatusCallback | None = None,
    ) -> TransferResult:
        progress = on_progress or (lambda _done, _total, _key: None)
        log = on_log or (lambda _message: None)
        completed_bytes = 0
        failures: list[str] = []
        downloaded = 0
        deleted = 0
        total_bytes = plan.download_bytes

        for item in plan.downloads:
            if cancel.is_set():
                raise TransferCancelled("Transfer cancelled")
            item.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = item.path.with_name(f".{item.path.name}.shuttle-part")
            current_object_bytes = 0
            base_completed = completed_bytes
            item_key = item.key or ""

            def callback(
                delta: int,
                base_completed: int = base_completed,
                item_key: str = item_key,
            ) -> None:
                nonlocal current_object_bytes
                if cancel.is_set():
                    raise TransferCancelled("Transfer cancelled")
                current_object_bytes += delta
                progress(base_completed + current_object_bytes, total_bytes, item_key)

            try:
                self.client.download_file(
                    plan.bucket,
                    item.key,
                    str(temporary),
                    Callback=callback,
                )
                temporary.replace(item.path)
                completed_bytes += item.size
                downloaded += 1
                log(f"Downloaded: {item.key}")
            except TransferCancelled:
                temporary.unlink(missing_ok=True)
                raise
            except Exception as error:  # Continue independent downloads and report all failures.
                temporary.unlink(missing_ok=True)
                failures.append(f"{item.key}: {error}")

        if failures and plan.deletions:
            failures.append(
                "Mirror deletions were skipped because one or more downloads failed"
            )
            deletions: tuple[PlanItem, ...] = ()
        else:
            deletions = plan.deletions

        if cancel.is_set():
            raise TransferCancelled("Transfer cancelled")
        for item in deletions:
            try:
                if item.path.is_dir() and item.path.is_symlink():
                    item.path.unlink()
                else:
                    item.path.unlink(missing_ok=True)
                deleted += 1
                log(f"Deleted: {item.path}")
            except OSError as error:
                failures.append(f"{item.path}: {error}")

        if plan.mode == "mirror" and not failures and plan.destination.exists():
            for directory, _subdirectories, _files in os.walk(
                plan.destination, topdown=False, followlinks=False
            ):
                path = Path(directory)
                if path != plan.destination:
                    try:
                        path.rmdir()
                    except OSError:
                        pass
        for item in plan.skipped:
            log(f"Skipped existing file: {item.key}")
        return TransferResult(
            downloaded=downloaded,
            skipped=len(plan.skipped),
            deleted=deleted,
            failed=tuple(failures),
        )

    def download_now(
        self,
        *,
        bucket: str,
        source: str,
        destination: Path,
        overwrite: bool,
        cancel: threading.Event,
        known_entries: list[RemoteEntry] | None = None,
        on_status: PlanStatusCallback | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> TransferResult:
        """Stream a download without first materializing a complete transfer plan."""
        status = on_status or (lambda _message: None)
        progress = on_progress or (lambda _done, _total, _key: None)
        source = source.lstrip("/")
        if not bucket:
            raise ValueError("Select a bucket")
        if not source:
            raise ValueError("Enter an object key or folder prefix")
        destination = destination.expanduser()
        if destination.exists() and not destination.is_dir():
            raise ValueError("The local destination must be a folder")

        status("Checking the selected S3 path…")
        exact = self._exact_object(bucket, source)
        _check_cancel(cancel)
        if exact is not None:
            prefix = ""
            single = True
            objects: Iterator[dict[str, Any]] = iter(
                [{"Key": source, "Size": int(exact.get("ContentLength", 0))}]
            )
        else:
            prefix = source if source.endswith("/") else f"{source}/"
            single = False
            if known_entries is not None and all(
                not entry.is_prefix and entry.key.startswith(prefix)
                for entry in known_entries
            ):
                status("Using the objects already loaded in the S3 browser…")
                objects = iter(
                    {"Key": entry.key, "Size": entry.size}
                    for entry in known_entries
                )
            else:
                status("Downloading objects as S3 listing pages arrive…")
                objects = self._objects(bucket, prefix, cancel, status)

        downloaded = 0
        skipped = 0
        found = 0
        failures: list[str] = []
        for item in objects:
            _check_cancel(cancel)
            found += 1
            key = item["Key"]
            relative_key = PurePosixPath(key).name if single else key.removeprefix(prefix)
            local_path = destination / _safe_relative_path(relative_key)
            if local_path.exists() and not overwrite:
                skipped += 1
                status(f"Skipped existing file: {key}")
                continue

            local_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = local_path.with_name(f".{local_path.name}.shuttle-part")
            current_bytes = 0

            def callback(delta: int, item_key: str = key) -> None:
                nonlocal current_bytes
                _check_cancel(cancel)
                current_bytes += delta
                progress(current_bytes, 0, item_key)

            status(f"Downloading: {key}")
            try:
                self.client.download_file(
                    bucket,
                    key,
                    str(temporary),
                    Callback=callback,
                )
                temporary.replace(local_path)
                downloaded += 1
                status(f"Downloaded: {key}")
            except TransferCancelled:
                temporary.unlink(missing_ok=True)
                raise
            except Exception as error:
                temporary.unlink(missing_ok=True)
                failures.append(f"{key}: {error}")

        if not found:
            raise ValueError("No object or folder was found at that S3 path")
        return TransferResult(
            downloaded=downloaded,
            skipped=skipped,
            deleted=0,
            failed=tuple(failures),
        )


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"

