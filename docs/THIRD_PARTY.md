# Third-party notices

Original converter code is provided under the MIT license in `LICENSE.txt`.
The DS bridge is GPL-2.0-or-later; the modified NTR Forwarder and nds-bootstrap
retain their upstream GPL licenses. Packaging them together does not replace
those licenses with MIT.

| Component | Source | License / notices |
| --- | --- | --- |
| YANBF launch components | https://github.com/YANBForwarder/YANBF | GPL-2.0; bridge derived under GPL-2.0-or-later |
| NTR Forwarder | https://github.com/RocketRobz/NTR_Forwarder | GPL-3.0; upstream bundled notices apply |
| nds-bootstrap | https://github.com/DS-Homebrew/nds-bootstrap | GPL-3.0; upstream bundled notices apply |
| makerom | https://github.com/3DSGuy/Project_CTR | MIT; includes mbedTLS and libyaml notices |
| bannertool | https://github.com/Epicpkmn11/bannertool | MIT |
| PyCTR | https://github.com/ihaveamac/pyctr | MIT |
| PyCryptodome | https://github.com/Legrandin/pycryptodome | BSD/public-domain components; bundled license |
| PyInstaller | https://github.com/pyinstaller/pyinstaller | GPL with bootloader exception; bundled license |
| Python and Tcl/Tk | https://www.python.org/ and https://www.tcl.tk/ | Their respective runtime license terms |

Runtime source revisions are fixed in `sources.json`. The release's corresponding
source archive includes those upstream snapshots plus the complete patch/build
recipe. CIA-building tool versions and checksums are fixed in `generator.py`.
The Windows dependency versions are pinned in `requirements-build.txt`.

License files collected during the build appear in the release ZIP's `licenses`
directory and inside the executable bundle. Original upstream attribution is
preserved. Nintendo's HOME Menu resources, system font, keys and commercial game
data are not distributed by this project; native banner resources must be
imported locally from the user's own dumps.
