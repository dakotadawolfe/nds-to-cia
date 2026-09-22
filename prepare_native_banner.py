"""Extract DS display resources from the user's HOME Menu and font CIA dumps.

Requires pyctr (pip install pyctr) and a local boot9 dump when input is encrypted.
No system resource, game, or key is downloaded or included in public builds.
"""
import argparse
import hashlib
import json
import os
import io
import struct
from pathlib import Path
from launch_logo import decompress
from native_banner import SystemFont, texture_entries


def read_resource(path, resource, boot9):
    # Fully decrypted CIA dumps do not need boot ROM keys. Avoid constructing
    # pyctr's CryptoEngine for those inputs, since it eagerly requires boot9.
    data = Path(path).read_bytes()
    if len(data) < 32:
        raise ValueError('Truncated CIA dump')
    header, _, _, cert, ticket, tmd_size, _, size = struct.unpack_from('<IHHIIIIQ', data)
    align = lambda value: (value+63)&~63
    start = align(align(align(align(header)+cert)+ticket)+tmd_size)
    if start+size > len(data):
        raise ValueError('Incomplete CIA dump')
    if data[start+0x100:start+0x104] == b'NCCH' and data[start+0x18f]&4:
        from pyctr.type.romfs import RomFSReader
        offset, length = struct.unpack_from('<II', data, start+0x1b0)
        begin, end = start+offset*512, start+(offset+length)*512
        if not length or end>start+size:
            raise ValueError('Invalid system resource filesystem')
        with RomFSReader(io.BytesIO(data[begin:end])) as romfs:
            return romfs.open(resource).read()
    if not boot9:
        raise ValueError('This CIA is encrypted. Select your boot9.bin, or export a decrypted CIA with GodMode9.')
    from pyctr.type.cia import CIAReader
    with CIAReader(path) as cia:
        return cia.contents[0].romfs.open(resource).read()


def prepare(menu, font, output, boot9=None):
    if boot9:
        os.environ['BOOT9_PATH'] = str(Path(boot9).resolve())
    model = decompress(read_resource(menu, '/3D/BannerDS_LZ.bin', boot9))
    font_data = decompress(read_resource(font, '/cbf_std.bcfnt.lz', boot9))
    entries = texture_entries(model)
    if not {'DmyIcon_00', 'DmyIconMask_00', 'DmyText_00'} <= entries.keys():
        raise ValueError('HOME Menu does not contain the expected DS display resources')
    SystemFont(font_data)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    files = {'BannerDS.bin': model, 'cbf_std.bcfnt': font_data}
    for name, data in files.items():
        target = output/name
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f'Refusing to replace different resource: {target}')
    for name, data in files.items():
        (output/name).write_bytes(data)
    receipt = {'source': 'user-supplied-system-dumps',
               'files': {name: hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    (output/'resources.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(f'Prepared native DS resources in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home-menu', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--boot9', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'native-assets')
    args = parser.parse_args()
    prepare(args.home_menu, args.font, args.output, args.boot9)
