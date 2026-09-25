import io
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from unittest.mock import patch
from scripts import prepare_ds_runtime as prep


class RomFS:
    def __init__(self):
        self.data = {f'/files/{i:02}.bin': bytes([i + 1]) * 32 for i in range(6)}
        entries = b''.join(prep.ENTRY.pack(f'{i:08x}.bin'.encode(), 32,
                          zlib.crc32(self.data[f'/files/{i:02}.bin']), int(i >= 4)) for i in range(6))
        self.data['/package.manifest'] = prep.HEADER.pack(b'DCSDPK02', b'00000000.bin', 6) + entries

    def open(self, path):
        return io.BytesIO(self.data[path])


class PreparationTests(unittest.TestCase):
    def test_bad_crc_does_not_publish_or_leave_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'game'
            with self.assertRaises(ValueError):
                prep.write_new(target, io.BytesIO(b'broken'), 6, 0)
            self.assertEqual(list(target.parent.iterdir()), [])

    def test_existing_file_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'game'
            target.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                prep.write_new(target, io.BytesIO(b'new'), 3)
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(len(list(target.parent.iterdir())), 1)

    def test_manifest_rejects_traversal_bad_flags_and_truncation(self):
        original = RomFS().data['/package.manifest']
        for offset, replacement in [(prep.HEADER.size, b'../bad'),
                                    (prep.HEADER.size + 140, struct.pack('<I', 1))]:
            modified = bytearray(original)
            modified[offset:offset + len(replacement)] = replacement
            with self.assertRaises(ValueError):
                prep.manifest(modified)
        with self.assertRaises(ValueError):
            prep.manifest(original[:-1])

    def test_repeat_preserves_settings_saves_and_workfiles(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(prep, 'WORKFILES', {'work.bin': 64}), \
                patch.object(prep, 'screenshot_archive', return_value=b'archive'):
            root = Path(directory)
            fs = RomFS()
            self.assertEqual(len(prep.prepare_package(fs, root)), 8)
            (root / '00000004.bin').write_bytes(b'my settings')
            (root / 'work.bin').write_bytes(b'x' * 64)
            (root / 'save.sav').write_bytes(b'my save')
            self.assertEqual(prep.prepare_package(fs, root), [])
            self.assertEqual((root / '00000004.bin').read_bytes(), b'my settings')
            self.assertEqual((root / 'work.bin').read_bytes(), b'x' * 64)
            self.assertEqual((root / 'save.sav').read_bytes(), b'my save')
            (root / '00000000.bin').write_bytes(b'z' * 32)
            with self.assertRaises(ValueError):
                prep.prepare_package(fs, root)
            self.assertEqual((root / '00000000.bin').read_bytes(), b'z' * 32)


if __name__ == '__main__':
    unittest.main()
