import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

spec = importlib.util.spec_from_file_location('generator', Path(__file__).parents[1]/'generator.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class PackageTests(unittest.TestCase):
    def test_destination_traversal_rejected(self):
        for path in ('../boot.firm', '/boot.firm', 'games/../../data', 'sdmc:/evil', 'games\\evil'):
            with self.assertRaises(ValueError):
                generator.manifest_bytes(path, [('bridge.cia', 1, 0, 0)])

    def test_manifest_wire_layout(self):
        data = generator.manifest_bytes('00000000.bin', [('00000000.bin', 123456789, 0xFEDCBA98, 0), ('00000001.bin', 42, 17, 0)])
        self.assertEqual(data[:8], b'DCSDPK02')
        self.assertEqual(len(data), 76 + 2*144)
        self.assertEqual(struct.unpack_from('<I', data, 72)[0], 2)
        self.assertEqual(struct.unpack_from('<QII', data, 76+128), (123456789, 0xFEDCBA98, 0))

    def test_original_banner_name_and_icon(self):
        import zlib
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            data = bytearray(0x1000)
            struct.pack_into('<4I', data, 0x20, 512, 0x2000000, 0x2000000, 32)
            struct.pack_into('<4I', data, 0x30, 544, 0x2380000, 0x2380000, 32)
            struct.pack_into('<I', data, 0x68, 0x400)
            banner = bytearray(0x840)
            banner[0x20:0x220] = bytes([0x11])*512
            struct.pack_into('<H', banner, 0x222, 31)
            name = 'Original Game\nOriginal Studio'.encode('utf-16le')
            banner[0x340:0x340+len(name)] = name
            data[0x400:0xc40] = banner
            rom = folder/'different-filename.nds'
            rom.write_bytes(data)
            detected, found = generator.inspect_rom(rom)
            self.assertIn('Original Game', detected)
            self.assertNotIn('different-filename', detected)
            generator.artwork(folder, found)
            png = (folder/'icon.png').read_bytes()
            at = png.index(b'IDAT')
            size = struct.unpack_from('>I', png, at-4)[0]
            raw = zlib.decompress(png[at+4:at+4+size])
            for y in range(48):
                for x in range(48):
                    expected = bytes([255,0,0]) if 8 <= x < 40 and 8 <= y < 40 else bytes([255]*3)
                    self.assertEqual(raw[y*145+1+x*3:y*145+4+x*3], expected)

    def test_title_id_collision_keeps_existing_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory)/'ids.json'
            first, mapping = generator.reserve_id('a'*64, registry)
            import json
            registry.write_text(json.dumps(mapping))
            second, _ = generator.reserve_id('a'*8+'b'*56, registry)
            self.assertNotEqual(first, second)
            self.assertEqual(generator.reserve_id('a'*64, registry)[0], first)

    def test_incomplete_rom_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.nds'
            header = bytearray(512)
            struct.pack_into('<4I', header, 0x20, 512, 0, 0, 1024)
            path.write_bytes(header)
            with self.assertRaises(ValueError):
                generator.inspect_rom(path)

    def test_libnds_homebrew_is_not_rejected_as_dsiware(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'homebrew.nds'
            data = bytearray(576)
            data[0x12] = 2
            struct.pack_into('<I', data, 0x1B4, 0x138)
            struct.pack_into('<4I', data, 0x20, 512, 0x02000000, 0x02000000, 32)
            struct.pack_into('<4I', data, 0x30, 544, 0x02380000, 0x02380000, 32)
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'not DSiWare'):
                generator.inspect_rom(path)
            struct.pack_into('<4I', data, 512, 0xE3A00301, 0xE5800208, 0xE3A00013, 0xE129F000)
            path.write_bytes(data)
            self.assertEqual(generator.inspect_rom(path)[0], 'homebrew')


if __name__ == '__main__':
    unittest.main()
