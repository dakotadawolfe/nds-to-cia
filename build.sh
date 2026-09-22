#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$DEVKITPRO/tools/bin:$DEVKITARM/bin:$PATH"
python3 prepare.py
mkdir -p .build-v2/tools dist-v2/runtime dist-v2/data dist-v2/tools dist-v2/licenses

# The DS bridge uses the upstream SRL packager.
curl -fsSL https://github.com/ihaveamac/ctr_toolkit/releases/download/make_cia6.4builds/make_cia6.4builds.zip -o .build-v2/tools/make_cia.zip
python3 -c "import hashlib; assert hashlib.sha256(open('.build-v2/tools/make_cia.zip','rb').read()).hexdigest() == '610270542e0c94a8861e2dd279aa4f509249c9fc566cd8db82754c0de54f2af3'"
python3 -c "import zipfile; zipfile.ZipFile('.build-v2/tools/make_cia.zip').extractall('.build-v2/tools/make_cia')"
chmod +x .build-v2/tools/make_cia/linux/make_cia
export PATH="$PWD/.build-v2/tools/make_cia/linux:$PATH"

make -C .build-v2/yanbf forwarder bootstrap -j2
make -C .build-v2/forwarder/SD_Card/sd bootloader bootstub
make -C .build-v2/forwarder/SD_Card/sd -j2
gcc .build-v2/bootstrap/lzss.c -o .build-v2/tools/lzss
export PATH="$PWD/.build-v2/tools:$PATH"
make -C .build-v2/bootstrap package-release

cp .build-v2/yanbf/forwarder/forwarder.elf dist-v2/data/launcher.elf
cp .build-v2/yanbf/generator/data/build-cia.rsf dist-v2/data/build-cia.rsf
cp .build-v2/yanbf/generator/data/dsboot.wav dist-v2/data/dsboot.wav
python3 launch_logo.py .build-v2/makerom/makerom/src/ncch_logo.h dist-v2/data/blank-logo.lz
cp .build-v2/yanbf/bootstrap/bootstrap.cia dist-v2/runtime/bridge.cia
cp .build-v2/forwarder/SD_Card/sd/sdcard.nds dist-v2/runtime/sdcard.nds
cp .build-v2/bootstrap/bin/nds-bootstrap-release.nds dist-v2/runtime/
cp .build-v2/bootstrap/bin/nds-bootstrap-hb-release.nds dist-v2/runtime/
cp generator.py banner.py native_banner.py prepare_native_banner.py launch_logo.py verify.py README.md sources.json LICENSE.txt dist-v2/
mkdir -p dist-v2/assets
cp assets/blank-logo-auth.json dist-v2/assets/
arm-none-eabi-strip --strip-debug dist-v2/data/launcher.elf
cp .build-v2/bootstrap/LICENSE dist-v2/licenses/nds-bootstrap.txt
cp .build-v2/yanbf/README.md dist-v2/licenses/YANBF.md
cp .build-v2/yanbf/license.txt dist-v2/licenses/YANBF.txt
cp '.build-v2/forwarder/SuperCard DSTWO/twlnand/License.txt' dist-v2/licenses/NTR-Forwarder.txt
cp .build-v2/forwarder/README.md dist-v2/licenses/NTR-Forwarder.md

arm-none-eabi-gcc -specs=ds_arm9.specs -march=armv5te -mtune=arm946e-s -mthumb -DARM9 \
    -I"$DEVKITPRO/libnds/include" probe.c -L"$DEVKITPRO/libnds/lib" -lfat -lnds9 -o .build-v2/probe.elf
ndstool -c dist-v2/Storage-Probe.nds -9 .build-v2/probe.elf -7 .build-v2/yanbf/bootstrap/bootstrap.arm7.elf
make -C .build-v2/makerom/makerom deps
make -C .build-v2/makerom/makerom -j2
python3 generator.py --prepare-tools --package dist-v2 --makerom-linux .build-v2/makerom/makerom/bin/makerom
python3 dist-v2/generator.py dist-v2/Storage-Probe.nds --title "DS Storage Test" --basic-banner --output dist-v2/DS-Storage-Test.cia
python3 verify.py dist-v2
python3 -m unittest discover -s tests -v
python3 - <<'PY'
import hashlib, json, os, pathlib
p = pathlib.Path('dist-v2')
receipt = {'source_commit': os.environ.get('GITHUB_SHA'), 'sources': json.loads(pathlib.Path('sources.json').read_text()),
           'hardware_tested': False, 'files': {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in sorted(p.rglob('*')) if f.is_file()}}
(p/'build-info.json').write_text(json.dumps(receipt, indent=2)+'\n')
PY
