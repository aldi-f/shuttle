from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        return f"Shuttle-windows-{architecture}-setup.exe"
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
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
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


def _write_unix_helper(current: Path, replacement: Path, *, macos: bool) -> Path:
    directory = replacement.parent
    helper = directory / "install-update.sh"
    if macos:
        command = (
            'rm -rf -- "$current"\n'
            'mv -- "$replacement" "$current"\n'
            'open "$current"\n'
        )
    else:
        command = (
            'chmod +x "$replacement"\n'
            'mv -f -- "$replacement" "$current"\n'
            '"$current" &\n'
        )
    helper.write_text(
        "#!/bin/sh\n"
        'pid="$1"\n'
        'current="$2"\n'
        'replacement="$3"\n'
        'while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done\n'
        f"{command}"
        'rm -f -- "$0"\n',
        encoding="utf-8",
    )
    helper.chmod(0o700)
    subprocess.Popen(
        [str(helper), str(os.getpid()), str(current), str(replacement)],
        env=_restart_environment(),
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


def _write_windows_helper(installer: Path) -> Path:
    helper = installer.parent / "install-update.ps1"
    helper.write_text(
        "param($ProcessId, $Installer)\n"
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "Add-Type -AssemblyName System.Drawing\n"
        "[System.Windows.Forms.Application]::EnableVisualStyles()\n"
        "\n"
        "$form = New-Object System.Windows.Forms.Form\n"
        '$form.Text = "Shuttle Update"\n'
        "$form.ClientSize = New-Object System.Drawing.Size(360, 105)\n"
        "$form.FormBorderStyle = "
        "[System.Windows.Forms.FormBorderStyle]::FixedDialog\n"
        "$form.MaximizeBox = $false\n"
        "$form.MinimizeBox = $false\n"
        "$form.ControlBox = $false\n"
        "$form.StartPosition = "
        "[System.Windows.Forms.FormStartPosition]::CenterScreen\n"
        "$form.TopMost = $true\n"
        "\n"
        "$status = New-Object System.Windows.Forms.Label\n"
        "$status.AutoSize = $false\n"
        "$status.Location = New-Object System.Drawing.Point(20, 18)\n"
        "$status.Size = New-Object System.Drawing.Size(320, 24)\n"
        '$status.Text = "Waiting for Shuttle to close..."\n'
        "$form.Controls.Add($status)\n"
        "\n"
        "$progress = New-Object System.Windows.Forms.ProgressBar\n"
        "$progress.Location = New-Object System.Drawing.Point(20, 52)\n"
        "$progress.Size = New-Object System.Drawing.Size(320, 22)\n"
        "$progress.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee\n"
        "$progress.MarqueeAnimationSpeed = 25\n"
        "$form.Controls.Add($progress)\n"
        "\n"
        "$arguments = @(\n"
        '  "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"\n'
        ")\n"
        '$installed = Join-Path $env:LOCALAPPDATA "Programs\\Shuttle\\Shuttle.exe"\n'
        '$state = @{ Phase = "waiting"; InstallerProcess = $null }\n'
        "$timer = New-Object System.Windows.Forms.Timer\n"
        "$timer.Interval = 200\n"
        "$timer.Add_Tick({\n"
        '  if ($state.Phase -eq "waiting") {\n'
        "    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {\n"
        '      $state.Phase = "installing"\n'
        '      $status.Text = "Installing Shuttle update..."\n'
        "      try {\n"
        "        $state.InstallerProcess = Start-Process -FilePath $Installer "
        "-ArgumentList $arguments -PassThru -ErrorAction Stop\n"
        "      } catch {\n"
        "        $timer.Stop()\n"
        "        [System.Windows.Forms.MessageBox]::Show(\n"
        '          "Could not start the Shuttle installer.`n`n$($_.Exception.Message)",\n'
        '          "Shuttle Update",\n'
        "          [System.Windows.Forms.MessageBoxButtons]::OK,\n"
        "          [System.Windows.Forms.MessageBoxIcon]::Error\n"
        "        )\n"
        "        $form.Close()\n"
        "      }\n"
        "    }\n"
        '  } elseif ($state.Phase -eq "installing" -and '
        "$state.InstallerProcess.HasExited) {\n"
        "    $timer.Stop()\n"
        "    if ($state.InstallerProcess.ExitCode -eq 0) {\n"
        '      $status.Text = "Starting Shuttle..."\n'
        "      $form.Refresh()\n"
        "      Start-Process -FilePath $installed\n"
        "    } else {\n"
        "      [System.Windows.Forms.MessageBox]::Show(\n"
        '        "The Shuttle installer exited with code '
        '$($state.InstallerProcess.ExitCode).",\n'
        '        "Shuttle Update",\n'
        "        [System.Windows.Forms.MessageBoxButtons]::OK,\n"
        "        [System.Windows.Forms.MessageBoxIcon]::Error\n"
        "      )\n"
        "    }\n"
        "    $form.Close()\n"
        "  }\n"
        "})\n"
        "$form.Add_Shown({ $timer.Start() })\n"
        "[System.Windows.Forms.Application]::Run($form)\n"
        "Remove-Item -Force -LiteralPath $Installer -ErrorAction SilentlyContinue\n"
        "Remove-Item -Force -LiteralPath $MyInvocation.MyCommand.Path "
        "-ErrorAction SilentlyContinue\n",
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
            str(os.getpid()),
            str(installer),
        ],
        env=_restart_environment(),
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


def install_and_restart(download: Path) -> None:
    """Start a detached helper that replaces the frozen app after this process exits."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Automatic installation is available only in a packaged Shuttle app")

    if sys.platform == "darwin":
        current_app = _macos_app_path()
        extracted = download.parent / "extracted"
        extracted.mkdir()
        subprocess.run(["ditto", "-x", "-k", str(download), str(extracted)], check=True)
        replacement_app = extracted / "Shuttle.app"
        if not replacement_app.exists():
            raise RuntimeError("The macOS update does not contain Shuttle.app")
        _write_unix_helper(current_app, replacement_app, macos=True)
        return

    if sys.platform.startswith("linux"):
        _write_unix_helper(Path(sys.executable).resolve(), download, macos=False)
        return

    if sys.platform == "win32":
        _write_windows_helper(download)
        return
    raise RuntimeError(f"Unsupported update platform: {sys.platform}")

