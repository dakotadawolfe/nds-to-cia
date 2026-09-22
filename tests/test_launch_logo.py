import importlib.util
from pathlib import Path
import random
import re
import struct
import unittest

spec = importlib.util.spec_from_file_location('launch_logo', Path(__file__).parents[1]/'launch_logo.py')
logo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logo)


class LaunchLogoTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).parents[1]/'.build-v2/makerom/makerom/src/ncch_logo.h').exists(),
                         'Pinned makerom sources are fetched by the package build')
    def test_stale_internal_tag_from_failed_hardware_build_is_rejected(self):
        source = (Path(__file__).parents[1]/'.build-v2/makerom/makerom/src/ncch_logo.h').read_text()
        match = re.search(r'Homebrew_LZ\[0x2000\]\s*=\s*\{(.*?)\};', source, re.S)
        packed = bytes(int(value, 16) for value in re.findall(r'0x([0-9A-Fa-f]{2})', match[1]))
        stale = logo.blank_archive(logo.decompress(packed))
        with self.assertRaisesRegex(ValueError, 'internal authentication tag'):
            logo.validate_archive(stale)
        corrected = logo.authenticate_blank_archive(stale)
        logo.validate_archive(corrected)
        self.assertEqual(corrected[:-32], stale[:-32])
        self.assertNotEqual(corrected[-32:], stale[-32:])
        with self.assertRaises(ValueError):
            logo.validate_archive(corrected[:-1] + bytes([corrected[-1] ^ 1]))
        changed = bytearray(corrected)
        changed[8] ^= 1
        with self.assertRaisesRegex(ValueError, 'artwork changed'):
            logo.validate_archive(changed)

    def test_lz11_known_reference_lengths(self):
        # Literal A followed by an overlapping reference of distance one.
        for count, reference in ((3, b'\x20\0'), (17, b'\0\0\0'),
                                 (273, b'\x10\0\0\0')):
            encoded = b'\x11' + (count+1).to_bytes(3, 'little') + b'\x40A' + reference
            self.assertEqual(logo.decompress(encoded), b'A' * (count+1))

    def test_lz11_round_trip(self):
        random_bytes = random.Random(42).randbytes(9000)
        for data in (b'x', random_bytes, bytes(70000), b'abc' * 30000,
                     random_bytes + random_bytes[-4096:] + bytes(8192)):
            self.assertEqual(logo.decompress(logo.compress(data)), data)

    def test_blank_preserves_resource_headers_and_layout(self):
        names = b'\0\0' + b''.join(f'{i}.bclim\0'.encode('utf-16le') for i in range(4))
        names_at = 28 + 5 * 12
        data_at = names_at + len(names)
        archive = bytearray(data_at + 4 * 72)
        archive[:8] = b'darc\xff\xfe\x1c\0'
        struct.pack_into('<III', archive, 16, 28, data_at-28, data_at)
        struct.pack_into('<III', archive, 28, 0x1000000, 0, 5)
        archive[names_at:data_at] = names
        for i in range(4):
            offset = data_at + i * 72
            struct.pack_into('<III', archive, 40+i*12, 2+i*16, offset, 72)
            archive[offset:offset+32] = b'\xff' * 32
            archive[offset+32:offset+36] = b'CLIM'
            archive[offset+52:offset+56] = b'imag'
            struct.pack_into('<I', archive, offset+64, 10)
        blank = logo.blank_archive(archive)
        self.assertEqual(blank[:data_at], archive[:data_at])
        for i in range(4):
            offset = data_at + i * 72
            self.assertEqual(blank[offset:offset+32], bytes(32))
            self.assertEqual(blank[offset+32:offset+72], archive[offset+32:offset+72])
