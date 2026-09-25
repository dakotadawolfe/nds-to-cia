from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import os

ROOT = Path(__file__).parents[1]


class RuntimeTests(unittest.TestCase):
    @unittest.skipUnless(os.name != 'nt' and shutil.which('g++'), 'C++ sanitizer tests run in the Linux build')
    def test_real_resolver_and_request_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work/'test.cpp'
            source.write_text(r'''
#include "runtime_paths.h"
#include "requests.h"
#include <assert.h>
#include <stdlib.h>
static int count;
static int visit(const char*, uint64_t title, void*) {
    assert(title == 0x000400000d743200ULL); ++count; return 1;
}
int main() {
    assert(!ds_storage_init(NULL));
    assert(!ds_storage_init("sd:/_nds/game.nds"));
    assert(!ds_storage_init("sd:/Nintendo 3DS/../data/00000000/a.bin"));
    const char* base = "/Nintendo 3DS/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/title/00040000/0d743200/data/00000000";
    char input[256], expected[256];
    snprintf(input, sizeof(input), "sd:%s/00000001.bin", base);
    assert(ds_storage_init(input));
    snprintf(expected, sizeof(expected), "sd:%s/00000005.bin", base);
    const char* stable = ds_path("sd:", "/00000005.bin");
    assert(!strcmp(stable, expected));
    assert(stable == ds_path("sd:", "/00000005.bin"));
    ds_path("fat:", "/12345678/abcdef01.bin");
    assert(!strcmp(stable, expected));
    assert(!ds_storage_init(input));
    assert(ds_visit_titles("card", 0, visit, NULL));
    assert(count == 1);
    assert(ds_visit_titles("uppercase-card", 0, visit, NULL));
    assert(count == 2);
    assert(!ds_hex_name("0g743200", 8));
    return 0;
}
''')
            import struct
            titles = work/'card'/('a'*32)/('b'*32)/'title'/'00040000'
            for title, record in [
                    ('0d743200', b'DCSREQ02'+struct.pack('<Q', 0x000400000d743200)),
                    ('0d743201', b'DCSREQ02'+struct.pack('<Q', 0x000400000d743200)),
                    ('0d743202', b'DCSREQ01'+struct.pack('<Q', 0x000400000d743202)),
                    ('0d743203', b'DCSREQ02'),
                    ('0d743204', b'DCSREQ02'+struct.pack('<Q', 0x000400000d743204)+b'extra')]:
                folder = titles/title/'data'/'00000000'
                folder.mkdir(parents=True)
                (folder/'00000007.bin').write_bytes(record)
            # libfat and CTR FS can expose different casing for FAT short names.
            upper = work/'uppercase-card'/('A'*32)/('B'*32)/'title'/'00040000'/'0D743200'/'data'/'00000000'
            upper.mkdir(parents=True)
            (upper/'00000007.bin').write_bytes(b'DCSREQ02'+struct.pack('<Q', 0x000400000d743200))
            exe = work/'runtime-test'
            subprocess.run(['g++', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            '-I', str(ROOT.resolve()), str(source), str(ROOT/'runtime_paths.cpp'),
                            '-o', str(exe)], check=True)
            subprocess.run([str(exe)], cwd=work, check=True)
