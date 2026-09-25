"""Prepare installed DS Clean SD packages on a PC before copying a master card.

Requires pyctr==0.7.6 and the owner's boot9 dump and matching movable.sed.
Encrypted installed contents are read only. Existing saves/settings are retained.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import zlib

HEADER = struct.Struct('<8s64sI')
ENTRY = struct.Struct('<128sQII')
BLOCK = 1024 * 1024
BOOTSTRAP_SHA = 'd1a1264b54bd4fe06d5f1288bda8d8ca1a3e7cdf52d9a6d50ddbb5b85c6143bb'
WORKFILES = {'ff62061c/054778e7.bin': 32 << 20,
             'ff62061c/757d8f91.bin': 10 << 20, '81788216.bin': 6 << 20}
SCREENSHOT = 'ff62061c/26739303.bin'


def manifest(raw):
    if len(raw) < HEADER.size:
        raise ValueError('Truncated DS package manifest')
    magic, game, count = HEADER.unpack_from(raw)
    if magic != b'DCSDPK02' or game.rstrip(b'\0') != b'00000000.bin' or count != 6:
        raise ValueError('Unsupported DS package manifest')
    if len(raw) != HEADER.size + count * ENTRY.size:
        raise ValueError('Incorrect DS package manifest length')
    entries = []
    for i in range(count):
        name, size, crc, flags = ENTRY.unpack_from(raw, HEADER.size + i * ENTRY.size)
        expected = f'{i:08x}.bin'.encode()
        if name != expected.ljust(128, b'\0') or flags != int(i >= 4) or not 0 < size <= 512 << 20:
            raise ValueError('Unsupported DS package entry')
        entries.append((expected.decode(), size, crc, flags))
    return entries


def checksum(stream):
    crc, size = 0, 0
    sha = hashlib.sha256()
    while chunk := stream.read(BLOCK):
        crc = zlib.crc32(chunk, crc)
        sha.update(chunk)
        size += len(chunk)
    return size, crc, sha.hexdigest()


def write_new(target, source, expected_size, expected_crc=None):
    """Stage and read back before publication; never replace an existing file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ds-prep-', delete=False) as output:
            temporary = Path(output.name)
            while chunk := source.read(BLOCK):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        with temporary.open('rb') as check:
            size, crc, sha = checksum(check)
        if size != expected_size or (expected_crc is not None and crc != expected_crc):
            raise ValueError(f'Prepared file failed readback: {target.name}')
        # link is atomic and fails if the destination appeared while staging.
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise
        except OSError:
            if os.name != 'nt':
                raise
            # FAT cards do not support hard links. Windows rename also refuses
            # an existing destination, so it retains the no-overwrite guarantee.
            os.rename(temporary, target)
        return sha
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ZeroFile:
    def __init__(self, size):
        self.remaining = size

    def read(self, size):
        length = min(size, self.remaining)
        self.remaining -= length
        return bytes(length)


def screenshot_archive(bootstrap):
    """Reproduce this pinned bootstrap's archive from its own NitroFS headers."""
    if hashlib.sha256(bootstrap).hexdigest() != BOOTSTRAP_SHA:
        raise ValueError('Unsupported nds-bootstrap; review work-file layout before preparing it')
    fnt, fnt_size, fat, fat_size = struct.unpack_from('<4I', bootstrap, 0x40)
    names = bootstrap[fnt:fnt + fnt_size]
    pos, file_id = struct.unpack_from('<IH', names)
    headers = None
    while names[pos]:
        length = names[pos]
        pos += 1
        name = names[pos:pos + (length & 127)]
        pos += length & 127
        if length & 128:
            pos += 2
            continue
        if name == b'screenshotTarHeaders.bin':
            if file_id * 8 + 8 > fat_size:
                raise ValueError('NitroFS file index out of range')
            start, end = struct.unpack_from('<II', bootstrap, fat + file_id * 8)
            headers = bootstrap[start:end]
            break
        file_id += 1
    if headers is None or len(headers) != 51 * 0x100:
        raise ValueError('Missing screenshot archive headers')
    data = bytearray(0x4BCC00)
    for i in range(50):
        start = i * 0x18400
        data[start:start + 0x100] = headers[(i + 1) * 0x100:(i + 2) * 0x100]
        data[start + 0x100:start + 0x200] = headers[:0x100]
    return data


