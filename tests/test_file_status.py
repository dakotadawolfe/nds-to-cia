from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PreparedFileTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gcc'), 'Host C tests run in the Linux build')
    def test_trusted_same_size_file_and_missing_truncated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'check.c'
            source.write_text(r'''
#include "file_status.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    assert(!ds_has_expected_size("missing", 0));
    assert(!ds_has_expected_size(".", 0));
    FILE *f = fopen("game", "wb"); assert(f);
    assert(fwrite("abcd", 1, 4, f) == 4); assert(!fclose(f));
    assert(ds_has_expected_size("game", 4));
    assert(!ds_has_expected_size("game", 5));
    f = fopen("game", "wb"); assert(f);
    assert(fwrite("WXYZ", 1, 4, f) == 4); assert(!fclose(f));
    assert(ds_has_expected_size("game", 4));
    f = fopen("game", "wb"); assert(f); assert(!fclose(f));
    assert(!ds_has_expected_size("game", 4));
    return 0;
}
''')
            binary = root / 'check'
            subprocess.run(['gcc', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                            '-I', str(Path(__file__).parents[1].resolve()),
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], cwd=root, check=True)
