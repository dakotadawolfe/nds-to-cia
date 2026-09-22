from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
from banner import metadata, ds_icon


class BannerTests(unittest.TestCase):
    def banner(self, text):
        b=bytearray(0x840)
        b[0x20:0x220]=bytes([0x11])*512
        struct.pack_into('<H',b,0x222,31)
        raw=text.encode('utf-16le');b[0x340:0x340+len(raw)]=raw
        return b

    def test_title_publisher_and_line_breaks(self):
        b=self.banner('Pokémon\nHeartGold Version\nNintendo')
        name,publisher,lines=metadata(b,'wrong file name')
        self.assertEqual(name,'Pokémon HeartGold Version')
        self.assertEqual(publisher,'Nintendo')
        self.assertEqual(lines,['Pokémon','HeartGold Version','Nintendo'])
        self.assertEqual(metadata(b,'unused','Custom name'),('Custom name','Nintendo',['Custom name','Nintendo']))
        self.assertEqual(metadata(b'','Homebrew'),('Homebrew','',['Homebrew']))

    def test_ds_palette_and_transparency(self):
        b=self.banner('Title\nPublisher');b[0x20]=0x10
        pixels=ds_icon(b)
        self.assertEqual(pixels[0],(255,255,255,255))
        self.assertEqual(pixels[1],(255,0,0,255))
