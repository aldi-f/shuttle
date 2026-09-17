# Changelog

All notable changes to Shuttle are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-09-17

### Changed

- Applied a complete dark Fusion palette so text, controls, selection, and
  disabled states render consistently across supported platforms.

## [0.4.0] - 2026-09-17

### Fixed

- Made packaged application updates wait for the PyInstaller bootloader to exit
  and report detached installer failures instead of failing silently.
- Added an actionable warning when macOS App Translocation prevents Shuttle from
  replacing an application launched from Downloads.
- Stored the update installer log alongside Shuttle's saved settings.

## [0.3.2] - 2026-09-17

### Added

- Displayed the running Shuttle version in the bottom-right corner of the window.

## [0.3.1] - 2026-09-17

### Fixed

- Fixed update checks failing TLS certificate verification in packaged macOS
  applications by using a bundled CA certificate store.
- Standardized widget sizing and menu placement across macOS, Windows, and Linux.

## [0.3.0] - 2026-09-17

### Added

- Added checkboxes to the S3 browser for downloading multiple files and folders
  together.
- Added fuzzy file and folder search within the currently loaded S3 folder.
- Added a **Refresh & find** action that reloads the current folder from S3 and
  reapplies the active search.
- Added remote-to-local path mappings to transfer previews.

### Changed

- Moved **Run now** to the left side of the transfer action row.
- Limited detailed preview output to the first 250 items so large transfer
  previews remain responsive. All omitted items are still included in the
  transfer.

### Security

- **Run now** now requires explicit confirmation before starting a transfer
  without reviewing a preview.

## [0.2.2] - 2026-09-17

### Fixed

- Improved automatic update replacement behavior on Windows and Linux.

## [0.2.1] - 2026-09-16

### Fixed

- Reset the S3 browser when the selected bucket changes, preventing stale
  results from a previous bucket.

## [0.2.0] - 2026-09-15

### Added

- Added automatic release update checks, verified artifact downloads, and
  application restart after installation.
- Added a manual **Check for updates…** action.

## [0.1.0] - 2026-09-15

### Added

- Initial Shuttle desktop client.
- Added IAM Identity Center authentication and in-memory session handling.
- Added S3 bucket discovery, fuzzy bucket matching, and prefix browsing.
- Added download, overwrite, mirror, preview, cancellation, and saved-job
  workflows.
- Added native packaging and release automation.

[0.4.1]: https://github.com/aldi-f/shuttle/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/aldi-f/shuttle/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/aldi-f/shuttle/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/aldi-f/shuttle/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/aldi-f/shuttle/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/aldi-f/shuttle/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/aldi-f/shuttle/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/aldi-f/shuttle/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aldi-f/shuttle/releases/tag/v0.1.0