def prepare_package(romfs, base):
    with romfs.open('/package.manifest') as source:
        entries = manifest(source.read(4096))
    with romfs.open('/files/02.bin') as source:
        bootstrap = source.read(4 << 20)
    screenshots = screenshot_archive(bootstrap)
    # Validate all existing destinations before changing this package.
    for name, size, crc, mutable in entries:
        target = base / name
        if target.exists():
            if not target.is_file():
                raise ValueError(f'Package destination is not a file: {name}')
            if not mutable:
                with target.open('rb') as source:
                    existing = checksum(source)
                if existing[:2] != (size, crc):
                    raise ValueError(f'Existing runtime differs: {name}; retained without replacement')
    for name, size in {**WORKFILES, SCREENSHOT: len(screenshots)}.items():
        target = base / name
        if target.exists() and (not target.is_file() or target.stat().st_size < size):
            raise ValueError(f'Existing work file is incomplete: {name}; retained without replacement')
    created = []
    for index, (name, size, crc, mutable) in enumerate(entries):
        if not (base / name).exists():
            with romfs.open(f'/files/{index:02}.bin') as source:
                sha = write_new(base / name, source, size, crc)
            created.append({'file': name, 'size': size, 'sha256': sha})
    for name, size in WORKFILES.items():
        if not (base / name).exists():
            sha = write_new(base / name, ZeroFile(size), size)
            created.append({'file': name, 'size': size, 'sha256': sha})
    if not (base / SCREENSHOT).exists():
        sha = write_new(base / SCREENSHOT, io.BytesIO(screenshots), len(screenshots))
        created.append({'file': SCREENSHOT, 'size': len(screenshots), 'sha256': sha})
    return created


def prepare(sd_root, boot9):
    from pyctr.crypto import CryptoEngine
    from pyctr.type.sd import SDFilesystem
    from pyctr.type.ncch import NCCHReader
    root = Path(sd_root).resolve(strict=True)
    keys = [p for p in (root / 'movable.sed', root / 'moveable.sed') if p.is_file()]
    if not keys or any(p.read_bytes() != keys[0].read_bytes() for p in keys):
        raise ValueError('One unambiguous matching movable.sed is required')
    crypto = CryptoEngine(boot9=str(boot9))
    sd = SDFilesystem(root / 'Nintendo 3DS', crypto=crypto, sd_key_file=keys[0])
    if len(sd.id1s) != 1:
        raise ValueError('Expected one ID1 directory for the supplied movable')
    tree = root / 'Nintendo 3DS' / crypto.id0.hex() / sd.current_id1
    report = []
    for title in sorted((tree / 'title' / '00040000').iterdir()):
        if not title.is_dir():
            continue
        found = []
        for content in sorted((title / 'content').glob('*.app')):
            relative = content.relative_to(tree).as_posix()
            with sd.open(relative) as source:
                header = source.read(0x200)
            if header[0x100:0x104] == b'NCCH' and header[0x150:0x160].rstrip(b'\0') == b'CTR-H-DCSD':
                found.append(relative)
        if len(found) > 1:
            raise ValueError(f'Multiple DS packages in title {title.name}')
        if not found:
            continue
        with sd.open(found[0]) as source, NCCHReader(source, crypto=crypto) as ncch:
            if ncch.program_id.lower() != '00040000' + title.name.lower():
                raise ValueError('Installed DS title ID mismatch')
            created = prepare_package(ncch.romfs, title / 'data' / '00000000')
            report.append({'title_id': ncch.program_id, 'created': created})
            print(f'{ncch.program_id}: prepared {len(created)} files', flush=True)
    if not report:
        raise ValueError('No installed DS Clean SD packages found')
    return {'hardware_tested': False, 'titles': report,
            'note': 'Prepared extraction and work files; use launcher 1.1.0 to skip full-ROM launch CRC. Runtime initialization still runs.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sd-root', type=Path, required=True)
    parser.add_argument('--boot9', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.sd_root, args.boot9)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
