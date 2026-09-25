"""Ship the release source and pinned upstream source archives together."""
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'release';out.mkdir(exist_ok=True)
files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
with zipfile.ZipFile(out/'NDS-to-CIA-1.1.0-Source.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        if name:archive.write(ROOT/name,'nds-to-cia/'+name)
    for source in sorted((ROOT/'.build-v2/archives').glob('*.zip')):
        archive.write(source,'upstream/'+source.name)
    archive.writestr('BUILDING.txt','The nds-to-cia folder contains the source and exact runtime patch recipe.\n'
                    'The upstream folder contains the original pinned source archives.\n'
                    'Copy upstream/*.zip into nds-to-cia/.build-v2/archives/ before building to reuse them.\n'
                    'See nds-to-cia/docs/BUILDING.md for the compiler image and Windows build steps.\n')
