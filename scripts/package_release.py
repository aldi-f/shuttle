from __future__ import annotations

import argparse
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def platform_name() -> str:
    names = {"darwin": "macos", "linux": "linux", "win32": "windows"}
    try:
        return names[sys.platform]
    except KeyError:
        raise SystemExit(f"Unsupported build platform: {sys.platform}") from None


def architecture_name() -> str:
    machine = platform.machine().casefold()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    raise SystemExit(f"Unsupported build architecture: {machine}")


def application_version() -> str:
    return importlib.metadata.version("shuttle-s3")


def _pyinstaller_arguments(
    system: str,
    build_directory: Path,
    distribution_directory: Path,
) -> list[str]:
    arguments = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Shuttle",
        "--specpath",
        str(build_directory),
        "--workpath",
        str(build_directory / "work"),
        "--distpath",
        str(distribution_directory),
        "--paths",
        str(ROOT / "src"),
        "--collect-data",
        "botocore",
    ]
    # Windows and Linux are portable single-file applications. macOS uses an app
    # bundle both in its DMG and update archive.
    arguments.append("--onedir" if system == "macos" else "--onefile")
    if system == "windows":
        arguments.extend(["--icon", str(ROOT / "assets" / "branding" / "shuttle.ico")])
    if system == "macos":
        arguments.extend(["--osx-bundle-identifier", "com.github.aldi-f.shuttle"])
    arguments.append(str(ROOT / "src" / "shuttle_s3" / "__main__.py"))
    return arguments


def _windows_package_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) > 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Cannot convert {version!r} to an MSIX package version")
    return ".".join([*parts, *(["0"] * (4 - len(parts)))])


def _find_windows_sdk_tool(name: str) -> str:
    if tool := shutil.which(name):
        return tool
    kits = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    candidates = sorted((kits / "Windows Kits" / "10" / "bin").glob(f"*/x64/{name}"))
    if not candidates:
        raise RuntimeError(f"Could not find {name} in the Windows SDK")
    return str(candidates[-1])


def _build_windows_artifacts(
    executable: Path,
    output_directory: Path,
    artifact_stem: str,
) -> tuple[Path, Path]:
    portable = output_directory / f"{artifact_stem}.exe"
    shutil.copy2(executable, portable)

    package_root = executable.parent / "msix"
    package_root.mkdir()
    shutil.copy2(executable, package_root / "Shuttle.exe")
    shutil.copytree(
        ROOT / "packaging" / "windows" / "msix" / "Assets",
        package_root / "Assets",
    )
    manifest = (
        ROOT / "packaging" / "windows" / "msix" / "AppxManifest.xml.in"
    ).read_text(encoding="utf-8")
    manifest = manifest.replace("@VERSION@", _windows_package_version(application_version()))
    (package_root / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    msix = output_directory / f"{artifact_stem}.msix"
    subprocess.run(
        [
            _find_windows_sdk_tool("makeappx.exe"),
            "pack",
            "/d",
            str(package_root),
            "/p",
            str(msix),
            "/o",
        ],
        check=True,
    )
    return portable, msix


def _build_macos_artifacts(
    source: Path,
    output_directory: Path,
    artifact_stem: str,
) -> Path:
    update_archive = output_directory / f"{artifact_stem}.zip"
    installer = output_directory / f"{artifact_stem}.dmg"
    subprocess.run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(source),
            str(update_archive),
        ],
        check=True,
    )

    dmg_root = source.parent / "dmg"
    shutil.rmtree(dmg_root, ignore_errors=True)
    dmg_root.mkdir()
    shutil.copytree(source, dmg_root / source.name, symlinks=True)
    (dmg_root / "Applications").symlink_to("/Applications")
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            "Shuttle",
            "-srcfolder",
            str(dmg_root),
            "-ov",
            "-format",
            "UDZO",
            str(installer),
        ],
        check=True,
    )
    return installer


def build(output_directory: Path) -> Path:
    system = platform_name()
    architecture = architecture_name()
    build_directory = ROOT / "build"
    distribution_directory = ROOT / "dist"
    shutil.rmtree(build_directory, ignore_errors=True)
    shutil.rmtree(distribution_directory, ignore_errors=True)
    output_directory.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        _pyinstaller_arguments(system, build_directory, distribution_directory),
        cwd=ROOT,
        check=True,
    )

    artifact_stem = f"Shuttle-{system}-{architecture}"
    if system == "windows":
        destination, _msix = _build_windows_artifacts(
            distribution_directory / "Shuttle.exe",
            output_directory,
            artifact_stem,
        )
    elif system == "linux":
        source = distribution_directory / "Shuttle"
        destination = output_directory / artifact_stem
        shutil.copy2(source, destination)
        destination.chmod(destination.stat().st_mode | 0o111)
    else:
        source = distribution_directory / "Shuttle.app"
        destination = _build_macos_artifacts(source, output_directory, artifact_stem)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a native Shuttle release artifact")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts",
        help="directory that receives the packaged artifact",
    )
    arguments = parser.parse_args()
    artifact = build(arguments.output.resolve())
    size_mib = artifact.stat().st_size / (1024 * 1024)
    print(f"Created {artifact} ({size_mib:.1f} MiB)")
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with Path(github_output).open("a", encoding="utf-8") as output:
            output.write(f"artifact={artifact}\n")
            output.write(f"artifact_name={artifact.name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

