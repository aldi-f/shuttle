# Shuttle — an S3 client

Shuttle is a cross-platform desktop application for people who need to browse,
download, and mirror Amazon S3 folders without using the AWS CLI. It reads AWS
IAM Identity Center profiles from the standard AWS config file and performs a
fresh browser-based sign-in for every application session. Tokens and temporary
AWS credentials are kept in memory only.

## Current features

- Discovers modern `sso_session` and legacy IAM Identity Center profiles.
- Performs standalone OIDC device authorization in the user's default browser.
- Reuses one in-memory Identity Center login across compatible SSO profiles.
- Lists accessible buckets with fuzzy name matching and browses S3 prefixes.
- Downloads an object or recursively downloads a prefix.
- Can stream downloads immediately with **Run now**, without a complete preview.
- Optionally overwrites existing files.
- Mirrors a prefix, with a preview and explicit deletion confirmation.
- Displays planning and transfer progress and supports cancellation.
- Saves non-secret job inputs as JSON for quick reuse.

## Development

Shuttle requires Python 3.11 or newer.

PySide6 uses native desktop libraries on Linux. Install Qt's XCB cursor
dependency before launching Shuttle on Ubuntu or Linux Mint:

```shell
sudo apt install libxcb-cursor0
```

Equivalent packages are named `xcb-util-cursor` on Arch Linux and
`xcb-util-cursor` on Fedora.

```shell
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m shuttle_s3
```

Run the tests and linter with:

```shell
pytest
ruff check .
```

## IAM Identity Center profile

Shuttle reads `~/.aws/config`. A modern profile looks like:

```ini
[profile analyst]
sso_session = company
sso_account_id = 123456789012
sso_role_name = BusinessAnalyst
region = eu-west-1

[sso-session company]
sso_start_url = https://example.awsapps.com/start
sso_region = eu-west-1
sso_registration_scopes = sso:account:access
```

The AWS CLI does not need to be installed and Shuttle does not use its SSO token
cache. The profile itself must already exist because it identifies the company's
start URL, account, role, and regions.

Profiles with the same IAM Identity Center start URL and SSO region share one
in-memory browser login. Shuttle still requests separate temporary AWS
credentials for each profile's account and role. The shared login is forgotten
when Shuttle closes and is never written to disk.

## Updates

Packaged builds check the repository's latest GitHub Release shortly after
startup. When a newer version is available, Shuttle offers to download the
matching platform artifact, verifies it against the release's `SHA256SUMS`,
then replaces the portable executable or app bundle and restarts.

The update check runs in the background and update prompts wait until active
operations finish. Use **Help > Check for updates…** to check manually. Source
development runs can detect releases, but only packaged PyInstaller builds can
install an update automatically.

Updates rely on GitHub HTTPS and release checksums; the artifacts are not yet
code-signed.

## Saved jobs

Saved jobs contain non-secret inputs and options only. They are stored in:

- Linux: `~/.local/share/Shuttle/Shuttle/jobs.json`
- Windows: `%APPDATA%\Shuttle\Shuttle\jobs.json`
- macOS: `~/Library/Application Support/Shuttle/Shuttle/jobs.json`

Transfer activity logs are currently kept in the application window only and
are not persisted after Shuttle exits.

## Mirror safety

Mirror mode treats the selected local destination as the root of the selected S3
prefix. Local files absent from S3 are deleted. Shuttle always creates a plan
first, displays every deletion, and asks for confirmation immediately before
execution. Symlinked directories are never traversed.

Mirror mode cannot bypass its inventory step because Shuttle must compare the
complete remote and local file sets before deleting anything. **Run now**
performs that safety scan and proceeds automatically. In download mode,
**Run now** starts transferring objects as soon as the first S3 listing page
arrives.

## Development commands

The Makefile keeps common local and CI commands consistent:

```shell
make install-dev
make check
make run
make build
```

`make build` creates a native artifact for the current operating system and
architecture under `artifacts/`. Native builds cannot be cross-compiled, so run
the target on each corresponding operating system.

## Packaging and releases

Install the build extra and run:

```shell
python -m pip install -e ".[build]"
python scripts/package_release.py
```

PyInstaller's one-file mode is convenient for portable Windows builds but starts
more slowly because it extracts at launch. A signed installer is recommended for
managed distribution. macOS builds must be produced on macOS, and Windows builds
on Windows.

Pushing a tag beginning with `v`, such as `v0.1.0`, triggers the
`Build release` GitHub Actions workflow. It runs tests, builds these native
artifacts, and attaches them to a GitHub Release:

- `Shuttle-linux-amd64`
- `Shuttle-windows-amd64.exe`
- `Shuttle-macos-arm64.zip`

Create and push a release tag with:

```shell
git tag v0.1.0
git push origin v0.1.0
```

The macOS artifacts are currently unsigned. Users may need to approve the app
through macOS Privacy & Security until code signing and notarization are
configured.

