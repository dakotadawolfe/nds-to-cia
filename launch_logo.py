"""Keep a valid HOME Menu launch archive while blanking its artwork.

The input is makerom's Homebrew_LZ resource from the pinned Project_CTR source.
Its layout and animation names remain intact; texture payloads become black.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

AUTH = json.loads((Path(__file__).parent/'assets/blank-logo-auth.json').read_text())


def authenticate_blank_archive(archive):
    """Use the precomputed tag only for the exact fixed artwork it authenticates."""
    if hashlib.sha256(archive[:-32]).hexdigest() != AUTH['body_sha256']:
        raise ValueError('Blank launch artwork changed; its authentication tag is no longer valid')
    return archive[:-32] + bytes.fromhex(AUTH['hmac_sha256'])


def validate_archive(archive):
    if len(archive) < 60 or struct.unpack_from('<I', archive, 12)[0] != len(archive)-32:
        raise ValueError('Launch archive must end with a 32-byte authentication tag')
    if blank_archive(archive) != archive:
        raise ValueError('Launch resource still contains artwork')
    if authenticate_blank_archive(archive) != archive:
        raise ValueError('Launch archive has an invalid internal authentication tag')


def decompress(data):
    if len(data) < 4 or data[0] != 0x11:
        raise ValueError('Expected an LZ11 launch archive')
    size = int.from_bytes(data[1:4], 'little')
    output, at = bytearray(), 4
    while len(output) < size:
        flags = data[at]
        at += 1
        for bit in range(7, -1, -1):
            if len(output) == size:
                break
            if not flags & (1 << bit):
                output.append(data[at])
                at += 1
                continue
            first = data[at]
            at += 1
            kind = first >> 4
            if kind == 0:
                second, third = data[at:at+2]
                at += 2
                length = ((first & 15) << 4 | second >> 4) + 0x11
                distance = ((second & 15) << 8 | third) + 1
            elif kind == 1:
                second, third, fourth = data[at:at+3]
                at += 3
                length = ((first & 15) << 12 | second << 4 | third >> 4) + 0x111
                distance = ((third & 15) << 8 | fourth) + 1
            else:
                length = kind + 1
                distance = ((first & 15) << 8 | data[at]) + 1
                at += 1
            if distance > len(output) or len(output) + length > size:
                raise ValueError('Invalid LZ11 reference')
            for _ in range(length):
                output.append(output[-distance])
    return bytes(output)


def compress(data):
    if not 0 < len(data) < 1 << 24:
        raise ValueError('Invalid launch archive size')
    output = bytearray(b'\x11' + len(data).to_bytes(3, 'little'))
    at = 0
    while at < len(data):
        flag_at = len(output)
        output.append(0)
        for bit in range(7, -1, -1):
            if at == len(data):
                break
            # A short dictionary search is sufficient for these small archives.
            length, distance = 0, 0
            start = max(0, at - 4096)
            candidate = data.rfind(data[at:at+3], start, at)
            if candidate >= 0 and at + 3 <= len(data):
                distance = at - candidate
                limit = min(len(data) - at, 0x10110)
                while length < limit and data[at+length] == data[at+length-distance]:
                    length += 1
            if length < 3:
                output.append(data[at])
                at += 1
                continue
            output[flag_at] |= 1 << bit
            offset = distance - 1
            if length <= 0x10:
                output.extend((((length - 1) << 4) | (offset >> 8), offset & 255))
            elif length <= 0x110:
                value = length - 0x11
                output.extend((value >> 4, ((value & 15) << 4) | (offset >> 8), offset & 255))
            else:
                value = length - 0x111
                output.extend((0x10 | (value >> 12), (value >> 4) & 255,
                               ((value & 15) << 4) | (offset >> 8), offset & 255))
            at += length
    return bytes(output)


def blank_archive(data):
    archive = bytearray(data)
    if archive[:8] != b'darc\xff\xfe\x1c\x00':
        raise ValueError('Unexpected launch archive header')
    table = struct.unpack_from('<I', archive, 16)[0]
    count = struct.unpack_from('<I', archive, table+8)[0]
    names = table + count * 12
    textures = 0
    for index in range(count):
        flags, offset, size = struct.unpack_from('<III', archive, table+index*12)
        if flags >> 24:
            continue
        at = names + (flags & 0xffffff)
        end = at
        while end + 2 <= len(archive) and archive[end:end+2] != b'\0\0':
            end += 2
        name = archive[at:end].decode('utf-16le')
        if offset + size > len(archive):
            raise ValueError('Launch resource exceeds archive bounds')
        if name.endswith('.bclim'):
            footer = offset + size - 40
            if archive[footer:footer+4] != b'CLIM' or archive[footer+20:footer+24] != b'imag':
                raise ValueError('Unexpected launch texture')
            # This pinned resource uses opaque ETC1 (format 10). All-zero ETC1
            # blocks decode to a uniform near-black color, without logos/text.
            if struct.unpack_from('<I', archive, footer+32)[0] != 10:
                raise ValueError('Unexpected launch texture format')
            archive[offset:footer] = bytes(footer-offset)
            textures += 1
    if textures != 4:
        raise ValueError('Pinned launch archive no longer has four textures')
    return bytes(archive)


def build(source, destination):
    text = Path(source).read_text()
    match = re.search(r'Homebrew_LZ\[0x2000\]\s*=\s*\{(.*?)\};', text, re.S)
    if not match:
        raise ValueError('Pinned makerom homebrew logo was not found')
    packed = bytes(int(value, 16) for value in re.findall(r'0x([0-9A-Fa-f]{2})', match[1]))
    blank = authenticate_blank_archive(blank_archive(decompress(packed)))
    validate_archive(blank)
    result = compress(blank)
    if decompress(result) != blank or len(result) > 0x2000:
        raise ValueError('Blank launch archive failed round-trip/size validation')
    Path(destination).write_bytes(result.ljust(0x2000, b'\0'))


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
