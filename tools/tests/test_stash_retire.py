"""Native cleanup byte-conservation and origin tests (no player saves)."""
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from tools import d2save
ROOT=Path(__file__).resolve().parents[2]
EXE=ROOT/'build/plugin/tests/Release/stash_retire_codec.exe'
T=d2save.Tables.from_excel() if Path(d2save.EXCEL).exists() else None
def item(code='r01',page=1,**kw):
    return dict(dict(flags=0x00A80010,b105=5,version=5,location=0,equip=0,x=0,y=0,page=page,code=code,filled=0,guid=123),**kw)
def save(items,other=b'JM\0\0jfJM\0\0kf\0'):
    head=bytearray(0x340);struct.pack_into('<II',head,0,d2save.SIG,0x44520005);head[0x18]=4;head[0x1b]=1
    return d2save.fix_header(bytes(head)+d2save.write_char_stats([dict(id=0,value=20)],T)+b'if'+bytes(30)+d2save.write_item_list(items,T)+other)
def sidecar(data,charm=False,version="0.1.18",owner=None):
    """A D2RL v2 sidecar for `data` recording mxl2012-core `version` and, with `charm`, CharmInv; `owner` names another
    page-6 owner DLL (invtabs.dll) recorded instead."""
    body=bytearray(0x154-0x2c)
    struct.pack_into('<II',body,8,struct.unpack_from('<I',data,12)[0],len(data));body[16:48]=hashlib.sha256(data).digest()
    owners=((b'd2rl-charm-inv.dll',) if charm else ())+((owner.encode(),) if owner else ())
    for s in (b'mxl2012-core.dll',)+owners:
        body+=struct.pack('<I',len(s))+s
        if s==b'mxl2012-core.dll':
            v=version.encode();body+=struct.pack('<I',len(v))+v
    return b'D2RL'+struct.pack('<HHI',2,0x2c,len(body))+hashlib.sha256(body).digest()+body
