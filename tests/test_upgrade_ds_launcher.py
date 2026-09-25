import struct
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import upgrade_ds_launcher as upgrade


def fixture(code=b'old code', title=0x000400000C123400):
    data = bytearray(0x1800)
    data[0x100:0x104] = b'NCCH'
    struct.pack_into('<I', data, 0x104, len(data) // 512)
    struct.pack_into('<Q', data, 0x118, title)
    data[0x150:0x15A] = b'CTR-H-DCSD'
    data[0x18F] = 4
    struct.pack_into('<I', data, 0x180, 0x400)
    struct.pack_into('<III', data, 0x1A0, 5, 5, 1)
    struct.pack_into('<II', data, 0x1B0, 11, 1)
    for offset in (0x3C8, 0x400, 0x800):
        struct.pack_into('<Q', data, offset, title)
    for i, (name, value) in enumerate(((b'.code', code), (b'banner', b'artwork'),
                                      (b'icon', b'icon'), (b'logo', b'logo'))):
        struct.pack_into('<8sII', data, 0xA00 + i * 16, name, i * 512, len(value))
        start = 0xC00 + i * 512
        data[start:start + len(value)] = value
        digest = 0xBE0 - i * 32
        data[digest:digest + 32] = upgrade.sha(value)
    data[0x160:0x180] = upgrade.sha(data[0x200:0x600])
    data[0x1C0:0x1E0] = upgrade.sha(data[0xA00:0xC00])
    data[0x1600:] = b'R' * 512
    return bytes(data)


class LauncherUpgradeTests(unittest.TestCase):
    def test_preserves_identity_game_artwork_and_access_signature(self):
        old = fixture(b'old launcher code')
        template = bytearray(fixture(b'new code', 0x000400000C888800))
        template[0x600:0x700] = b'S' * 256
        updated = upgrade.replace_launcher(old, template)
        self.assertEqual(len(updated), len(old))
        self.assertEqual(updated[0x240:0xA00], old[0x240:0xA00])
        self.assertEqual(updated[0x1600:], old[0x1600:])
        for offset in (0x118, 0x3C8, 0x400, 0x800):
            self.assertEqual(updated[offset:offset + 8], old[offset:offset + 8])
        for name in (b'icon', b'banner', b'logo'):
            _, offset, size = upgrade.validate_ncch(old)[name]
            self.assertEqual(updated[offset:offset + size], old[offset:offset + size])
        self.assertEqual(upgrade.replace_launcher(updated, template), updated)

    def test_rejects_larger_code(self):
        with self.assertRaisesRegex(ValueError, 'does not fit'):
            upgrade.replace_launcher(fixture(b'short'), fixture(b'longer code'))

    def test_rejects_changed_capabilities(self):
        template = bytearray(fixture())
        template[0x500] ^= 1
        template[0x160:0x180] = upgrade.sha(template[0x200:0x600])
        with self.assertRaisesRegex(ValueError, 'capabilities'):
            upgrade.replace_launcher(fixture(), template)

    def test_rejects_damaged_code_and_extended_header(self):
        for offset in (0x210, 0xC00):
            damaged = bytearray(fixture())
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                upgrade.replace_launcher(damaged, fixture())

    @unittest.skipUnless(importlib.util.find_spec('pyctr'), 'Crypto publication tests run in the Windows build')
    def test_encrypted_publication_and_rollback_close_file_handles(self):
        from pyctr.crypto import CryptoEngine, Keyslot
        crypto = CryptoEngine(setup_b9_keys=False)
        crypto.set_normal_key(Keyslot.SD, bytes(16))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tree = root / 'tree'
            tree.mkdir()
            names = ['app', 'tmd', 'cmd']
            for name in names:
                with (tree / name).open('wb') as file, crypto.create_ctr_io(
                        Keyslot.SD, file, crypto.sd_path_to_iv('/' + name)) as output:
                    output.write(b'original ' + name.encode())
            original = {name: (tree / name).read_bytes() for name in names}
            # A validation read must not leave a Windows sharing lock behind.
            with upgrade.open_sd(tree, 'tmd', crypto) as source:
                self.assertEqual(source.read(), b'original tmd')
            replace = upgrade.os.replace
            calls = 0

            def fail_second(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated publication failure')
                return replace(source, target)

            updates = [(name, b'new ' + name.encode()) for name in names]
            with patch.object(upgrade.os, 'replace', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'publication'):
                    upgrade.publish(None, crypto, tree, updates, root / 'failed-backup')
            self.assertEqual({name: (tree / name).read_bytes() for name in names}, original)
            self.assertEqual(sorted(p.name for p in tree.iterdir()), sorted(names))
            upgrade.publish(None, crypto, tree, updates, root / 'backup')
            for name, expected in updates:
                with upgrade.open_sd(tree, name, crypto) as source:
                    self.assertEqual(source.read(), expected)


if __name__ == '__main__':
    unittest.main()
