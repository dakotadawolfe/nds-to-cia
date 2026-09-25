"""Fetch pinned references and apply the clean-SD runtime changes."""
import io
import json
import hashlib
import re
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / "sources.json").read_text())
BUILD = ROOT / '.build-v2'
SPECIAL = {
    '/nds-bootstrap-release.nds': '/00000002.bin',
    '/nds-bootstrap-nightly.nds': '/00000002.bin',
    '/nds-bootstrap-hb-release.nds': '/00000003.bin',
    '/nds-bootstrap-hb-nightly.nds': '/00000003.bin',
    '/ntr_forwarder.ini': '/00000004.bin',
    '/nds-bootstrap.ini': '/00000005.bin',
}


def opaque_suffix(path):
    if path in SPECIAL:
        return SPECIAL[path]
    result = []
    for component in path.split('/'):
        if not component:
            result.append('')
            continue
        formats = re.findall(r'%[-+0-9.]*[suxXd]', component)
        name = hashlib.sha256(component.lower().encode()).hexdigest()[:8]
        result.append(name + ('-' + '-'.join(formats) if formats else '') + ('.bin' if '.' in component else ''))
    return '/'.join(result)


def relocate_bytes(raw):
    def replace(match):
        device, suffix = match.group(1).decode(), match.group(2).decode()
        return f'ds_path("{device}", "{opaque_suffix(suffix)}")'.encode()
    raw = re.sub(rb'"((?:sd|fat|%s):|)/_nds([^"\n]*)"', replace, raw)
    for name in ('NDSBTSRP.LOG', 'NDSBTSRPHB.LOG', 'snemul.cfg'):
        raw = re.sub(rb'"((?:sd|fat):)/' + name.encode() + rb'"',
                     lambda m: f'ds_path("{m[1].decode()}", "{opaque_suffix("/"+name)}")'.encode(), raw)
    return raw


def fetch_sources():
    for name, source in SOURCES.items():
        target = BUILD / name
        url = f"https://codeload.github.com/{source['repo']}/zip/{source['commit']}"
        cached = BUILD/'archives'/(name+'-'+source['commit']+'.zip')
        if not cached.exists():
            print(f"Fetching {name}: {source['commit']}", flush=True)
            cached.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            archive = zipfile.ZipFile(io.BytesIO(data))
            if archive.testzip() is not None:
                raise ValueError(f'Corrupted source archive: {name}')
            cached.write_bytes(data)
        archive = zipfile.ZipFile(cached)
        # Always start from the pinned originals when applying the patch recipe again.
        for item in archive.infolist():
            parts = Path(item.filename).parts[1:]
            if not parts or ".." in parts:
                continue
            dest = target.joinpath(*parts)
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(item))
        archive.close()


def replace_required(path, old, new):
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise ValueError(f"Pinned patch no longer matches: {path}: {old!r}")
    path.write_text(text.replace(old, new))


