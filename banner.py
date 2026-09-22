"""Read original DS icon and title metadata."""
import struct


def title_lines(banner, fallback='Nintendo DS'):
    if len(banner) >= 0x440:
        text = banner[0x340:0x440].decode('utf-16le', errors='replace').split('\0')[0]
        lines = [s.strip() for s in text.replace('\r', '').split('\n') if s.strip()]
        if lines:
            return lines
    return [fallback]


def metadata(banner, fallback, override=None):
    lines = title_lines(banner, fallback)
    publisher = lines[-1] if len(lines) > 1 else ''
    name = ' '.join(lines[:-1]) if publisher else lines[0]
    if override:
        name = override
        lines = [override] + ([publisher] if publisher else [])
    return name, publisher, lines


def ds_icon(banner):
    pixels = []
    for y in range(32):
        for x in range(32):
            if len(banner) < 0x240:
                pixels.append((72, 76, 84, 255) if 5 <= x < 27 and 5 <= y < 27 else (255,255,255,255))
                continue
            offset = 0x20 + ((y//8)*4+x//8)*32 + (y%8)*4+(x%8)//2
            index = (banner[offset] >> (4*(x & 1))) & 15
            color = struct.unpack_from('<H', banner, 0x220+index*2)[0]
            pixels.append(tuple(((color >> shift) & 31)*255//31 for shift in (0,5,10))+(255,)
                          if index else (255,255,255,255))
    return pixels
