"""Create a portable Windows EXE using the CI-built runtime package."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def build():
    package=ROOT/'dist-v2'
    if not (package/'build-info.json').is_file():
        raise SystemExit('Download the runtime-build artifact into dist-v2 first.')
    manifest=json.loads((package/'build-info.json').read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((package/name).read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Runtime artifact hash mismatch: {name}')
    bundle=ROOT/'build/windows-bundle';bundle.mkdir(parents=True,exist_ok=True)
    # Explicit inventory: never collect a user's registry, game, font or key.
    allowed=['data/launcher.elf','data/build-cia.rsf','data/dsboot.wav','data/blank-logo.lz',
             'assets/blank-logo-auth.json','runtime/sdcard.nds','runtime/nds-bootstrap-release.nds',
             'runtime/nds-bootstrap-hb-release.nds','tools/makerom.exe','tools/bannertool.exe',
             'DS-Storage-Test.cia']
    for name in allowed:
        target=bundle/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(package/name,target)
    shutil.copytree(package/'licenses',bundle/'licenses',dirs_exist_ok=True)
    for distribution in ('pyinstaller','pyctr','pycryptodomex'):
        dist=importlib.metadata.distribution(distribution)
        for file in dist.files or []:
            if 'license' in file.name.lower() or 'copying' in file.name.lower():
                source=dist.locate_file(file)
                if source.is_file():shutil.copy2(source,bundle/'licenses'/(distribution+'-'+file.name))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():raise ValueError('Python runtime license is missing')
    shutil.copy2(python_license,bundle/'licenses/Python.txt')
    import tkinter
    root=tkinter.Tk();root.withdraw()
    versions={'tcl':root.tk.call('info','patchlevel'),'tk':root.tk.call('package','provide','Tk')}
    root.destroy()
    for component,version in versions.items():
        tag='core-'+version.replace('.','-')
        url=f'https://raw.githubusercontent.com/tcltk/{component}/{tag}/license.terms'
        with urllib.request.urlopen(url,timeout=30) as response:
            (bundle/'licenses'/(component+'.txt')).write_bytes(response.read())
    release=ROOT/'release';release.mkdir(exist_ok=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
                    '--name','NDS-to-CIA','--distpath',str(release),'--workpath',str(ROOT/'build/pyinstaller'),
                    '--specpath',str(ROOT/'build'),'--add-data',f'{bundle};bundle',
                    '--add-data',f'{ROOT / "assets"};assets','--collect-all','Cryptodome',
                    '--collect-all','pyctr',str(ROOT/'windows_app.py')],cwd=ROOT,check=True)
    shutil.copy2(package/'runtime/bridge.cia',release/'Bridge.cia')
    shutil.copy2(ROOT/'README.md',release/'README.md')
    shutil.copy2(ROOT/'LICENSE.txt',release/'LICENSE.txt')
    shutil.copytree(bundle/'licenses',release/'licenses',dirs_exist_ok=True)
    shutil.copy2(ROOT/'docs/THIRD_PARTY.md',release/'THIRD_PARTY.md')
    shutil.copytree(ROOT/'docs',release/'docs',dirs_exist_ok=True)
    (release/'build-info.json').write_text(json.dumps({'version':'1.1.0','source_commit':manifest['source_commit'],
        'runtime_sources':manifest['sources'],'python':sys.version.split()[0],
        'python_packages':{name:importlib.metadata.version(name) for name in ('pyinstaller','pyctr','pycryptodomex')}},indent=2)+'\n')


if __name__=='__main__':build()
