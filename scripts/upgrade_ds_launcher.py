"""Update a prepared card's DS launchers from a verified build's test CIA.

Keeps NCCH sizes, title IDs, game RomFS and artwork unchanged. Recomputes TMD
hashes and SD CMD authentication. Requires pyctr==0.7.6 and private owner keys.
Encrypted originals are backed up before publication; no NAND writes are made.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile


def sha(data):
    return hashlib.sha256(data).digest()


def open_sd(tree, relative, crypto):
    from pyctr.crypto import Keyslot
    # SDFilesystem.open in pyctr 0.7.6 leaves its underlying file handle open.
    # Own it explicitly so Windows permits atomic replacement after validation.
    return crypto.create_ctr_io(Keyslot.SD, (tree / relative).open('rb'),
                                crypto.sd_path_to_iv('/' + relative), closefd=True)


def section(data, offset):
    start, length = struct.unpack_from('<II', data, offset)
    start, length = start * 512, length * 512
    if start < 0xA00 or start + length > len(data):
        raise ValueError('Invalid NCCH section')
    return start, length


def validate_ncch(data):
    if data[0x100:0x104] != b'NCCH' or data[0x150:0x160].rstrip(b'\0') != b'CTR-H-DCSD':
        raise ValueError('Expected a DS Clean SD NCCH')
    if not data[0x18F] & 4 or struct.unpack_from('<I', data, 0x180)[0] != 0x400:
        raise ValueError('Unsupported encrypted NCCH or extended header')
    if struct.unpack_from('<I', data, 0x104)[0] * 512 != len(data):
        raise ValueError('NCCH content length mismatch')
    if sha(data[0x200:0x600]) != data[0x160:0x180]:
        raise ValueError('NCCH extended-header hash mismatch')
    start, length = section(data, 0x1A0)
    hash_size = struct.unpack_from('<I', data, 0x1A8)[0] * 512
    if not 0 < hash_size <= length or sha(data[start:start + hash_size]) != data[0x1C0:0x1E0]:
        raise ValueError('NCCH ExeFS header hash mismatch')
    entries = {}
    for i in range(10):
        name, offset, size = struct.unpack_from('<8sII', data, start + i * 16)
        name = name.rstrip(b'\0')
        if not name:
            continue
        if name in entries or offset + size > length - 512:
            raise ValueError('Invalid ExeFS entry')
        absolute = start + 512 + offset
        digest_pos = start + 0x1E0 - i * 32
        if sha(data[absolute:absolute + size]) != data[digest_pos:digest_pos + 32]:
            raise ValueError('ExeFS resource hash mismatch')
        entries[name] = (i, absolute, size)
    if set(entries) != {b'.code', b'banner', b'icon', b'logo'}:
        raise ValueError('Unsupported ExeFS resources')
    section(data, 0x1B0)
    return entries


def replace_launcher(original, template):
    old_entries, new_entries = validate_ncch(original), validate_ncch(template)
    index, code_start, old_size = old_entries[b'.code']
    _, new_start, new_size = new_entries[b'.code']
    if new_size > old_size:
        raise ValueError('New launcher does not fit the existing code allocation')
    if original[0x188:0x190] != template[0x188:0x190]:
        raise ValueError('Launcher NCCH format changed')
    capabilities = bytearray(template[0x200:0xA00])
    for offset in (0x3C8, 0x400, 0x800):
        capabilities[offset - 0x200:offset - 0x200 + 8] = original[0x118:0x120]
    # Access-descriptor signatures differ with title identity. Retain the old
    # signed descriptor after comparing its actual capabilities and public key.
    if capabilities[0x40:0x400] != original[0x240:0x600] or \
            capabilities[0x500:] != original[0x700:0xA00]:
        raise ValueError('Launcher capabilities or storage changed')
    result = bytearray(original)
    result[0x200:0x240] = template[0x200:0x240]
    result[code_start:code_start + old_size] = bytes(old_size)
    result[code_start:code_start + new_size] = template[new_start:new_start + new_size]
    exefs, length = section(original, 0x1A0)
    struct.pack_into('<I', result, exefs + index * 16 + 12, new_size)
    digest_pos = exefs + 0x1E0 - index * 32
    result[digest_pos:digest_pos + 32] = sha(result[code_start:code_start + new_size])
    result[0x160:0x180] = sha(result[0x200:0x600])
    hash_size = struct.unpack_from('<I', result, 0x1A8)[0] * 512
    result[0x1C0:0x1E0] = sha(result[exefs:exefs + hash_size])
    validate_ncch(result)
    romfs, romfs_size = section(original, 0x1B0)
    if result[romfs:romfs + romfs_size] != original[romfs:romfs + romfs_size]:
        raise ValueError('Game RomFS changed')
    for name in (b'banner', b'icon', b'logo'):
        _, offset, size = old_entries[name]
        if result[offset:offset + size] != original[offset:offset + size]:
            raise ValueError('Artwork changed')
    return result


def load_template(path):
    from pyctr.type.cia import CIAReader
    with CIAReader(path) as cia:
        if len(cia.contents) != 1:
            raise ValueError('Expected the build storage-test CIA')
        with cia.open_raw_section(0) as content:
            template = content.read()
        record = cia.tmd.chunk_records[0]
        if len(template) != record.size or sha(template) != record.hash:
            raise ValueError('Template CIA hash mismatch')
    entries = validate_ncch(template)
    _, offset, size = entries[b'.code']
    if b'Launcher 1.1.0 entered' not in template[offset:offset + size]:
        raise ValueError('Expected the uncompressed 1.1.0 launcher')
    return template


def upgraded_metadata(raw, content, crypto):
    from pyctr.crypto import Keyslot
    from pyctr.type.tmd import TitleMetadataReader
    tmd = TitleMetadataReader.load(io.BytesIO(raw))
    if len(tmd.chunk_records) != 1 or tmd.chunk_records[0].cindex != 0:
        raise ValueError('Only single-content DS packages are supported')
    record = tmd.chunk_records[0]
    if record.size != len(content):
        raise ValueError('Content size changed')
    tmd.chunk_records = (record._replace(hash=sha(content)),)
    tmd.info_records = tuple(r._replace(hash=sha(b''.join(bytes(c) for c in
                       tmd.chunk_records[r.index_offset:r.index_offset + r.command_count])))
                       if r.command_count else r for r in tmd.info_records)
    updated = bytes(tmd)
    TitleMetadataReader.load(io.BytesIO(updated))
    header = struct.pack('<4I', 1, 1, 1, 1)
    cmac = crypto.create_cmac_object(Keyslot.CMACSDNAND)
    cmac.update(header)
    content_id = int(record.id, 16)
    content_cmac = crypto.create_cmac_object(Keyslot.CMACSDNAND)
    content_cmac.update(sha(content[0x100:0x200] + struct.pack('<II', 0, content_id)))
    cmd = header + cmac.digest() + struct.pack('<II', content_id, content_id) + content_cmac.digest()
    return updated, cmd


def publish(sd, crypto, tree, replacements, backup):
    from pyctr.crypto import Keyslot
    staged = []
    try:
        for relative, data in replacements:
            target = tree / relative
            original = backup / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            if original.exists():
                raise ValueError('Backup already exists; use a fresh backup directory')
            shutil.copy2(target, original)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ds-upgrade-', delete=False) as file:
                temporary = Path(file.name)
            staged.append((relative, target, temporary, original))
            iv = crypto.sd_path_to_iv('/' + relative)
            with temporary.open('wb') as file, crypto.create_ctr_io(Keyslot.SD, file, iv) as output:
                output.write(data)
                output.flush()
            with temporary.open('rb') as file, crypto.create_ctr_io(Keyslot.SD, file, iv) as check:
                if sha(check.read()) != sha(data):
                    raise ValueError('Encrypted staging readback failed')
        for relative, target, temporary, original in staged:
            os.replace(temporary, target)
        for relative, data in replacements:
            with open_sd(tree, relative, crypto) as source:
                if sha(source.read()) != sha(data):
                    raise ValueError('Published SD readback failed')
    except Exception:
        for _, target, _, original in staged:
            shutil.copy2(original, target)
        raise
    finally:
        for _, _, temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def upgrade(root, boot9, template_path, backup):
    from pyctr.crypto import CryptoEngine
    from pyctr.type.sd import SDFilesystem
    root = Path(root).resolve(strict=True)
    crypto = CryptoEngine(boot9=str(boot9))
    keys = [p for p in (root / 'movable.sed', root / 'moveable.sed') if p.is_file()]
    if not keys or any(p.read_bytes() != keys[0].read_bytes() for p in keys):
        raise ValueError('One unambiguous matching movable.sed is required')
    sd = SDFilesystem(root / 'Nintendo 3DS', crypto=crypto, sd_key_file=keys[0])
    if len(sd.id1s) != 1:
        raise ValueError('Expected one matching SD tree')
    tree = root / 'Nintendo 3DS' / crypto.id0.hex() / sd.current_id1
    template = load_template(template_path)
    report = []
    for title in sorted((tree / 'title' / '00040000').iterdir()):
        for app in sorted((title / 'content').glob('*.app')):
            relative = app.relative_to(tree).as_posix()
            with open_sd(tree, relative, crypto) as source:
                header = source.read(0x200)
                if header[0x150:0x160].rstrip(b'\0') != b'CTR-H-DCSD':
                    continue
                source.seek(0)
                content = source.read()
            tmd_paths = list((title / 'content').glob('*.tmd'))
            if len(tmd_paths) != 1:
                raise ValueError('Expected one installed TMD')
            tmd_relative = tmd_paths[0].relative_to(tree).as_posix()
            with open_sd(tree, tmd_relative, crypto) as source:
                raw = source.read()
            from pyctr.type.tmd import TitleMetadataReader
            tmd = TitleMetadataReader.load(io.BytesIO(raw))
            if len(tmd.chunk_records) != 1 or tmd.chunk_records[0].hash != sha(content) or \
                    tmd.chunk_records[0].id != app.stem or tmd.title_id != '00040000' + title.name:
                raise ValueError('Original content/TMD validation failed')
            replacement = replace_launcher(content, template)
            if replacement == content:
                continue
            new_tmd, cmd = upgraded_metadata(raw, replacement, crypto)
            cmd_relative = (title / 'content/cmd/00000001.cmd').relative_to(tree).as_posix()
            publish(sd, crypto, tree, [(relative, replacement), (tmd_relative, new_tmd),
                                      (cmd_relative, cmd)], Path(backup))
            report.append({'title_id': tmd.title_id, 'before': sha(content).hex(),
                           'after': sha(replacement).hex(), 'size': len(replacement)})
            print(f'{tmd.title_id}: launcher updated, game and artwork preserved', flush=True)
    return {'template_sha256': sha(Path(template_path).read_bytes()).hex(),
            'hardware_tested': False, 'updated_titles': report}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sd-root', 'boot9', 'template-cia', 'backup-dir', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = upgrade(args.sd_root, args.boot9, args.template_cia, args.backup_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
