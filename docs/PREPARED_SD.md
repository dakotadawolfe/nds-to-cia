# Prepare an installed SD or master folder

This optional PC step avoids extracting the game and allocating large work files
on the console. Normal CIA creation and installation still work without it.
Use a copy of the complete SD folder, including its installed titles, with the
owner's matching `movable.sed` (or historical `moveable.sed`) at its root.
Supply the owner's `boot9.bin` separately. Neither file is included in the release.

The tool discovers installed DS Clean SD / NDS to CIA titles; it does not require
a fixed title list, console ID or game collection. It supports one matching
ID0/ID1 tree and the pinned bundled bootstrap. It stops on conflicting keys,
unsupported package layouts or mismatching existing immutable runtime files.

## Prepare titles made with version 1.1.0

From PowerShell, wait for the windowed EXE to exit and inspect the JSON report:

```powershell
$process = Start-Process -FilePath .\NDS-to-CIA.exe -ArgumentList '--prepare-sd "D:\Master Card" --boot9 "D:\Private\boot9.bin" --report "D:\Private\prepare-result.json"' -WindowStyle Hidden -Wait -PassThru
$process.ExitCode
Get-Content -LiteralPath 'D:\Private\prepare-result.json'
```

Exit code `0` and `"success": true` indicate completion. Copy the entire prepared
`Nintendo 3DS` folder onto the target card, keeping its matching encryption key
and normal console setup. Folder copying alone does not register titles or make
an encrypted dataset work on an unrelated console.

Preparation writes exact extracted game/runtime files under each title's
`data/00000000/` folder, plus 32 MiB RAM-dump space, 10 MiB overlay space,
a 6 MiB page file and a 4,967,424-byte initialized screenshot archive. This costs
another copy of the game plus runtime and work-file space. Existing saves,
settings and complete work files are preserved. Incomplete existing work files
are reported rather than deleted. Source package CRCs and staged readback are
checked on the PC, so that work does not delay the console's launch.

No played saves, screenshots, console settings, soft-reset state or physical-card
cluster addresses are imported. Small per-game files and runtime initialization
still happen on the console; this does not promise instant startup.

## Upgrade already-installed older launchers

Updating the converter EXE does not update existing game CIAs. Either rebuild
and reinstall them while preserving saves, or use the included upgrade command
on your PC copy. Choose a fresh backup directory:

```powershell
$process = Start-Process -FilePath .\NDS-to-CIA.exe -ArgumentList '--prepare-sd "D:\Master Card" --boot9 "D:\Private\boot9.bin" --upgrade-launchers --backup-dir "D:\Private\Original Launchers" --report "D:\Private\upgrade-result.json"' -WindowStyle Hidden -Wait -PassThru
$process.ExitCode
Get-Content -LiteralPath 'D:\Private\upgrade-result.json'
```

The upgrade retains game RomFS, title IDs, artwork, content sizes and compatible
access descriptors. It updates native launcher code and code-layout fields,
recalculates TMD hashes and CMD authentication, and verifies encrypted readback.
It backs up each title's encrypted originals before publication and rolls that
title back if publication fails. Successfully updated earlier titles remain
updated if a later title fails; rerunning recognizes already-updated launchers.

Only compatible single-content packages are accepted, and the new launcher must
fit the existing code allocation. If the tool refuses a package, rebuild its CIA
instead. Keep backups private; they contain the owner's installed content.

The hidden bridge is unchanged from 1.0.0. An existing installation of that bridge
does not need reinstalling for this launcher update.

## From source

With `pyctr==0.7.6` installed, the same tools can run as Python scripts:

```text
python scripts/prepare_ds_runtime.py --sd-root "Master Card" --boot9 boot9.bin --report preparation.json
python scripts/upgrade_ds_launcher.py --sd-root "Master Card" --boot9 boot9.bin --template-cia dist-v2/DS-Storage-Test.cia --backup-dir originals --report upgrade.json
```

Use the matching 1.1.0 build's test CIA as the launcher template. It contains only
the original homebrew storage probe; it is not copied into the master as a game.
