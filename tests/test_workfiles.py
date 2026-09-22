from pathlib import Path
import importlib.util
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]


class WorkfileTests(unittest.TestCase):
    def test_paths_match_bootstrap_relocation(self):
        spec = importlib.util.spec_from_file_location('prepare', ROOT/'prepare.py')
        prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare)
        header = (ROOT/'workfiles.h').read_text()
        for macro, original in [('DS_RAM_DUMP_PATH', '/nds-bootstrap/ramDump.bin'),
                                ('DS_OVERLAY_PATH', '/nds-bootstrap/apFixOverlays.bin')]:
            path = re.search(r'#define '+macro+r' "([^"]+)"', header)[1]
            self.assertEqual('/'+path, prepare.opaque_suffix(original))

    @unittest.skipUnless(shutil.which('gcc'), 'C allocation tests run in the Linux build')
    def test_allocation_preservation_and_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work/'test.c'
            source.write_text(r'''
#include "workfiles.h"
#include <assert.h>
#include <signal.h>
#include <sys/resource.h>
static unsigned char block[65536];
static void contents(const char *path, size_t size, int prefix) {
    FILE *f = fopen(path, "rb"); assert(f);
    for (size_t i = 0; i < size; i++) assert(fgetc(f) == (i < 3 ? prefix : 0));
    assert(fgetc(f) == EOF && !ferror(f)); assert(!fclose(f));
}
int main(void) {
    assert(ds_ensure_workfile("fresh", 131075, block, sizeof(block)));
    contents("fresh", 131075, 0);
    FILE *f = fopen("partial", "wb"); assert(f);
    assert(fwrite("xxx", 1, 3, f) == 3); assert(!fclose(f));
    assert(ds_ensure_workfile("partial", 131075, block, sizeof(block)));
    contents("partial", 131075, 'x');
    assert(ds_ensure_workfile("partial", 131075, block, sizeof(block)));
    assert(ds_ensure_workfile("partial", 64, block, sizeof(block)));
    contents("partial", 131075, 'x');
    assert(!ds_ensure_workfile("missing/child", 4, block, sizeof(block)));
    assert(!ds_ensure_workfile(".", 4, block, sizeof(block)));
    assert(!ds_ensure_workfile("invalid", 4, NULL, 0));
    /* A real short write must fail closed and leave a resumable prefix. */
    struct rlimit original, limited;
    assert(!getrlimit(RLIMIT_FSIZE, &original));
    limited = original; limited.rlim_cur = 70000;
    signal(SIGXFSZ, SIG_IGN);
    assert(!setrlimit(RLIMIT_FSIZE, &limited));
    assert(!ds_ensure_workfile("limited", 131075, block, sizeof(block)));
    assert(!setrlimit(RLIMIT_FSIZE, &original));
    assert(ds_ensure_workfile("limited", 131075, block, sizeof(block)));
    contents("limited", 131075, 0);
    return 0;
}
''')
            exe = work/'allocation-test'
            subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(ROOT.resolve()),
                            str(source), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], cwd=work, check=True)
