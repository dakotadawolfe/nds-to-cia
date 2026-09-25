import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import windows_app


class PreparationCommandTests(unittest.TestCase):
    def args(self, **overrides):
        values = dict(boot9=Path('boot9.bin'), report=Path('report.json'),
                      prepare_sd=Path('card'), upgrade_launchers=False, backup_dir=None)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_missing_key_and_backup_rejected_before_writes(self):
        with patch.object(windows_app, 'prepare_sd_runtime') as prepare, \
                patch.object(windows_app, 'upgrade_sd_launchers') as upgrade:
            for args in (self.args(boot9=None), self.args(report=None), self.args(upgrade_launchers=True)):
                with self.assertRaises(ValueError):
                    windows_app.prepare_card(args)
            prepare.assert_not_called()
            upgrade.assert_not_called()

    def test_upgrade_failure_does_not_continue_preparation(self):
        with patch.object(windows_app, 'prepare_sd_runtime') as prepare, \
                patch.object(windows_app, 'upgrade_sd_launchers', side_effect=ValueError('invalid title')):
            with self.assertRaisesRegex(ValueError, 'invalid title'):
                windows_app.prepare_card(self.args(upgrade_launchers=True, backup_dir=Path('backup')))
            prepare.assert_not_called()

    def test_preparation_does_not_upgrade_without_option(self):
        with patch.object(windows_app, 'prepare_sd_runtime', return_value={'titles': []}) as prepare, \
                patch.object(windows_app, 'upgrade_sd_launchers') as upgrade:
            self.assertEqual(windows_app.prepare_card(self.args()), {'preparation': {'titles': []}})
            prepare.assert_called_once_with(Path('card'), Path('boot9.bin'))
            upgrade.assert_not_called()
