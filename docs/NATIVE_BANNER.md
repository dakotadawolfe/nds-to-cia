# Native cartridge banner setup

Do this once on your PC. The converter needs the DS cartridge artwork from
HOME Menu and the standard system font from your own console. It never changes
those installed system titles. No shared `_nds` directory is required.

## Obtain your system dumps

Use GodMode9's title manager to export **HOME Menu** and the **standard system
font** to CIA files. The standard font title ID is `0004009B00014002`.
HOME Menu's title ID depends on the console's region; select the title by its
name instead of copying another region's ID.

Follow the [installed-title dumping instructions](https://3ds.hacks.guide/dumping-titles-and-game-cartridges.html#dumping-an-installed-title).
In GodMode9, open the HOME action menu, choose **Title manager**, select the
system-title location, then choose **Manage Title… → Build CIA (standard)** for
each title. The output is placed in `gm9/out`.

For a key-free import on the PC, use GodMode9's **CIA image options → Decrypt to
0:/gm9/out** on copies of those dumps. See the
[CIA decryption instructions](https://3ds.hacks.guide/dumping-titles-and-game-cartridges.html#encrypting-decrypting-a-cia-file).
Keep the original dumps separate and use the fully decrypted copies for import.

Alternatively, select your own `boot9.bin` alongside encrypted dumps. This file
is read only to decrypt the resources. The app does not copy it into its
profile, generated CIA, release package or repository. Do not upload it to an
issue or include it when sharing logs.

## Import on Windows

1. Open `NDS-to-CIA.exe` and select **Banner setup…**.
2. Select the HOME Menu CIA and the standard system font CIA.
3. Leave the boot9 field empty for fully decrypted CIAs, or select your boot9
   dump if the inputs are encrypted.
4. Select **Import resources**.

Once setup completes, leave **Native DS cartridge** selected when creating
games. The imported resources are stored under
`%LOCALAPPDATA%\nds-to-cia\native-assets` on this PC.

The importer expects HOME Menu's `BannerDS_LZ.bin` and `cbf_std.bcfnt.lz`.
Resource layouts from other system versions/regions may differ; an unsupported
layout produces an error. **Simple icon** mode works without these resources.

## Developer CLI

```text
python -m pip install pyctr==0.7.6
python prepare_native_banner.py --home-menu HOME-MENU.cia --font SYSTEM-FONT.cia --output native-assets
```

Add `--boot9 boot9.bin` for encrypted inputs. Do not commit `native-assets` or
any of the input dumps. The public build and automated tests use synthetic
fixtures and the original homebrew storage probe instead.
