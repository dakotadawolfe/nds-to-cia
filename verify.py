"""Check CIA content hashes and required release output files."""
import hashlib
from pathlib import Path
import struct
import sys


def align(value):
    return (value + 63) & ~63


def verify_cia(path, title=None, native_assets=None):
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError(f'{path}: truncated CIA')
    header, _, _, cert, ticket, tmd_size, meta, content_size = struct.unpack_from('<IHHIIIIQ', data)
    ticket_offset = align(align(header) + cert)
    tmd_offset = align(ticket_offset + ticket)
    content_offset = align(tmd_offset + tmd_size)
    if content_offset + content_size > len(data):
        raise ValueError(f'{path}: incomplete content')
    tmd = data[tmd_offset:tmd_offset+tmd_size]
    title_id = struct.unpack_from('>Q', tmd, 0x18C)[0]
    if ticket < 0x1e4 or struct.unpack_from('>Q', data, ticket_offset+0x1dc)[0] != title_id:
        raise ValueError(f'{path}: ticket does not match the title')
    if title is not None and title_id != title:
        raise ValueError(f'{path}: unexpected title {title_id:016X}')
    count = struct.unpack_from('>H', tmd, 0x1DE)[0]
    if count != 1:
        raise ValueError(f'{path}: expected one content')
    length = struct.unpack_from('>Q', tmd, 0xB0C)[0]
    expected = tmd[0xB14:0xB34]
    if length > content_size or len(expected) != 32 or hashlib.sha256(data[content_offset:content_offset+length]).digest() != expected:
        raise ValueError(f'{path}: content hash mismatch')
    if title_id >> 32 == 0x00040000:
        ncch = data[content_offset:content_offset+length]
        if ncch[0x100:0x104] != b'NCCH' or any(ncch[0x198:0x1a0]):
            raise ValueError(f'{path}: expected native content with an ExeFS launch logo')
        for offset in (0x108, 0x118, 0x3c8, 0x400, 0x800):
            if struct.unpack_from('<Q', ncch, offset)[0] != title_id:
                raise ValueError(f'{path}: inconsistent launch/program title ID')
        exefs = struct.unpack_from('<I', ncch, 0x1a0)[0] * 512
        names = [ncch[exefs+i*16:exefs+i*16+8].rstrip(b'\0') for i in range(10)]
        if any(name not in names for name in (b'logo', b'icon', b'banner', b'.code')):
            raise ValueError(f'{path}: missing icon/banner/code/launch logo in ExeFS')
        for index, name in enumerate(names):
            if not name:
                continue
            offset, size = struct.unpack_from('<II', ncch, exefs+index*16+8)
            resource = ncch[exefs+512+offset:exefs+512+offset+size]
            expected_hash = ncch[exefs+0x1e0-index*32:exefs+0x200-index*32]
            if len(resource) != size or hashlib.sha256(resource).digest() != expected_hash:
                raise ValueError(f'{path}: invalid ExeFS resource hash: {name!r}')
            if name == b'logo':
                from launch_logo import decompress, validate_archive
                archive = decompress(resource)
                validate_archive(archive)
            if name == b'banner' and native_assets is not None:
                from launch_logo import decompress
                from native_banner import validate_native_banner
                if resource[:4] != b'CBMD':
                    raise ValueError('Invalid HOME Menu banner container')
                graphics_offset = struct.unpack_from('<I', resource, 8)[0]
                audio_offset = struct.unpack_from('<I', resource, 0x84)[0]
                if not 0x88 <= graphics_offset < audio_offset < len(resource) or resource[audio_offset:audio_offset+4] != b'CWAV':
                    raise ValueError('Invalid banner graphics/audio ranges')
                validate_native_banner(decompress(resource[graphics_offset:audio_offset]), (Path(native_assets)/'BannerDS.bin').read_bytes())
    print(f'CIA verified: {path.name}, {title_id:016X}, {length:,} content bytes')


if __name__ == '__main__':
    root = Path(sys.argv[1])
    verify_cia(root/'runtime/bridge.cia', 0x0004800544435332)
    verify_cia(root/'DS-Storage-Test.cia')
    for name in ('nds-bootstrap-release.nds', 'nds-bootstrap-hb-release.nds', 'sdcard.nds'):
        data = (root/'runtime'/name).read_bytes()
        if len(data) < 512:
            raise ValueError(f'Invalid DS runtime: {name}')
