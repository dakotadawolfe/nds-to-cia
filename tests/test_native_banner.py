from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from native_banner import SystemFont, bind_common, make_native_banner, pack_l4, tiled, validate_native_banner, relative


def font_fixture():
    data = bytearray(512)
    data[:4] = b'CFNT'; data[0x14:0x18] = b'FINF'
    data[0x1d] = 30; data[0x30:0x32] = bytes([30,25])
    struct.pack_into('<3I',data,0x24,0x3c,0x68,0x88)
    data[0x34:0x38] = b'TGLP'; data[0x3c:0x40] = bytes([8,8,7,8])
    struct.pack_into('<I6HI',data,0x40,128,1,11,1,1,16,16,0x100)
    data[0x60:0x64] = b'CWDH'
    struct.pack_into('<HHI',data,0x68,0,0,0)
    data[0x70:0x73] = bytes([0,8,9])
    data[0x80:0x84] = b'CMAP'
    struct.pack_into('<HHHHIH',data,0x88,65,65,0,0,0,0)
    # Asymmetric glyph catches vertical flips in the font sheet decoder.
    for x in range(1,9):
        index=tiled(x,1,16)
        data[0x100+index//2] |= 15 << (4*(index&1))
    return data


def model_fixture():
    data = bytearray(0x800)
    data[:4] = b'CGFX';data[0x14:0x18] = b'DATA'
    struct.pack_into('<I',data,0x18,0x800-0x14)
    struct.pack_into('<Ii',data,0x24,3,0x94-0x28)
    data[0x94:0x98] = b'DICT'
    for i,slot in enumerate((0,9,10)):
        d=0x400+i*0x80;obj=d+0x30;name=d+0x60
        struct.pack_into('<Ii',data,0x1c+slot*8,1,d-(0x20+slot*8))
        data[d:d+4]=b'DICT';struct.pack_into('<II',data,d+4,44,1)
        struct.pack_into('<iHHii',data,d+12,-1,1,0,0,0)
        struct.pack_into('<iHHii',data,d+28,62,0,1,name-(d+36),obj-(d+40))
        if slot==0:
            data[obj+4:obj+8]=b'CMDL';field=obj+12
        else:
            data[obj:obj+4]=b'CANM';field=obj+8
        struct.pack_into('<i',data,field,name-field)
        data[name:name+9]=b'BannerDS\0'
    data.extend(b'IMAG'+bytes(8))
    for i,(name,h,w,fmt) in enumerate([('DmyIcon_00',64,64,7),('DmyIconMask_00',64,64,10),('DmyText_00',64,256,10)]):
        node=0xb0+i*16;tx=0x100+i*0x60;im=tx+0x3c;name_at=0x300+i*32
        raw=name.encode()+b'\0';data[name_at:name_at+len(raw)]=raw
        struct.pack_into('<ii',data,node+8,name_at-node-8,tx-node-12)
        struct.pack_into('<I4s',data,tx,0x20000011,b'TXOB')
        struct.pack_into('<II',data,tx+0x18,h,w)
        struct.pack_into('<Ii',data,tx+0x34,fmt,4)
        size=w*h if fmt==7 else w*h//2
        struct.pack_into('<IIIi',data,im,h,w,size,len(data)-(im+12))
        data.extend(bytes([0xff])*size)
    struct.pack_into('<I',data,12,len(data));struct.pack_into('<I',data,0x804,len(data)-0x800)
    return data


class NativeBannerTests(unittest.TestCase):
    def test_cxi_dictionary_lookup_finds_common(self):
        def lookup(data,slot,name):
            d=relative(data,0x20+slot*8);parent=d+12
            child=d+12+struct.unpack_from('<H',data,parent+4)[0]*16
            def bit(node):return struct.unpack_from('<I',data,node)[0]
            while bit(parent)>bit(child):
                ref=bit(child);byte=ref//8
                direction=(name[byte]>>(ref%8))&1 if byte<len(name) else 0
                parent,child=child,d+12+struct.unpack_from('<H',data,child+4+direction*2)[0]*16
            at=relative(data,child+8)
            return bytes(data[at:data.index(0,at)])==name
        donor=model_fixture();fixed=bind_common(donor)
        for slot in (0,9,10):
            self.assertTrue(lookup(donor,slot,b'BannerDS'))
            self.assertFalse(lookup(donor,slot,b'COMMON'))
            self.assertTrue(lookup(fixed,slot,b'COMMON'))
            self.assertFalse(lookup(fixed,slot,b'BannerDS'))

    def test_font_orientation_and_metrics(self):
        font=SystemFont(font_fixture())
        left,width,advance,pixels=font.glyph('A')
        self.assertEqual((left,width,advance),(0,8,9))
        self.assertEqual(pixels[:8],[255]*8)
        self.assertEqual(pixels[-8:],[0]*8)

    def test_font_cycle_rejected(self):
        data=font_fixture();struct.pack_into('<I',data,0x90,0x88)
        with self.assertRaisesRegex(ValueError,'Cyclic'):SystemFont(data)

    def test_native_l4_orientation(self):
        pixels=[255]*8+[0]*56
        packed=pack_l4(pixels,8,8)
        for y in range(8):
            for x in range(8):
                i=tiled(x,y,8)
                self.assertEqual((packed[i//2]>>(4*(i&1)))&15,15 if y==0 else 0)

    def test_donor_geometry_preserved_and_damage_rejected(self):
        donor=model_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'BannerDS.bin').write_bytes(donor)
            (root/'cbf_std.bcfnt').write_bytes(font_fixture())
            result=make_native_banner(root,bytes(0x840),['A'],root)
            validate_native_banner(result,donor)
            broken=bytearray(result);broken[0x80]^=1
            with self.assertRaisesRegex(ValueError,'model or animation'):validate_native_banner(broken,donor)
            # Reproduce the invisible 0.2.6 package with unbound donor names.
            unbound=bytearray(result)
            for i in range(3):
                d=0x400+i*0x80;name=d+0x60
                unbound[name:name+9]=b'BannerDS\0'
                struct.pack_into('<I',unbound,d+28,62)
            with self.assertRaisesRegex(ValueError,'model or animation'):validate_native_banner(unbound,donor)


if __name__=='__main__':unittest.main()