@unittest.skipUnless(EXE.exists() and T is not None, "build the native codec and data tables first")
class Retire(unittest.TestCase):
    def run_plan(self,a,b,ok=True):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
            p=Path(td);(p/'a').write_bytes(a);(p/'b').write_bytes(b)
            r=subprocess.run([str(EXE),str(p/'a'),str(p/'b'),str(p/'c'),str(p/'d')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0 if ok else 1,r.stdout+r.stderr)
            return ((p/'c').read_bytes(),(p/'d').read_bytes(),r.stdout) if ok else None
    def test_deletes_only_old_player_page_and_keeps_other_bytes(self):
        keep=[item(page=p,guid=p) for p in (1,4,5)]
        # Corpse, mercenary and golem include page-7 shaped items: never remove these.
        suffix=b'JM\1\0'+bytes(12)+d2save.write_item_list([item(page=7)],T)+b'jf'+d2save.write_item_list([item(page=7)],T)+b'kf\1'+d2save.write_item(item(page=7),T)+b'TAIL'
        a=save(keep+[item(page=7),item(page=7)],suffix);b=sidecar(a)
        c,d,out=self.run_plan(a,b)
        self.assertEqual(c,save(keep,suffix));self.assertEqual(d2save.check_sidecar(c,d),[]);self.assertIn('removed=2',out)
        self.assertEqual(d[:12],b[:12]);self.assertEqual(d[0x5c:],b[0x5c:])
    def test_real_normal_misc_records_are_bounded_and_removed(self):
        raw = [
            '000088000505109c7f78d07ff2140c080000cec7d4a8eaf717eda166d6d6e341a0dbfbff07',
            '002088000505141c1f13f292e794020201f7567a93b18e8fe257d904c49fcf7fa7fdff03',
            '00208800050518fc9b44583e33450a086302c524451254d3616f59b7520ef3d696ff7f',
        ]
        old = [d2save.read_item(bytes.fromhex(r), 0, T)[0] for r in raw]
        keep = [dict(i, page=1) for i in old]
        a = save(old + keep); c, _, _ = self.run_plan(a, sidecar(a))
        self.assertEqual(c, save(keep))
    def test_no_page2_is_byte_identical(self):
        a=save([item(page=1),item(page=5)]);b=sidecar(a);c,d,_=self.run_plan(a,b);self.assertEqual((c,d),(a,b))
    def test_charminv_origin_preserves_charms_and_all_page6_contents(self):
        a=save([item('x1x',page=7),item(page=7)]);b=sidecar(a,True)
        for _ in range(3):
            c,d,out=self.run_plan(a,b);self.assertEqual((c,d),(a,b));self.assertIn('charmOrigin=1',out)
    def test_socketed_children_removed_only_with_parent(self):
        parent=dict(flags=0x00880810,b105=5,version=5,location=0,equip=0,x=0,y=0,page=7,code='100',filled=1,id=11,ilvl=12,quality=2,sockets=1,maxdur=0,children=[item(location=6,page=0)])
        survivor=dict(parent,page=1,id=22)
        a=save([parent,survivor]);c,_,_=self.run_plan(a,sidecar(a));self.assertEqual(c,save([survivor]))
    def test_coordinates_and_item_type_do_not_identify_origin(self):
        a=save([item('x1x',page=7,x=9,y=3)]);c,_,_=self.run_plan(a,sidecar(a));self.assertEqual(c,save([]))
    def test_second_cleanup_is_noop(self):
        a=save([item(page=7),item(page=5)]);c,d,_=self.run_plan(a,sidecar(a));e,f,_=self.run_plan(c,d);self.assertEqual((e,f),(c,d))
    def test_bad_pair_checksum_format_and_unknown_origin_refuse(self):
        a=save([item(page=7)]);b=sidecar(a)
        self.run_plan(a,b[:-1],False);self.run_plan(a,sidecar(save([])),False)
        damaged=bytearray(a);damaged[-1]^=1;self.run_plan(damaged,b,False)
        unknown=bytearray(b);unknown[-15:]=b'unknown-file.xx';unknown[12:44]=hashlib.sha256(unknown[44:]).digest();self.run_plan(a,unknown,False)
    def test_page6_owners_charminv_and_invtabs_and_neither(self):
        # both page-6 owners keep every page-6 item (charms and anything else); with neither and an old core, page 6 is the
        # retired personal stash page 2 and goes
        a=save([item('x1x',page=7),item(page=7,x=12,y=15),item(page=5)])
        for owner in ('d2rl-charm-inv.dll','invtabs.dll'):
            with self.subTest(owner=owner):
                b=sidecar(a,owner=owner);c,d,out=self.run_plan(a,b);self.assertEqual((c,d),(a,b));self.assertIn('charmOrigin=1',out)
        c,d,out=self.run_plan(a,sidecar(a));self.assertEqual(c,save([item(page=5)]));self.assertIn('removed=2 charmOrigin=0',out)
        self.assertEqual(d2save.check_sidecar(c,d),[])
        # a name that only ends like an owner is not one (length-prefixed field match)
        c,_,out=self.run_plan(a,sidecar(a,owner='notinvtabs.dll'));self.assertIn('removed=2',out)
    def test_updated_core_marker_survives_absent_charminv_record(self):
        a=save([item('x1x',page=7)])
        for version in ('0.1.19','0.1.20','0.2.0','1.0.0'):
            b=sidecar(a,False,version);c,d,_=self.run_plan(a,b);self.assertEqual((c,d),(a,b))
    def test_complex_item_layouts_are_copied_verbatim(self):
        # Exercise all quality branches, personalization, runewords, stat pairs,
        # parameterized stats, tomes, armor/durability and non-simple padding.
        rows=[]
        for code in ('100','600','x1x','tbk'):
            for quality in range(1,9):
                it=dict(flags=0x05880810,b105=5,version=5,location=0,equip=0,x=0,y=0,page=5,
                        code=code,filled=0,id=quality,ilvl=99,quality=quality,sockets=2,maxdur=3,dur=2,defense=7,
                        personal='Alpha',runeword_id=12,set_mask=3,
                        stats=[dict(id=17,value=20,lead=True),dict(id=18,value=21,lead=False)])
                rows.append(it)
        a=save(rows+[item(page=7)]);c,_,_=self.run_plan(a,sidecar(a));self.assertEqual(c,save(rows))
    def test_interrupted_pairs_and_stale_journal(self):
        a=save([item(page=7),item(page=5)]);b=sidecar(a)
        c,d,_=self.run_plan(a,b)
        newer=save([item('x1x',page=7),item(page=5)]);newside=sidecar(newer,False,'0.1.19')
        for left,right,rollback in ((a,b,0),(a,d,1),(c,b,1),(c,d,0),(newer,newside,0)):
            with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
                p=Path(td)
                for name,data in zip(('a','b','c','d'),(a,b,left,right)):(p/name).write_bytes(data)
                r=subprocess.run([str(EXE),'--recover',*[str(p/name) for name in ('a','b','c','d')]],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr);self.assertIn('rollback='+str(rollback),r.stdout)
        # An unrelated newer save paired with stale metadata must be refused, never restored over.
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
            p=Path(td)
            for name,data in zip(('a','b','c','d'),(a,b,newer,b)):(p/name).write_bytes(data)
            r=subprocess.run([str(EXE),'--recover',*[str(p/name) for name in ('a','b','c','d')]],capture_output=True)
            self.assertEqual(r.returncode,1)
    def test_real_chronicle_records_and_quest_difficulty(self):
        # Exact game-written item bytes from DevMenuD / DevMenuH. Chronicle data
        # follows the stat terminator; interpreting it as the next item caused
        # the release startup failure.
        records = [
            '10008810050510e4ed9180a8a1a93e3e62010000e08300003e1000e08301003ef800100ef0000ce00350c0ff3ffd82f312720000',
            '10008810050510e4fcd8306f8ab8ffafd30100f8ffa75f585f420e00',
        ]
        items = [d2save.read_item(bytes.fromhex(r), 0, T)[0] for r in records]
        for it, raw in zip(items, records):
            self.assertEqual(d2save.write_item(it, T), bytes.fromhex(raw))
            self.assertEqual(it['chronicle_source'], 3060)
        for code in ('bks', 'qey'):
            items.append(item(code, quest_difficulty=2))
        a = save(items + [item(page=7)])
        c, _, _ = self.run_plan(a, sidecar(a))
        self.assertEqual(c, save(items))

    def test_chronicle_recipients_and_advanced_stacks(self):
        for compact in (False, True):
            it = dict(flags=0x10880010 | (0x20000000 if compact else 0), b105=5,
                      version=5, location=0, page=1, code='rin', quality=2,
                      chronicle_source=3060, chronicle_timestamp=123,
                      chronicle_count=2, chronicle_recipient0=0x123456789abcdef0,
                      chronicle_recipient1=42, advanced_stack_present=1, advanced_stack=3)
            a = save([it, item(page=7)])
            c, _, _ = self.run_plan(a, sidecar(a))
            self.assertEqual(c, save([it]))

    @unittest.skipUnless(os.name == 'nt', 'Windows runtime folder scan')
    def test_bad_character_does_not_block_or_change_other_characters(self):
        a = save([item(page=7)])
        class UnknownStat(d2save._Codec):
            def props(self, name):
                self.w.write(60000, 16)
                self.w.write(65535, 16)
        writer = d2save.BitWriter()
        d2save._item_layout(UnknownStat(T, dict(item('rin'), flags=0x00880010, quality=2), writer=writer))
        empty = save([]); jm = empty.index(b'JM', 0x340)
        unknown = d2save.fix_header(empty[:jm] + b'JM\1\0' + writer.tobytes() + empty[jm+4:])
        self.run_plan(unknown, sidecar(unknown), ok=False)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
            p = Path(td)
            fixtures = {
                'a-invalid': (b'not a save', b'invalid sidecar'),
                'b-mismatch': (a, sidecar(save([item(page=1)]))),
                'c-unknownstat': (unknown, sidecar(unknown)),
                'z-valid': (a, sidecar(a)),
            }
            for name, pair in fixtures.items():
                for ext, data in zip(('.d2s', '.d2rl'), pair):
                    (p/(name+ext)).write_bytes(data)
            r = subprocess.run([str(EXE), '--folder', str(p)], capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            for name, pair in fixtures.items():
                if name == 'z-valid': continue
                self.assertEqual(tuple((p/(name+e)).read_bytes() for e in ('.d2s', '.d2rl')), pair)
            self.assertEqual((p/'z-valid.d2s').read_bytes(), save([]))
            self.assertEqual(d2save.check_sidecar((p/'z-valid.d2s').read_bytes(), (p/'z-valid.d2rl').read_bytes()), [])

    def test_generated_tables_current(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        import stash_retire_data
        self.assertEqual((ROOT/'plugin/src/stash_retire_data.h').read_text(),stash_retire_data.generate())
if __name__=='__main__':unittest.main()
