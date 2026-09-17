from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import certifi

REPOSITORY = "aldi-f/shuttle"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
USER_AGENT = "Shuttle updater"


@dataclass(frozen=True, slots=True)
class AvailableUpdate:
    version: str
    tag: str
    release_url: str
    asset_name: str
    asset_url: str
    sha256: str


def _version_tuple(version: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", version.strip())
    if match is None:
        raise ValueError(f"Unsupported release version: {version!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def _platform_asset(
    system: str | None = None,
    machine: str | None = None,
) -> str:
    system = (system or sys.platform).casefold()
    machine = (machine or platform.machine()).casefold()
    architecture = (
        "amd64"
        if machine in {"amd64", "x86_64"}
        else "arm64" if machine in {"arm64", "aarch64"} else None
    )
    if architecture is None:
        raise RuntimeError(f"Shuttle updates do not support architecture {machine!r}")
    if system.startswith("win"):
        return f"Shuttle-windows-{architecture}.exe"
    if system == "darwin":
        if architecture != "arm64":
            raise RuntimeError("Shuttle does not publish updates for Intel macOS")
        return "Shuttle-macos-arm64.zip"
    if system.startswith("linux"):
        return f"Shuttle-linux-{architecture}"
    raise RuntimeError(f"Shuttle updates do not support platform {system!r}")


class UpdateClient:
    def __init__(
        self,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if opener is None:
            context = ssl.create_default_context(cafile=certifi.where())
            opener = partial(urllib.request.urlopen, context=context)
        self._opener = opener

    def _get(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with self._opener(request, timeout=15) as response:
            return response.read()

    def check(
        self,
        current_version: str,
        *,
        system: str | None = None,
        machine: str | None = None,
    ) -> AvailableUpdate | None:
        release = json.loads(self._get(LATEST_RELEASE_URL))
        tag = release["tag_name"]
        if _version_tuple(tag) <= _version_tuple(current_version):
            return None

        assets = {asset["name"]: asset for asset in release.get("assets", [])}
        asset_name = _platform_asset(system, machine)
        if asset_name not in assets:
            raise RuntimeError(f"Release {tag} does not contain {asset_name}")
        if "SHA256SUMS" not in assets:
            raise RuntimeError(f"Release {tag} does not contain SHA256SUMS")

        checksums = self._get(assets["SHA256SUMS"]["browser_download_url"]).decode("utf-8")
        sha256 = ""
        for line in checksums.splitlines():
            checksum, _, filename = line.partition("  ")
            if filename.strip() == asset_name:
                sha256 = checksum.strip().casefold()
                break
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise RuntimeError(f"Release {tag} has no valid checksum for {asset_name}")
        return AvailableUpdate(
            version=tag.removeprefix("v"),
            tag=tag,
            release_url=release["html_url"],
            asset_name=asset_name,
            asset_url=assets[asset_name]["browser_download_url"],
            sha256=sha256,
        )

    def download(
        self,
        update: AvailableUpdate,
        *,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> Path:
        progress = on_progress or (lambda _done, _total, _name: None)
        request = urllib.request.Request(
            update.asset_url,
            headers={"User-Agent": USER_AGENT},
        )
        directory = Path(tempfile.mkdtemp(prefix="shuttle-update-"))
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / update.asset_name
        digest = hashlib.sha256()
        try:
            with self._opener(request, timeout=60) as response, destination.open("wb") as output:
                total = int(response.headers.get("Content-Length", 0))
                completed = 0
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    completed += len(chunk)
                    progress(completed, total, update.asset_name)
            if digest.hexdigest().casefold() != update.sha256:
                raise RuntimeError("The downloaded update failed SHA-256 verification")
            return destination
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise


def _installer_process_ids() -> tuple[int, ...]:
    process_ids = [os.getpid()]
    if os.environ.get("_PYI_APPLICATION_HOME_DIR"):
        parent_process_id = os.getppid()
        if parent_process_id > 1:
            process_ids.append(parent_process_id)
    return tuple(process_ids)


def _installer_log_path() -> Path:
    return Path(tempfile.gettempdir()) / "Shuttle-update.log"


def _write_unix_helper(
    current: Path,
    replacement: Path,
    *,
    macos: bool,
    process_ids: tuple[int, ...] | None = None,
) -> Path:
    directory = replacement.parent
    helper = directory / "install-update.sh"
    process_ids = process_ids or (os.getpid(),)
    log = _installer_log_path()
    if macos:
        command = (
            'backup="${current}.shuttle-backup"\n'
            'rm -rf "$backup"\n'
            'mv "$current" "$backup" || fail "Could not move the existing application."\n'
            'if mv "$replacement" "$current"; then\n'
            '  rm -rf "$backup"\n'
            'else\n'
            '  mv "$backup" "$current"\n'
            '  fail "Could not install the replacement application."\n'
            'fi\n'
            'open "$current" || fail "The update was installed but could not be opened."\n'
        )
    else:
        command = (
            'chmod +x "$replacement" || fail "Could not make the update executable."\n'
            'mv -f "$replacement" "$current" || fail "Could not install the update."\n'
            '"$current" >/dev/null 2>&1 &\n'
        )
    helper.write_text(
        "#!/bin/sh\n"
        'pids="$1"\n'
        'current="$2"\n'
        'replacement="$3"\n'
        'log="$4"\n'
        'exec >>"$log" 2>&1\n'
        'echo "Starting Shuttle update at $(date)"\n'
        'fail() {\n'
        '  echo "$1"\n'
        + (
            "  /usr/bin/osascript -e 'on run argv' "
            "-e 'display alert \"Shuttle update failed\" "
            "message \"See the installer log at \" & item 1 of argv' "
            "-e 'end run' \"$log\"\n"
            if macos
            else ""
        )
        + '  exit 1\n'
        '}\n'
        'for pid in $pids; do\n'
        '  while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done\n'
        'done\n'
        f"{command}"
        'echo "Shuttle update completed successfully."\n'
        'rm -f "$0"\n',
        encoding="utf-8",
    )
    helper.chmod(0o700)
    subprocess.Popen(
        [
            str(helper),
            " ".join(str(process_id) for process_id in process_ids),
            str(current),
            str(replacement),
            str(log),
        ],
        env=_restart_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return helper


def _restart_environment() -> dict[str, str]:
    """Return a clean environment for a new top-level PyInstaller process."""
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    original_library_path = environment.pop("LD_LIBRARY_PATH_ORIG", None)
    if original_library_path is None:
        environment.pop("LD_LIBRARY_PATH", None)
    else:
        environment["LD_LIBRARY_PATH"] = original_library_path
    return environment


def _write_windows_helper(
    current: Path,
    replacement: Path,
    *,
    process_ids: tuple[int, ...] | None = None,
) -> Path:
    helper = replacement.parent / "install-update.ps1"
    process_ids = process_ids or (os.getpid(),)
    log = _installer_log_path()
    helper.write_text(
        "param($ProcessIds, $Current, $Replacement, $Log)\n"
        '$ErrorActionPreference = "Stop"\n'
        "try {\n"
        '  "Starting Shuttle update at $(Get-Date)" | Set-Content -LiteralPath $Log\n'
        "  foreach ($ApplicationProcessId in $ProcessIds.Split(',')) {\n"
        "    while (Get-Process -Id $ApplicationProcessId "
        "-ErrorAction SilentlyContinue) {\n"
        "      Start-Sleep -Milliseconds 200\n"
        "    }\n"
        "  }\n"
        "  $deadline = (Get-Date).AddSeconds(60)\n"
        "  while ($true) {\n"
        "    try {\n"
        "      Copy-Item -Force -LiteralPath $Replacement -Destination $Current\n"
        "      break\n"
        "    } catch {\n"
        "      if ((Get-Date) -ge $deadline) { throw }\n"
        "      Start-Sleep -Milliseconds 200\n"
        "    }\n"
        "  }\n"
        "  Start-Process -FilePath $Current\n"
        '  "Shuttle update completed successfully." | Add-Content -LiteralPath $Log\n'
        "  Remove-Item -Force -LiteralPath $Replacement\n"
        "  Remove-Item -Force -LiteralPath $MyInvocation.MyCommand.Path\n"
        "} catch {\n"
        "  $_ | Out-String | Add-Content -LiteralPath $Log\n"
        "  Add-Type -AssemblyName PresentationFramework\n"
        "  [System.Windows.MessageBox]::Show("
        '"The update could not be installed. See the installer log at:`n$Log", '
        '"Shuttle update failed")\n'
        "}\n",
        encoding="utf-8",
    )
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            ",".join(str(process_id) for process_id in process_ids),
            str(current),
            str(replacement),
            str(log),
        ],
        env=_restart_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    return helper


def _macos_app_path() -> Path:
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    raise RuntimeError("Could not locate the running Shuttle.app bundle")


def _ensure_macos_app_is_updatable(application: Path) -> None:
    if "AppTranslocation" in application.parts:
        raise RuntimeError(
            "macOS is running Shuttle from a protected App Translocation location. "
            "Move Shuttle.app from Downloads to Applications, reopen it, and check "
            "for updates again."
        )


def install_and_restart(download: Path) -> None:
    """Start a detached helper that replaces the frozen app after this process exits."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Automatic installation is available only in a packaged Shuttle app")

    if sys.platform == "darwin":
        current_app = _macos_app_path()
        _ensure_macos_app_is_updatable(current_app)
        extracted = download.parent / "extracted"
        extracted.mkdir()
        subprocess.run(["ditto", "-x", "-k", str(download), str(extracted)], check=True)
        replacement_app = extracted / "Shuttle.app"
        if not replacement_app.exists():
            raise RuntimeError("The macOS update does not contain Shuttle.app")
        _write_unix_helper(
            current_app,
            replacement_app,
            macos=True,
            process_ids=_installer_process_ids(),
        )
        return

    if sys.platform.startswith("linux"):
        _write_unix_helper(
            Path(sys.executable).resolve(),
            download,
            macos=False,
            process_ids=_installer_process_ids(),
        )
        return

    if sys.platform == "win32":
        _write_windows_helper(
            Path(sys.executable).resolve(),
            download,
            process_ids=_installer_process_ids(),
        )
        return
    raise RuntimeError(f"Unsupported update platform: {sys.platform}")

