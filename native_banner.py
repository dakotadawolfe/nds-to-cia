"""Fill HOME Menu's own DS banner using locally supplied system resources.

The donor model and system font are never bundled in public packages. Meshes,
materials, skeletons and animation curves remain byte-for-byte donor data.
"""
import math
from pathlib import Path
import struct


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def relative(data, offset):
    target = offset + struct.unpack_from('<i', data, offset)[0]
    if not 0 <= target < len(data):
        raise ValueError('Resource pointer outside file')
    return target


def tiled(x, y, width):
    return ((y // 8) * (width // 8) + x // 8) * 64 + sum(
        ((x >> bit) & 1) << (2 * bit) | ((y >> bit) & 1) << (2 * bit + 1)
        for bit in range(3))


def pack_l4(pixels, width, height):
    if width % 8 or height % 8 or len(pixels) != width * height:
        raise ValueError('Invalid L4 dimensions')
    out = bytearray(width * height // 2)
    for y in range(height):
        for x in range(width):
            index = tiled(x, y, width)
            out[index // 2] |= (int(pixels[y * width + x]) >> 4) << (4 * (index & 1))
    return out


class SystemFont:
    """Read CFNT glyphs with libctru's CMAP/CWDH and sheet addressing rules."""
    def __init__(self, data):
        self.data = data
        if data[:4] != b'CFNT' or data[0x14:0x18] != b'FINF':
            raise ValueError('Expected an unmodified CFNT font file')
        self.line_feed = data[0x1d]
        self.default_index = struct.unpack_from('<H', data, 0x1e)[0]
        self.font_height, self.font_width = data[0x30:0x32]
        tg = u32(data, 0x24) - 8
        if data[tg:tg+4] != b'TGLP':
            raise ValueError('Invalid font texture section')
        self.cell_width, self.cell_height = data[tg+8:tg+10]
        self.sheet_size = u32(data, tg+12)
        self.sheets, fmt, self.cols, self.rows, self.width, self.height = struct.unpack_from('<6H', data, tg+16)
        self.sheet_offset = u32(data, tg+28)
        if fmt != 11 or self.sheet_offset + self.sheets * self.sheet_size > len(data):
            raise ValueError('Expected complete A4 system font sheets')
        self.widths = {}
        self.codes = {}
        for field, magic in ((0x28, b'CWDH'), (0x2c, b'CMAP')):
            at = u32(data, field)
            seen = set()
            while at:
                if at in seen:
                    raise ValueError('Cyclic font section chain')
                seen.add(at)
                start = at - 8
                if data[start:start+4] != magic:
                    raise ValueError('Invalid font section')
                first, last = struct.unpack_from('<HH', data, at)
                if magic == b'CWDH':
                    for i in range(first, last+1):
                        self.widths[i] = struct.unpack_from('<bBB', data, at+8+3*(i-first))
                    at = u32(data, at+4)
                else:
                    method = struct.unpack_from('<H', data, at+4)[0]
                    if method == 0:
                        base = struct.unpack_from('<H', data, at+12)[0]
                        self.codes.update((c, base+c-first) for c in range(first, last+1))
                    elif method == 1:
                        self.codes.update((c, struct.unpack_from('<H', data, at+12+2*(c-first))[0]) for c in range(first, last+1))
                    elif method == 2:
                        count = struct.unpack_from('<H', data, at+12)[0]
                        self.codes.update(struct.unpack_from('<HH', data, at+14+4*i) for i in range(count))
                    else:
                        raise ValueError('Unsupported font map')
                    at = u32(data, at+8)

    def glyph(self, char):
        index = self.codes.get(ord(char), self.default_index)
        if index == 0xffff:
            index = self.default_index
        left, width, advance = self.widths[index]
        per_sheet = self.cols * self.rows
        sheet, cell = divmod(index, per_sheet)
        if sheet >= self.sheets:
            raise ValueError('Font glyph outside texture sheets')
        x0 = (cell % self.cols) * (self.cell_width+1) + 1
        y0 = (cell // self.cols) * (self.cell_height+1) + 1
        pixels = []
        for y in range(self.cell_height):
            for x in range(width):
                # CFNT sheets store glyph rows from the top; fontCalcGlyphPos
                # flips their sampling coordinates when submitting the quad.
                pos = tiled(x0+x, y0+y, self.width)
                byte = self.data[self.sheet_offset+sheet*self.sheet_size+pos//2]
                pixels.append(((byte >> (4*(pos & 1))) & 15)*17)
        return left, width, advance, pixels

    def render(self, lines):
        # Sizes come from HOME Menu's banner_LZ.bin T_Title_00 pane.
        sx, sy = 15.5 / self.font_width, 18.6 / self.font_height
        glyph_lines = [[self.glyph(c) for c in line] for line in lines]
        if not 1 <= len(lines) <= 3:
            raise ValueError('Native DS banner supports one to three title lines')
        if any(sum(g[2] for g in line)*sx > 256 for line in glyph_lines):
            raise ValueError('Title exceeds the native DS text pane width')
        pixels = [0]* (256*64)
        feed = self.line_feed * sy
        top = (64 - ((len(lines)-1)*feed+self.cell_height*sy))/2
        for line_no, line in enumerate(glyph_lines):
            pen = (256-sum(g[2] for g in line)*sx)/2
            for left, width, advance, glyph in line:
                x0, y0 = pen+left*sx, top+line_no*feed
                for y in range(max(0, math.floor(y0)), min(64, math.ceil(y0+self.cell_height*sy))):
                    for x in range(max(0, math.floor(x0)), min(256, math.ceil(x0+width*sx))):
                        gx, gy = (x+.5-x0)/sx-.5, (y+.5-y0)/sy-.5
                        ix, iy = math.floor(gx), math.floor(gy)
                        def sample(a, b):
                            return glyph[b*width+a] if 0 <= a < width and 0 <= b < self.cell_height else 0
                        fx, fy = gx-ix, gy-iy
                        value = (sample(ix,iy)*(1-fx)+sample(ix+1,iy)*fx)*(1-fy)+(sample(ix,iy+1)*(1-fx)+sample(ix+1,iy+1)*fx)*fy
                        pixels[y*256+x] = max(pixels[y*256+x], round(value))
                pen += advance*sx
        return pixels


def texture_entries(data):
    if data[:4] != b'CGFX' or u32(data, 12) != len(data):
        raise ValueError('Invalid donor CGFX')
    count, dictionary = u32(data, 0x24), relative(data, 0x28)
    entries = {}
    for i in range(count):
        node = dictionary+0x1c+i*16
        name_at = relative(data, node+8)
        name = data[name_at:data.index(0, name_at)].decode('ascii')
        tx = relative(data, node+12)
        if u32(data, tx) != 0x20000011 or data[tx+4:tx+8] != b'TXOB':
            raise ValueError('Expected image texture')
        im = relative(data, tx+0x38)
        entries[name] = (tx, im, relative(data, im+12), u32(data, im+8))
    return entries


def bind_common(data):
    """Register the donor model/animations under the CXI loader's COMMON name.

    HOME Menu's built-in DS renderer asks for BannerDS explicitly. Its ordinary
    CBMD path instead asks for COMMON, including skeletal/material animations.
    The one-entry Patricia dictionaries must change their reference bit too.
    """
    result = bytearray(data)
    for slot in (0, 9, 10):
        count = u32(data, 0x1c+slot*8)
        if count != 1:
            raise ValueError('Expected one native model and one animation of each kind')
        dictionary = relative(data, 0x20+slot*8)
        if data[dictionary:dictionary+4] != b'DICT' or u32(data,dictionary+8) != 1:
            raise ValueError('Invalid native binding dictionary')
        node = dictionary+0x1c
        root_links = struct.unpack_from('<HH',data,dictionary+0x10)
        node_links = struct.unpack_from('<HH',data,node+4)
        if root_links != (1,0) or node_links != (0,1):
            raise ValueError('Unsupported native binding tree')
        obj = relative(data,node+12)
        signature_offset = obj+4 if slot == 0 else obj
        if data[signature_offset:signature_offset+4] != (b'CMDL' if slot == 0 else b'CANM'):
            raise ValueError('Invalid native model/animation binding')
        object_name = obj+12 if slot == 0 else obj+8
        for pointer in (node+8,object_name):
            start = relative(data,pointer)
            if data[start:start+9] != b'BannerDS\0':
                raise ValueError('Unexpected donor model/animation name')
            result[start:start+9] = b'COMMON\0\0\0'
        struct.pack_into('<I',result,node,46)  # highest differing bit vs empty root
    return result


def make_native_banner(directory, banner, lines, assets):
    assets = Path(assets)
    donor = (assets/'BannerDS.bin').read_bytes()
    entries = texture_entries(donor)
    expected = {'DmyIcon_00': (64,64,7), 'DmyIconMask_00': (64,64,10), 'DmyText_00': (64,256,10)}
    for name, (h,w,fmt) in expected.items():
        tx,im,offset,size = entries[name]
        if (u32(donor,tx+0x18),u32(donor,tx+0x1c),u32(donor,tx+0x34)) != (h,w,fmt):
            raise ValueError('Unexpected native DS texture layout')
        if offset+size > len(donor):
            raise ValueError('Truncated donor texture')
    if len(banner)<0x240:
        raise ValueError('A native DS banner requires the original game icon')
    font = SystemFont((assets/'cbf_std.bcfnt').read_bytes())
    # The native material expects dark letters on a white L4 texture, with
    # top-down rows. Its UVs differ from the discarded glTF conversion.
    text = pack_l4([255-p for p in font.render(lines)],256,64)
    icon = bytearray(64*64*2)
    for y in range(64):
        for x in range(64):
            # The native mask supplies the rounded 48-pixel label. Retain
            # the original 32-pixel DS icon at its center, without filtering.
            a,b = x-16,y-16
            index = 0
            if 0 <= a < 32 and 0 <= b < 32:
                offset = 0x20+((b//8)*4+a//8)*32+(b%8)*4+(a%8)//2
                index = (banner[offset] >> (4*(a & 1))) & 15
            c = struct.unpack_from('<H',banner,0x220+index*2)[0] if index else 0x7fff
            r,g,blue = c & 31,(c>>5)&31,(c>>10)&31
            color = (r<<11)|(((g<<1)|(g>>4))<<5)|blue
            struct.pack_into('<H',icon,tiled(x,y,64)*2,color)
    data = bind_common(donor)
    for name,pixels in [('DmyText_00',text)]:
        _,_,offset,size=entries[name]
        if len(pixels)!=size: raise ValueError('Texture size mismatch')
        data[offset:offset+size]=pixels
    # Append the larger color texture; preserve all existing model pointers.
    tx,im,_,_=entries['DmyIcon_00']
    data.extend(bytes(-len(data)%128))
    start=len(data);data.extend(icon)
    struct.pack_into('<II',data,tx+0x20,0x6754,0x8363)
    struct.pack_into('<I',data,tx+0x34,3)  # RGB565
    struct.pack_into('<Ii',data,im+8,len(icon),start-(im+12))
    struct.pack_into('<I',data,im+20,16)
    imag=0x14+u32(data,0x18)
    if data[imag:imag+4]!=b'IMAG': raise ValueError('Missing donor image block')
    struct.pack_into('<I',data,imag+4,len(data)-imag)
    struct.pack_into('<I',data,12,len(data))
    validate_native_banner(data, donor)
    Path(directory,'banner.cgfx').write_bytes(data)
    return bytes(data)


def validate_native_banner(data, donor):
    """Reject geometry, animation, material or unrelated texture changes."""
    entries = texture_entries(donor)
    result_entries = texture_entries(data)
    if entries.keys() != result_entries.keys():
        raise ValueError('Native resource inventory changed')
    original = bind_common(donor)
    result = bytearray(data[:len(donor)])
    tx,im,_,_=entries['DmyIcon_00']
    _,_,text_at,text_size=entries['DmyText_00']
    imag=0x14+u32(donor,0x18)
    allowed=[(12,4),(imag+4,4),(tx+0x20,8),(tx+0x34,4),(im+8,8),(im+20,4),(text_at,text_size)]
    for offset,size in allowed:
        original[offset:offset+size]=bytes(size)
        result[offset:offset+size]=bytes(size)
    if original!=result:
        raise ValueError('Native model or animation was modified')
    _,_,offset,size=result_entries['DmyIcon_00']
    if size!=8192 or offset<len(donor) or offset+size!=len(data) or u32(data,tx+0x34)!=3:
        raise ValueError('Invalid replacement icon texture')
    if u32(data,imag+4)!=len(data)-imag:
        raise ValueError('Invalid image block length')
