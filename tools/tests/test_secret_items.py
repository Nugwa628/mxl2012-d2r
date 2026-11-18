import pathlib as _pl, sys as _sys; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1])); import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import build  # noqa: E402
import secret_items as si  # noqa: E402
from d2r_adds import Table  # noqa: E402

# The owner's list (2026-11-16): the wiki's "Secrets" uniques that have stats, without Aerial's Skull and the Token ring.
EXPECTED = {  # index: (name, rarity, base code, peer factor)
    "Lady of Storms2": ("Lady of Storms", 1, "jew", 10),
    "Atomus": ("Atomus", 2, "jew", 10),
    "Bardslore": ("Bard's Joke", 3, "jew", 10),
    "NewGrandArmor": ("Grand Armor", 1, "@15", 4),
    "NewSiggardsRevenge": ("Siggard's Revenge", 1, "7@N", 4),
    "NewAeterna": ("Aeterna", 1, "05@", 4),
    "NewWhiteVoid": ("Sword of the White Void", 1, "13@", 4),
    "NewFuryHell": ("Fury of Hellfire", 1, "7@F", 4),
    "NewSoulReaver": ("Soul Reaver", 1, "!14", 4),
}
EXCLUDED = ("RetardModeCharm", "TokenRing")  # Aerial's Skull, the Token beta ring (owner)
HEAD = ["index", "*ID", "version", "disabled", "spawnable", "rarity", "nolimit", "lvl", "lvl req", "code"]


def row(index, spawnable, rarity, lvl, req, code):
    return ["mxl2012:" + index, "", "", "", spawnable, str(rarity), "1", str(lvl), str(req), code]


def fixture():
    rows = [row("Heavenstone", "1", 250, 120, 100, "jew"), row("Cornerstone", "1", 1, 120, 100, "jew"),
            row("SkillsdLastSkillEver", "", 1, 120, 100, "jew"), row("Torn Flesh of Gods", "1", 2, 120, 100, "@15"),
            row("KhazraPlate", "1", 1, 120, 100, "@15"), row("RetardModeCharm", "", 1, 1, 0, "yq9"),
            row("TokenRing", "", 1, 120, 121, "rin"), row("Sigil", "1", 50, 120, 120, "rin")]
    for k, (_, _, code, _) in EXPECTED.items():
        rows.append(row(k, "0" if k == "NewSoulReaver" else "", 50 if k == "Bardslore" else 1, 40 if k == "Bardslore" else 120,
                        555 if k == "Lady of Storms2" else 100, code))
    return "\r\n".join("\t".join(r) for r in [HEAD, *rows]) + "\r\n"


class SecretItemsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mod = Path(self.temp.name) / "mod"
        for bank in ("", "base/"):
            p = self.mod / "data/global/excel" / bank / "uniqueitems.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(fixture().encode("utf-8"))

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(si.main(["apply", "--mod", str(self.mod)]), 0)

    def table(self, bank=""):
        t = Table(self.mod / "data/global/excel" / bank / "uniqueitems.txt")
        return t, {r[0].split(":", 1)[1]: r for r in t.rows}

    def test_data_lists_the_nine_with_rarity(self):
        secrets = {s["index"]: s for s in si.load_secrets()}
        self.assertEqual(set(secrets), set(EXPECTED))
        for k, (name, rarity, _, factor) in EXPECTED.items():
            self.assertEqual((secrets[k]["name"], secrets[k]["rarity"], secrets[k]["peer factor"]), (name, rarity, factor), k)
        self.assertEqual(secrets["Lady of Storms2"]["lvl req"], "40")
        self.assertTrue(all(not s["lvl req"] for k, s in secrets.items() if k != "Lady of Storms2"))
        self.assertFalse(set(EXCLUDED) & set(secrets))
        # Lady of Storms is the rarest jewel; every secret has the lowest weight of its kind
        jewels = sorted((s["rarity"], k) for k, s in secrets.items() if EXPECTED[k][2] == "jew")
        self.assertEqual(jewels[0][1], "Lady of Storms2")
        self.assertEqual(len({r for r, _ in jewels}), 3)

    def test_apply_makes_each_secret_spawnable(self):
        self.apply()
        for bank in ("", "base/"):
            t, rows = self.table(bank)
            cs, cr, cq = t.col("spawnable"), t.col("rarity"), t.col("lvl req")
            for k, (_, rarity, _, _) in EXPECTED.items():
                self.assertEqual((rows[k][cs], rows[k][cr]), ("1", str(rarity)), (bank, k))
            self.assertEqual(rows["Lady of Storms2"][cq], "40")
            self.assertEqual(rows["Atomus"][cq], "100")  # Median's level kept
            for k in EXCLUDED:
                self.assertEqual(rows[k][cs], "", k)
            # the other uniques of the bases: x10 jewels, x4 sacred; other bases and unspawnable rows untouched
            self.assertEqual([rows[k][cr] for k in ("Heavenstone", "Cornerstone", "Torn Flesh of Gods", "KhazraPlate")],
                             ["2500", "10", "8", "4"])
            self.assertEqual([rows[k][cr] for k in ("SkillsdLastSkillEver", "Sigil", "TokenRing")], ["1", "50", "1"])
            # every secret is rarer than any other spawnable unique on its base
            for k, (_, rarity, code, _) in EXPECTED.items():
                others = [int(r[cr]) for n, r in rows.items() if r[t.col("code")] == code and r[cs] == "1" and n not in EXPECTED]
                if others:
                    self.assertLess(rarity, min(others), k)

    def test_idempotent(self):
        self.apply()
        before = (self.mod / "data/global/excel/uniqueitems.txt").read_bytes()
        self.apply()
        self.assertEqual((self.mod / "data/global/excel/uniqueitems.txt").read_bytes(), before)
        self.assertIn(b"\r\n", before)

    def test_build_runs_it_after_txt_migrate_before_chronicle(self):
        names = [s[0] for s in build.DATA_STEPS]
        self.assertEqual(names.index("secret_items.py"), names.index("txt_migrate.py") + 1)
        self.assertLess(names.index("secret_items.py"), names.index("chronicle.py"))

    def test_built_mod(self):
        p = ROOT / "work" / "mod" / "data" / "global" / "excel" / "uniqueitems.txt"
        if not p.exists():
            self.skipTest("no built mod")
        t = Table(p)
        rows = {si.key(r[0]): r for r in t.rows}
        for k, (_, rarity, code, _) in EXPECTED.items():
            r = rows[k]
            self.assertEqual((r[t.col("spawnable")], r[t.col("rarity")], r[t.col("code")]), ("1", str(rarity), code), k)
        self.assertEqual(rows["Lady of Storms2"][t.col("lvl req")], "40")


if __name__ == "__main__":
    unittest.main()
