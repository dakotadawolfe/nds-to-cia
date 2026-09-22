# Building version 1.0

The GitHub Actions workflow builds the ARM runtime on Linux, then the Windows
executable on a clean Windows runner. No game dump, system dump, key, private
configuration or checkout of another project is needed.

## Runtime

Use the container pinned in `.github/workflows/build.yml`:

```text
devkitpro/devkitarm@sha256:a998edf6b06416b5c053edbcd879abfa22b1b88e9cd3f267f5c4ee9fec71a93a
```

Follow the workflow's host-tool installation step, then run `bash build.sh`
from the repository root. `prepare.py` fetches the revisions in `sources.json`
and applies this repository's launcher, bridge, quiet-startup and per-title
storage changes. Build files stay in `.build-v2`; results go to `dist-v2`.

`build-info.json` records source revisions and every packaged file's SHA256.
`python -m unittest discover -s tests -v` runs the Python tests; Linux builds
also run the C/C++ tests for path resolution and interrupted-write recovery.

## Windows executable

On Windows x64 with Python 3.12:

1. Place the runtime build (or the `runtime-build` Actions artifact) in `dist-v2`.
2. Run `python -m pip install -r requirements-build.txt`.
3. Run `python scripts/build_windows.py`.

The result is `release/NDS-to-CIA.exe`. The bundle is assembled from an explicit
file list and excludes native system artwork, fonts, keys, title-ID registries,
user games and diagnostic logs. The EXE embeds its Python interpreter, Tk GUI,
crypto/import libraries, CIA-building tools and DS runtime. It does not need
Python installed on the user's PC.

Run the two packaged-executable tests from the workflow before running
`python scripts/package_release.py`. The release ZIP contains the EXE, bridge,
instructions, build metadata and license notices. The EXE and bridge are also
published separately for convenience.

## Command-line conversion

The windowed EXE supports automation with an explicit output and JSON report:

```text
NDS-to-CIA.exe game.nds --output game.cia --report result.json
NDS-to-CIA.exe homebrew.nds --output homebrew.cia --basic-banner --report result.json
```

It uses the same local profile as the GUI. `--state-dir DIRECTORY` selects an
isolated profile for testing. Callers should wait for process exit; a report's
`success` field and the exit code distinguish success from failure.

## Source archive and licenses

`scripts/source_archive.py` packages the tracked source and the original pinned
upstream archives. The patch recipe is applied at build time. Upstream license
texts accompany the binaries; see [THIRD_PARTY.md](THIRD_PARTY.md).

Never add system resources or test-game data to the source archive. Release
binaries are built in GitHub Actions so local usernames and workspace paths do
not enter compiled debug information. The runtime launcher ELF is stripped of
debug information before packaging.