def patch_sources():
    changes = []
    yanbf = BUILD / "yanbf"
    shutil.copy2(ROOT / "launcher.c", yanbf / "forwarder/source/main.c")
    shutil.copy2(ROOT / "workfiles.h", yanbf / "forwarder/source/workfiles.h")
    shutil.copy2(ROOT / "file_status.h", yanbf / "forwarder/source/file_status.h")
    shutil.copy2(ROOT / "bridge.cpp", yanbf / "bootstrap/arm9/source/main.cpp")
    for folder in (yanbf/'forwarder/source', yanbf/'bootstrap/arm9/source'):
        for name in ('layout.h', 'requests.h', 'silent.h'):
            shutil.copy2(ROOT/name, folder/name)
    makefile = yanbf / "bootstrap/Makefile"
    replace_required(yanbf/'generator/data/build-cia.rsf',
                     'Logo                    : Nintendo', 'Logo                    : None')
    replace_required(makefile, '-g FWDR 01 "TWLNFWDR-LHS"', '-g DCS2 01 "TWLNDCS2-NDS"')
    replace_required(makefile, '"YANBF;TWLNAND Booter;lifehackerhansol"', '"NDS to CIA;Internal launch component;NDS to CIA"')
    # Avoid boot-time banners for the shared bridge. Its title ID is unique to this project.
    # Widescreen swaps files in /luma; it is deliberately unavailable in this release.
    main = BUILD / "forwarder/SD_Card/sd/arm9/source/main.cpp"
    replace_required(main, "if(isRunFromSd && consoleModel == 2 && gameSettings.widescreen >= 1)",
                     "if(false && isRunFromSd && consoleModel == 2 && gameSettings.widescreen >= 1)")
    replace_required(main, 'widescreenLoaded = ntrforwarderini.GetInt("NTR-FORWARDER", "WIDESCREEN_LOADED", false);',
                     'widescreenLoaded = false; // This build never swaps Luma files.')
    replace_required(main, 'const int runSplash = ntrforwarderini.GetInt("NTR-FORWARDER", "DSI_SPLASH", 0);', 'const int runSplash = 0;')
    replace_required(main, 'const bool openPerGameSettings = (keysHeld() & KEY_Y);', 'const bool openPerGameSettings = false;')
    replace_required(main, '"/saves/"', '"/0000000a/"')
    replace_required(main, 'mkdir("saves", 0777);', 'mkdir("0000000a", 0777);')
    replace_required(main, 'if (fatInited) {',
                     'if (fatInited) {\n\t\tds_log_stage("Forwarder 1.0.0: SD mounted, argc=%d\\n", argc);')
    replace_required(main, 'ndsPath = (std::string)argv[1];',
                     'ndsPath = (std::string)argv[1];\n\t\tds_log_stage("Forwarder: game path accepted\\n");')
    replace_required(main, 'bootstrapini.SaveIniFile( bootstrapIniPath );',
                     'bootstrapini.SaveIniFile( bootstrapIniPath );\n\t\t\tds_log_stage("Forwarder: bootstrap configuration saved\\n");')
    replace_required(main, 'int err = runNdsFile(argarray[0], sizeof(argarray) / sizeof(argarray[0]), argarray);',
                     'ds_log_stage("Forwarder: starting %s\\n", argarray[0]);\n'
                     '\t\t\tint err = runNdsFile(argarray[0], sizeof(argarray) / sizeof(argarray[0]), argarray);\n'
                     '\t\t\tds_log_stage("Forwarder: loader returned=%d\\n", err);')
    settings = main.with_name('perGameSettings.cpp')
    replace_required(settings, '"/_nds/ntr-forwarder/gamesettings/" + fileName + ".ini"',
                     '"/_nds/ntr-forwarder/gamesettings/00000000.bin"')
    retail = BUILD / 'bootstrap/retail/arm9/source/main.cpp'
    replace_required(retail, 'configuration* conf = (configuration*)malloc(sizeof(configuration));',
                     'configuration* conf = (configuration*)calloc(1, sizeof(configuration));\n'
                     '\tif (!conf) return 1;\n\tstatic char apPath[512];\n\tconf->apPatchPath = apPath;')
    replace_required(retail, '&& (!extension(conf->ndsPath, ".app")))',
                     '&& (!extension(conf->ndsPath, ".app"))\n\t&& (!extension(conf->ndsPath, ".bin")))')
    replace_required(retail, 'int status = loadFromSD(conf, argv[0]);',
                     'int status = loadFromSD(conf, argv[0]);\n\tds_log_stage("Bootstrap: configuration result=%d\\n", status);')
    replace_required(retail, 'status = runNdsFile(conf);',
                     'ds_log_stage("Bootstrap: starting retail loader\\n");\n\t\tstatus = runNdsFile(conf);\n'
                     '\t\tds_log_stage("Bootstrap: retail loader returned=%d\\n", status);')
    replace_required(retail, '\treturn runNds(st.st_ino,',
                     '\tds_log_stage("Bootstrap: entering ARM7 game loader\\n");\n\treturn runNds(st.st_ino,')
    homebrew = BUILD / 'bootstrap/hb/arm9/source/main.cpp'
    replace_required(homebrew, '&& strcasecmp (filename.c_str() + filename.size() - 4, ".app") != 0)',
                     '&& strcasecmp (filename.c_str() + filename.size() - 4, ".app") != 0\n\t  && strcasecmp (filename.c_str() + filename.size() - 4, ".bin") != 0)')
    # The relocated cache path exceeds the upstream 64-byte buffer.
    for path in (retail, homebrew, BUILD / 'bootstrap/retail/arm9/source/conf_sd.cpp'):
        replace_required(path, 'char patchOffsetCacheFilePath[64];', 'char patchOffsetCacheFilePath[512];')
    # A two-argument launch deliberately has no return-title file.
    replace_required(homebrew,
                     'fread(&srBackendId, sizeof(u32), 2, srBackendBin);\n\t\tfclose(srBackendBin);',
                     'if (srBackendBin) {\n\t\t\tfread(&srBackendId, sizeof(u32), 2, srBackendBin);\n\t\t\tfclose(srBackendBin);\n\t\t}')
    for entry in (main, retail, homebrew):
        text = entry.read_text()
        if 'ds_storage_init(argv[0])' not in text:
            text, count = re.subn(r'(int main\([^)]*\)\s*\{)',
                                 r'\1\n\tif (argc < 1 || !ds_storage_init(argv[0])) return 1;', text)
            if count != 1:
                raise ValueError(f'Cannot locate main: {entry}')
            entry.write_text(text)
        arm9 = entry.parent.parent
        for path in arm9.rglob('*'):
            if path.suffix not in ('.c', '.cpp', '.h') or not path.is_file():
                continue
            raw = path.read_bytes()
            patched = relocate_bytes(raw)
            if patched != raw:
                patched = b'#include "runtime_paths.h"\n' + patched
            # The game itself is never patched; only the startup programs are quiet.
            quiet = re.sub(rb'\b(?:iprintf|printf|vprintf)\s*\(', b'ds_silent_printf(', patched)
            quiet = quiet.replace(b'defaultExceptionHandler();', b'/* Startup remains blank on failure. */')
            if quiet != patched:
                quiet = b'#include "silent.h"\n' + quiet
            if quiet != raw:
                path.write_bytes(quiet)
                changes.append(str(path.relative_to(ROOT)))
        for folder in (arm9/'source', arm9/'include'):
            folder.mkdir(exist_ok=True)
            for name in ('runtime_paths.h', 'silent.h'):
                shutil.copy2(ROOT/name, folder/name)
        shutil.copy2(ROOT/'runtime_paths.cpp', arm9/'source/runtime_paths.cpp')
    # These are freestanding ARM7 programs, so suppress only their drawing requests.
    for loader in ('bootloader', 'bootloaderi'):
        path = BUILD/f'bootstrap/retail/{loader}/source/arm7/loading_screen.c'
        text = path.read_text()
        for name, body in (('pleaseWaitOutput', ''), ('esrbOutput', ''), ('errorOutput', 'clearScreen(); while (1);')):
            text, count = re.subn(r'void '+name+r'\(void\)\s*\{[^}]*\}',
                                 f'void {name}(void) {{ {body} }}', text)
            if count != 1:
                raise ValueError(f'Cannot silence {path}:{name}')
        path.write_text(text)
    (BUILD/'patches.json').write_text(json.dumps(changes, indent=2) + '\n')


if __name__ == "__main__":
    fetch_sources()
    patch_sources()
