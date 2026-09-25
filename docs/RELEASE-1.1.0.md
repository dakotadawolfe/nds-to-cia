# NDS to CIA 1.1.0

## Faster game startup

- Generated launchers reuse extracted game/runtime files of the expected size
  without scanning and checksumming the whole game on every launch.
- Missing or wrong-sized files are extracted again with streaming CRC and
  copy-error checks. Same-sized changes to prepared files are deliberately trusted.
- Optional PC preparation extracts the installed game/runtime files and creates
  the large work files before copying an SD/master folder to a card.

## Existing installed games

- The Windows EXE includes `--prepare-sd` and optional `--upgrade-launchers`
  commands. Python is not required. These need the owner's matching movable and
  boot9 files; see [Prepared SD folders](PREPARED_SD.md).
- The installed-launcher upgrade preserves game content, title IDs, artwork,
  settings and saves, backs up encrypted originals, and updates authenticated
  content metadata. Unsupported layouts stop without being rewritten.
- New conversions use the faster launcher automatically. Old CIAs do not change
  merely because the converter was updated.
- `Bridge.cia` is unchanged from 1.0.0; an existing bridge installation is sufficient.

## Downloads and validation

Use `NDS-to-CIA-1.1.0-Windows-x64.zip` for the executable, bridge, offline setup
guides and license notices. Separate executable and bridge downloads are also
available. `SHA256SUMS.txt` covers those files and the matching source archive.

The release is built from source in GitHub Actions, with ARM/runtime tests,
preparation and encrypted-update tests, and packaged Windows EXE startup,
conversion and invalid-input checks. The startup changes were also tested by
the project owner in the provisioning project before this standalone port.
No specific startup-time reduction or universal game compatibility is claimed.

Normal DS initialization still takes time. PC preparation uses additional space
for the extracted game, runtime and roughly 53 MiB of work files per title.
Nintendo game content, keys and system artwork are not included in this release.
