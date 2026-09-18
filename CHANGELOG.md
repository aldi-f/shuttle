# Changelog

All notable changes to Shuttle are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.0] - 2026-09-18

### Added

- Added a Microsoft Store MSIX package using Shuttle's registered Store identity.
- Added Microsoft Store listing artwork, screenshots, and application icons.

### Changed

- Windows GitHub releases are portable single-file applications again.
- Microsoft Store installations use Store-managed updates. Portable Windows
  installations notify users of new versions and open the GitHub release page
  for a manual download instead of replacing the running application.

## [0.7.0] - 2026-09-18

### Added

- Added a per-user Windows installer with Start menu integration and registered
  uninstallation.
- Added a conventional macOS DMG for installing Shuttle in `/Applications`.
- Added a persistent **Settings > Automatically check for updates** toggle.
- Added a small Windows update progress window with installation status and
  actionable failure messages.

### Changed

- Windows updates now run the verified installer instead of replacing a
  portable executable directly.
- Windows and macOS installed builds now keep application files on disk instead
  of extracting a one-file executable at every launch.

## [0.6.1] - 2026-09-18

### Changed

- Reset the bucket field to a selection prompt after authentication or profile
  changes, and automatically load the S3 root when a bucket is selected.

## [0.6.0] - 2026-09-18

### Added

- Persist IAM Identity Center login tokens until expiry, restore valid sessions
  when Shuttle starts, and automatically load buckets after authentication.

## [0.5.0] - 2026-09-18

### Added

- Added a **Select all** action for the files and folders currently shown in the
  S3 browser.
- Added a **Settings > Theme** menu for switching between light, dark, and
  automatic system themes. Light is the default for new installations.

### Changed

- Reload the current S3 folder after the Find field has been idle for one second,
  while continuing to filter already loaded entries immediately.
- Integrated S3 navigation, folder contents, selection controls, and search into
  one Explorer-style browse panel with up and reload icon actions.
- Made the S3 path navigation-only and required checkmarks to choose download
  sources.
- Required exactly one checked folder for mirror transfers.

### Fixed

- Reset checked browser items when navigating to a different S3 folder while
  preserving them during refreshes and fuzzy filtering in the same folder.

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

[Unreleased]: https://github.com/aldi-f/shuttle/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/aldi-f/shuttle/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/aldi-f/shuttle/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/aldi-f/shuttle/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/aldi-f/shuttle/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/aldi-f/shuttle/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/aldi-f/shuttle/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/aldi-f/shuttle/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/aldi-f/shuttle/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/aldi-f/shuttle/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/aldi-f/shuttle/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/aldi-f/shuttle/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/aldi-f/shuttle/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aldi-f/shuttle/releases/tag/v0.1.0
