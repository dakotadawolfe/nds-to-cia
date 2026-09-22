import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).parents[1]/'prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class RelocationTests(unittest.TestCase):
    def test_repeated_preparation_preserves_paths(self):
        source = b'"sd:/_nds/nds-bootstrap.ini" "fat:/NDSBTSRP.LOG" "sd:/NDSBTSRP.LOG" "fat:/NDSBTSRPHB.LOG"'
        once = prepare.relocate_bytes(source)
        self.assertEqual(prepare.relocate_bytes(once), once)
        self.assertNotIn(b'/_nds/', once)
        self.assertIn(b'ds_path("sd:", "/00000005.bin")', once)
        self.assertIn(f'ds_path("fat:", "{prepare.opaque_suffix("/NDSBTSRP.LOG")}")'.encode(), once)
        self.assertNotIn(b'NDSBTS', once)

    def test_device_formats_and_shared_directories_match(self):
        suffix = '/nds-bootstrap/patchOffsetCache/%s-%04X.bin'
        relocated = prepare.relocate_bytes(('"%s:/_nds' + suffix + '"').encode()).decode()
        self.assertEqual(relocated.count('%s'), 2)
        self.assertIn('%04X', relocated)
        self.assertEqual(prepare.opaque_suffix('/nds-bootstrap/apFixOverlays.bin'),
                         prepare.opaque_suffix('/nds-bootstrap/apfixOverlays.bin'))

    def test_identifiers_and_nitro_paths_preserved(self):
        source = b'void run_nds(); fopen("nitro:/cardengine_arm9.lz77", "rb");'
        self.assertEqual(prepare.relocate_bytes(source), source)
