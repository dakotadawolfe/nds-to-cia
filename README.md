# NDS to CIA

Turn your Nintendo DS game dump into a self-contained Nintendo 3DS HOME Menu
title. Each CIA includes the game and its launch files. After installation,
there is no loose `.nds` file or shared `_nds` folder to maintain on the SD card.

**[Download version 1.1.0](https://github.com/dakotadawolfe/nds-to-cia/releases/tag/v1.1.0)** ·
[Native banner setup](docs/NATIVE_BANNER.md) · [Build from source](docs/BUILDING.md)

## What you get

- A Windows x64 converter with a graphical interface; Python is not required.
- A separate `Bridge.cia`, installed once per console.
- One CIA per game, with the original DS icon, name and publisher.
- The native animated DS cartridge presentation after a one-time local resource import.
- Quiet startup and per-game runtime files, settings and saves.

This runs games through nds-bootstrap in DS mode. It is not a DS emulator or a
retail Nintendo installation format. Game compatibility follows the included
runtime and the limits below.

## Requirements

- Windows 10/11, 64-bit, for the release executable.
- A 3DS/2DS family console with working custom firmware and DS mode.
- FBI or another compatible CIA installer.
- Your own complete `.nds` dump. See the
  [GodMode9 dumping guide](https://3ds.hacks.guide/dumping-titles-and-game-cartridges.html).
- Free SD space for the installed CIA content **plus another copy of the game**,
  per-game runtime files, about 53 MiB of work files, and saves/caches.

## Quick start

### 1. Install the bridge once

1. Download and extract `NDS-to-CIA-1.1.0-Windows-x64.zip` from the release page.
2. Copy `Bridge.cia` to the console's SD card.
3. Open FBI, browse to that file, and select **Install CIA**.
4. After successful installation, remove the installation file if desired.

The bridge is a hidden internal title: **no HOME Menu icon appears**. Do not
launch it manually. It is title `0004800544435332` and installs to TWL NAND.
It is shared by all games made with this tool and needs installing only once,
unless it is removed or the console's NAND is restored/reset.

### 2. Create a game CIA on Windows

1. Open `NDS-to-CIA.exe`.
2. For the native cartridge banner, click **Banner setup…** and complete the
   [one-time resource import](docs/NATIVE_BANNER.md). Alternatively, choose
   **Simple icon** to build immediately without system resources.
3. Select your `.nds` file and choose a new output `.cia` filename.
4. Click **Create CIA** and wait for the completion message.

You can also drop a `.nds` file onto the EXE to preselect it. Existing output
files are not overwritten. A small JSON receipt is saved beside each CIA.

### 3. Install and play

1. Copy the generated CIA onto your SD card and install it with FBI.
2. Return to HOME Menu. The game appears with its original icon and name.
3. Launch the game and allow its initial setup to complete. The screens remain
   blank while the title extracts its files and enters DS mode; the first
   launch can take a minute or longer depending on the game and SD card.
4. After installation, the input `.nds` and installation `.cia` do not need to
   remain on the console's SD card. Keep your originals backed up on your PC.

Version 1.1.0 reuses extracted files based on their expected sizes, without
reading and checksumming the entire game on every launch. Missing or wrong-sized
files are extracted again. Same-sized changes are trusted.

For the shortest first launch, optionally [prepare the installed SD/master folder
on your PC](docs/PREPARED_SD.md). This also preallocates the large work files.
Existing games keep their old launchers until rebuilt or upgraded; updating the
Windows converter alone does not change installed games.
Reinstalling a CIA can trigger setup again. **Back up saves before updating,
reinstalling or uninstalling a generated title.**

## Storage and saves

The generated title owns its files inside:

```text
Nintendo 3DS/<ID0>/<ID1>/title/00040000/<title-low>/data/00000000/
```

`0000000a/00000000.sav` is the normal DS save. Back up the entire managed
directory when possible, especially before reinstalling or moving SD contents.
These extra files are not standard 3DS save archives; do not assume a normal
3DS save manager or installer preserves them.

The managed ROM is a raw `.bin`, not encrypted or copy-protected. The CIA and
extracted runtime both occupy space. Generated titles require no shared `_nds`
folder, but this tool does not remove files required by custom firmware or
other applications. Keep the boot files your console setup needs.

On Windows, imported artwork and the title-ID registry live in
`%LOCALAPPDATA%\nds-to-cia`. Keep that folder when updating the converter so the
same dumps retain their assigned title IDs. Your input dumps are read locally;
the application does not upload them or collect telemetry.

## Native banner resources

The native display uses artwork from your own HOME Menu dump and the standard
system font. Neither those resources nor Nintendo keys are included in the
release. Import them once with the GUI; they are embedded in each generated
CIA and are not needed as separate SD files.

See [Native banner setup](docs/NATIVE_BANNER.md) for the dump/import process.
**Simple icon** mode is always available without this import.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No icon after installing `Bridge.cia` | Expected: only game CIAs create HOME Menu icons. |
| Game returns to HOME Menu or stays black | Confirm the bridge is installed, DS mode works, the dump is complete, and the SD card has enough free space. |
| First launch is slow | Extraction and work-file creation happen silently. Use optional PC preparation to move this work off the console. Normal DS initialization still runs. |
| Native banner setup fails | Use the HOME Menu CIA and standard font CIA from your own console. Encrypted dumps also require your boot9 dump; fully decrypted CIAs do not. |
| Existing output error | Choose a new CIA filename. The tool does not replace existing output files. |
| Save disappeared after reinstall | Restore the backed-up managed save. Installer behavior can recreate the title's data folder. |
| Need a diagnostic log | The title's `00000006.bin` is a text log. It can contain SD paths and console directory identifiers; redact those before sharing publicly. |

The Windows executable is unsigned. Checksums are provided in `SHA256SUMS.txt`;
Windows may display an unknown-publisher prompt.

## Compatibility and current limits

- Intended for DS cartridge dumps and compatible DS homebrew; not DSiWare.
- Native banners use the English title and the base icon bitmap; animated DSi
  icon sequences are not reproduced. The cartridge itself remains animated.
- Native title text supports the system font and up to three lines. Text that
  exceeds the original pane is rejected rather than clipped silently.
- Optional widescreen, external compatibility packs and per-game startup menus
  are not included.
- On-console testing confirmed the native banner, game startup, saving,
  reopening and sleep with Super Mario 64 DS. This is not a compatibility claim
  for every game or every console model.
- The 1.1 desktop build is tested for GUI startup and end-to-end CIA creation;
  each newly generated game's compatibility still requires console testing.

## Source and credits

The repository contains only the converter, launcher, bridge, runtime patch
recipe and tests. It does not require another firmware project. The release
includes a source archive with the pinned upstream sources used for the build.

Built on [YANBF](https://github.com/YANBForwarder/YANBF),
[NTR Forwarder](https://github.com/RocketRobz/NTR_Forwarder),
[nds-bootstrap](https://github.com/DS-Homebrew/nds-bootstrap),
[Project CTR](https://github.com/3DSGuy/Project_CTR),
[bannertool](https://github.com/Epicpkmn11/bannertool), and
[PyCTR](https://github.com/ihaveamac/pyctr).
[NDSForwarder](https://github.com/MechanicalDragon0687/ndsForwarder) provided
the reference for the native DS presentation.

See [LICENSE.txt](LICENSE.txt) and [third-party notices](docs/THIRD_PARTY.md).
This is an independent homebrew project, not affiliated with Nintendo.
