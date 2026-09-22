from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from windows_app import convert, state_lock


class DesktopTests(unittest.TestCase):
    def test_profile_prevents_concurrent_registry_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)
            with state_lock(state):
                with self.assertRaises((ValueError,BlockingIOError)):
                    with state_lock(state):pass
            with state_lock(state):pass

    def test_conversion_uses_profile_not_executable_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'profile'
            with patch('windows_app.build_game') as build:
                convert('game.nds','game.cia',state)
                args=build.call_args.args
                self.assertEqual(args[4],state/'native-assets')
                self.assertEqual(args[6],state/'title-ids.json')

    def test_output_extension_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('windows_app.build_game') as build:
                with self.assertRaises(ValueError):convert('game.nds','game.nds',Path(directory))
                build.assert_not_called()
