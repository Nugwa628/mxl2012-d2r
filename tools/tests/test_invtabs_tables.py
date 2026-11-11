"""Synthetic invtabs tables: no game data."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: F401
import invtabs_tables as it
import charm_inv


class InvTabsTablesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mod = Path(self.tmp.name)
        excel = self.mod / "data/global/excel"
        excel.mkdir(parents=True)
        self.codes = ["char", "scha", "mcha", "lcha", "csch", "summ", "grtz", *["ara"+c for c in "abcdefg"]]
        self.itemtypes = excel / "itemtypes.txt"
        self.itemtypes.write_text("ItemType\tCode\tEquiv1\tEquiv2\n" + "".join(f"Charm\t{c}\t{'char' if c != 'char' else ''}\t\n" for c in self.codes), encoding="ascii")

    def test_build_and_check_median_defaults(self):
        it.build(self.mod)
        folder = self.mod / it.TABLE_DIR
        self.assertEqual((folder / "types_charms.txt").read_bytes(), ("itemType\n"+"\n".join(self.codes)+"\n").encode())
        self.assertEqual((folder / "tabs.txt").read_bytes(), b"name\tlabel\tcolumns\trows\ttypes\ncharms\tCharms\t10\t6\ttypes_charms.txt\n")
        self.assertEqual(it.check(self.mod), {"charms": (0,0)})
        charm_inv.apply(self.mod)  # unchanged CharmInv output remains usable

    def test_equiv2_and_cycle(self):
        self.itemtypes.write_text("ItemType\tCode\tEquiv1\tEquiv2\nRoot\tchar\t\t\nChild\tdeep\tloop\tchar\nLoop\tloop\tdeep\t\nOther\tnope\tnope\t\n",encoding="ascii")
        it.build(self.mod)
        self.assertEqual((self.mod / it.TABLE_DIR / "types_charms.txt").read_text(), "itemType\nchar\ndeep\nloop\n")

    def test_reject_bad_built_trees(self):
        for body in ("itemType\nnope\n", "itemType\nchar\nchar\n", "itemType\n", "itemType\r\nchar\r\n"):
            with self.subTest(body=body):
                it.build(self.mod)
                (self.mod / it.TABLE_DIR / "types_charms.txt").write_bytes(body.encode())
                with self.assertRaises(ValueError):
                    it.check(self.mod)
        it.build(self.mod)
        path = self.mod / it.TABLE_DIR / "tabs.txt"
        row = "charms\tCharms\t10\t6\ttypes_charms.txt\n"
        path.write_text(it.HEADER+"\n"+row+row,encoding="ascii")
        with self.assertRaises(ValueError):
            it.check(self.mod)

    def test_pack_geometry_and_order(self):
        def t(n,w,h): return dict(name=n,columns=w,rows=h)
        self.assertEqual(it.pack([t("small",6,6),t("big",10,16)]), {"big":(0,0),"small":(10,0)})
        for tabs in ([t("a",9,9),t("b",8,8)], [t("a",17,1)], [t("a",0,1)], [t(str(i),1,1) for i in range(13)]):
            with self.assertRaises(ValueError): it.pack(tabs)

    def test_future_tab_and_safe_filename(self):
        cfg = self.mod / "tabs.toml"
        cfg.write_text('[tabs.charms]\ncolumns=10\nrows=6\nlabel="Charms"\ntypes="types_charms.txt"\n[tabs.other]\ncolumns=6\nrows=6\nlabel="Other"\ntypes="types_other.txt"\n')
        folder = self.mod / it.TABLE_DIR
        folder.mkdir(parents=True)
        (folder / "types_other.txt").write_bytes(b"itemType\nchar\n")
        it.build(self.mod,cfg)
        self.assertEqual(len(it.check(self.mod)),2)
        cfg.write_text(cfg.read_text().replace("types_charms.txt","../escape.txt"))
        with self.assertRaises(ValueError): it.build(self.mod,cfg)
