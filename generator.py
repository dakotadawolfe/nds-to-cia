"""Build a self-contained NDS to CIA game package."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import zlib
from banner import ds_icon, metadata
from native_banner import make_native_banner

ROOT = Path(__file__).resolve().parent
HEADER = struct.Struct('<8s64sI')
ENTRY = struct.Struct('<128sQII')
TOOLS = {
    'bannertool': ('https://github.com/Epicpkmn11/bannertool/releases/download/v1.2.2/bannertool.zip',
                   'e4259c08fe8944ebadd5f4b96f9a8603e5427338074cfc46323fbbc3410d51ed'),
    'makerom.exe': ('https://github.com/3DSGuy/Project_CTR/releases/download/makerom-v0.19.0/makerom-v0.19.0-win_x86_64.zip',
                    '88df4455e60556374e202d507f54ee03fac7493ec9554ab853157524b6d69db0'),
    'makerom': ('https://github.com/3DSGuy/Project_CTR/releases/download/makerom-v0.19.0/makerom-v0.19.0-ubuntu_x86_64.zip',
                '287b809dec064e0ad597e3d272c49ecb7eed41693d5ee6fef9d8a8aa24c2497e'),
}


def digest_file(path):
    sha, crc, size = hashlib.sha256(), 0, 0
    with Path(path).open('rb') as stream:
        while data := stream.read(1024 * 1024):
            sha.update(data)
            crc = zlib.crc32(data, crc)
            size += len(data)
    return sha.hexdigest(), crc, size


def prepare_tools(package, makerom_linux=None):
    directory = package / 'tools'
    directory.mkdir(parents=True, exist_ok=True)
    provenance = dict(TOOLS)
    for name, (url, sha) in TOOLS.items():
        if name == 'makerom' and makerom_linux:
            shutil.copyfile(makerom_linux, directory / name)
            (directory / name).chmod(0o755)
            provenance[name] = {'method': 'provided-local-build', 'sha256': digest_file(makerom_linux)[0]}
            continue
        print(f'Downloading {name}', flush=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError(f'{name} download checksum mismatch')
        archive = zipfile.ZipFile(io.BytesIO(data))
        wanted = {'linux-x86_64/bannertool': 'bannertool',
                  'windows-x86_64/bannertool.exe': 'bannertool.exe'} if name == 'bannertool' else {name: name}
        for member, filename in wanted.items():
            target = directory / filename
            target.write_bytes(archive.read(member))
            target.chmod(0o755)
    (directory / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    licenses = package / 'licenses'
    licenses.mkdir(parents=True, exist_ok=True)
    for name, url in {
        'bannertool.txt': 'https://raw.githubusercontent.com/Epicpkmn11/bannertool/v1.2.2/LICENSE.txt',
        'makerom.txt': 'https://raw.githubusercontent.com/3DSGuy/Project_CTR/makerom-v0.19.0/makerom/LICENSE',
        'makerom-mbedtls.txt': 'https://raw.githubusercontent.com/3DSGuy/Project_CTR/makerom-v0.19.0/makerom/deps/libmbedtls/LICENSE',
        'makerom-libyaml.txt': 'https://raw.githubusercontent.com/3DSGuy/Project_CTR/makerom-v0.19.0/makerom/deps/libyaml/LICENSE',
    }.items():
        with urllib.request.urlopen(url, timeout=30) as response:
            (licenses / name).write_bytes(response.read())


def inspect_rom(path):
    size = path.stat().st_size
    if not 512 <= size <= 512 * 1024 * 1024:
        raise ValueError('Expected a DS image between 512 bytes and 512 MiB')
    with path.open('rb') as stream:
        header = stream.read(512)
        libnds_homebrew = False
        for offset in (0x20, 0x30):
            start, entry, load, length = struct.unpack_from('<4I', header, offset)
            if start < 512 or not length or start + length > size:
                raise ValueError('The DS ARM binary bounds are invalid; use a complete dump')
            if offset == 0x20 and 0 <= entry - load <= length - 16:
                stream.seek(start + entry - load)
                libnds_homebrew = stream.read(16) == struct.pack('<4I', 0xE3A00301, 0xE5800208, 0xE3A00013, 0xE129F000)
        # Modern libnds images share this flag with DSiWare; their startup is distinct.
        if header[0x12] and struct.unpack_from('<I', header, 0x1B4)[0] & 0x10 and not libnds_homebrew:
            raise ValueError('This release targets DS cartridges and homebrew, not DSiWare')
        banner_offset = struct.unpack_from('<I', header, 0x68)[0]
        banner = b''
        if banner_offset and banner_offset + 0x840 <= size:
            stream.seek(banner_offset)
            banner = stream.read(0x840)
    title = header[:12].decode('ascii', errors='replace').strip('\0 ')
    if banner:
        title = banner[0x340:0x440].decode('utf-16le', errors='replace').split('\0')[0].replace('\n', ' ').strip() or title
    return title or path.stem, banner


def write_png(path, width, height, pixel):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + b''.join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 2, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def artwork(directory, banner):
    pixels = ds_icon(banner)
    # Native DS icons retain their 32-pixel bitmap within a white menu tile.
    write_png(directory/'icon.png', 48, 48,
              lambda x,y: pixels[(y-8)*32+x-8][:3] if 8 <= x < 40 and 8 <= y < 40 else (255,255,255))


def manifest_bytes(game, entries):
    def encode(value, size):
        if not re.fullmatch(r'[a-z0-9/._-]+', value) or '..' in value or value.startswith('/'):
            raise ValueError('Invalid package destination')
        raw = value.encode('ascii')
        if len(raw) >= size:
            raise ValueError('Package destination too long')
        return raw
    if not 1 <= len(entries) <= 16 or len({e[0] for e in entries}) != len(entries):
        raise ValueError('Invalid package entry count or duplicate destination')
    result = HEADER.pack(b'DCSDPK02', encode(game, 64), len(entries))
    for name, size, crc, flags in entries:
        if not 0 <= size <= 512 * 1024 * 1024 or flags not in (0, 1):
            raise ValueError('Invalid package entry')
        result += ENTRY.pack(encode(name, 128), size, crc, flags)
    return result


def reserve_id(sha, registry):
    data = json.loads(registry.read_text()) if registry.exists() else {}
    if sha in data:
        return data[sha], data
    unique = 0xC0000 + (int(sha[:8], 16) & 0x1FFFF)
    used = set(data.values())
    for _ in range(0x20000):
        if unique not in used:
            data[sha] = unique
            return unique, data
        unique = 0xC0000 + ((unique - 0xC0000 + 1) & 0x1FFFF)
    raise ValueError('No available title IDs in the reserved title-ID range')


def build_game(rom, output, title=None, package=ROOT, native_assets=None, basic_banner=False, registry_path=None):
    rom, output, package = rom.resolve(), output.resolve(), package.resolve()
    if output.exists():
        raise ValueError(f'Output already exists: {output}')
    detected, banner = inspect_rom(rom)
    title, publisher, lines = metadata(banner, detected, title)
    title = title[:63]
    native_assets = Path(native_assets) if native_assets else package/'native-assets'
    if not basic_banner and not all((native_assets/name).is_file() for name in ('BannerDS.bin', 'cbf_std.bcfnt')):
        raise ValueError('Native DS artwork is required. Run prepare_native_banner.py with your HOME Menu/font dumps, or explicitly select --basic-banner for the plain recovery artwork.')
    sha, _, rom_size = digest_file(rom)
    registry = Path(registry_path) if registry_path else package / 'title-ids.json'
    registry.parent.mkdir(parents=True, exist_ok=True)
    unique, ids = reserve_id(sha, registry)
    game = '00000000.bin'
    suffix = '.exe' if sys.platform == 'win32' else ''
    makerom, bannertool = (package/'tools'/('makerom'+suffix), package/'tools'/('bannertool'+suffix))
    for tool in (makerom, bannertool, package/'data/launcher.elf', package/'data/blank-logo.lz'):
        if not tool.is_file():
            raise ValueError(f'Missing build component: {tool}. Use the compiled test package.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ds-clean-sd-') as temporary:
        work = Path(temporary)
        romfs = work/'romfs'
        files = romfs/'files'
        files.mkdir(parents=True)
        entries = []
        sources = [(game, rom, 0),
                   ('00000001.bin', package/'runtime/sdcard.nds', 0),
                   ('00000002.bin', package/'runtime/nds-bootstrap-release.nds', 0),
                   ('00000003.bin', package/'runtime/nds-bootstrap-hb-release.nds', 0)]
        defaults = {'00000004.bin': b'[NTR-FORWARDER]\nBOOTSTRAP_FILE = 0\nSAVE_LOCATION = 0\nDSI_SPLASH = 0\n',
                    '00000005.bin': b'[NDS-BOOTSTRAP]\nDEBUG = 0\nLOGGING = 0\n'}
        for name, data in defaults.items():
            source = work/name
            source.write_bytes(data)
            sources.append((name, source, 1))
        for index, (name, source, flags) in enumerate(sources):
            target = files/f'{index:02}.bin'
            shutil.copyfile(source, target)
            _, crc, size = digest_file(target)
            entries.append((name, size, crc, flags))
        (romfs/'package.manifest').write_bytes(manifest_bytes(game, entries))
        artwork(work, banner)
        if basic_banner:
            pixels = ds_icon(banner)
            write_png(work/'banner.png', 256, 128,
                      lambda x,y: pixels[((y-16)//3)*32+(x-80)//3][:3]
                      if 80 <= x < 176 and 16 <= y < 112 else (18,28,46))
        else:
            make_native_banner(work, banner, lines, native_assets)
        def run(args):
            result = subprocess.run([str(a) for a in args], cwd=work, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            if result.returncode:
                raise ValueError(f'{Path(args[0]).name} failed:\n{result.stdout[-4000:]}')
        # bannertool requires a nonempty argument even when no publisher exists.
        run([bannertool, 'makesmdh', '-i', 'icon.png', '-s', title, '-l', '\n'.join(lines), '-p', publisher[:63] or ' ', '-o', 'icon.smdh'])
        run([bannertool, 'makebanner', '-i' if basic_banner else '-ci',
             'banner.png' if basic_banner else 'banner.cgfx', '-a', package/'data/dsboot.wav', '-o', 'banner.bin'])
        run([makerom, '-f', 'cia', '-target', 't', '-exefslogo', '-logo', package/'data/blank-logo.lz',
             '-rsf', package/'data/build-cia.rsf',
             '-elf', package/'data/launcher.elf', '-banner', 'banner.bin', '-icon', 'icon.smdh',
             '-DAPP_ROMFS=romfs', '-major', '1', '-minor', '0', '-micro', '0', '-DAPP_VERSION_MAJOR=1',
             '-DAPP_PRODUCT_CODE=CTR-H-DCSD', '-DAPP_TITLE=DSCleanSD', f'-DAPP_UNIQUE_ID=0x{unique:X}', '-o', 'game.cia'])
        from verify import verify_cia
        verify_cia(work/'game.cia', 0x0004000000000000 | (unique << 8),
                   native_assets=None if basic_banner else native_assets)
        shutil.copyfile(work/'game.cia', output)
    staged_registry = registry.with_suffix('.tmp')
    staged_registry.write_text(json.dumps(ids, indent=2) + '\n')
    staged_registry.replace(registry)
    receipt = {'title': title, 'rom_sha256': sha, 'rom_size': rom_size, 'title_id': f'{0x0004000000000000 | (unique << 8):016X}',
               'managed_game': f'/Nintendo 3DS/<ID0>/<ID1>/title/00040000/{unique << 8:08x}/data/00000000/{game}', 'cia_sha256': digest_file(output)[0],
               'storage': 'per-title-raw-bin', 'required_bridge': '0004800544435332',
               'launch_resource': 'authenticated-blank-exefs-logo', 'hardware_tested': False,
               'banner_style': 'basic-recovery' if basic_banner else 'native-home-menu-donor',
               'banner_hardware_verified': False}
    if not basic_banner:
        receipt['native_resources'] = {name: digest_file(native_assets/name)[0]
                                       for name in ('BannerDS.bin', 'cbf_std.bcfnt')}
    output.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Created {output}\nInstall the one-time Bridge.cia first. Initial launch extracts the bundled files silently.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--title')
    parser.add_argument('--native-assets', type=Path, help='Directory prepared from your HOME Menu and system font dumps')
    parser.add_argument('--basic-banner', action='store_true', help='Use plain recovery artwork instead of the native DS resources')
    parser.add_argument('--prepare-tools', action='store_true')
    parser.add_argument('--makerom-linux', type=Path, help='Use a locally compiled Linux makerom when preparing tools')
    parser.add_argument('--package', type=Path, default=ROOT)
    args = parser.parse_args()
    if args.prepare_tools:
        prepare_tools(args.package, args.makerom_linux)
        return
    if args.rom is None:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        selected = filedialog.askopenfilename(title='Select a DS game dump', filetypes=[('DS images', '*.nds')])
        window.destroy()
        if not selected:
            return
        args.rom = Path(selected)
    output = args.output or ROOT/'games'/(args.rom.stem+'.cia')
    build_game(args.rom, output, args.title, args.package, args.native_assets, args.basic_banner)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
