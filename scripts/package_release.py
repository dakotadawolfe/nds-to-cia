"""Package only approved release files after the Windows smoke tests pass."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
release=ROOT/'release'
for name in ('self-test.json','conversion-test.json'):
    if not json.loads((ROOT/'build'/name).read_text())['success']:
        raise SystemExit(f'Packaged EXE test failed: {name}')
files=['NDS-to-CIA.exe','Bridge.cia','README.md','LICENSE.txt','THIRD_PARTY.md','build-info.json']
files += [str(p.relative_to(release)).replace('\\','/') for p in sorted((release/'licenses').iterdir()) if p.is_file()]
files += [str(p.relative_to(release)).replace('\\','/') for p in sorted((release/'docs').glob('*.md'))]
with zipfile.ZipFile(release/'NDS-to-CIA-1.1.0-Windows-x64.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in files:archive.write(release/name,'NDS-to-CIA/'+name)
checks=[]
for name in ('NDS-to-CIA.exe','Bridge.cia','NDS-to-CIA-1.1.0-Windows-x64.zip','NDS-to-CIA-1.1.0-Source.zip'):
    checks.append(hashlib.sha256((release/name).read_bytes()).hexdigest()+'  '+name)
(release/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
