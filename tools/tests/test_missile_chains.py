"""Bug #395: missile creation chains (tools/missile_chains.py) and the skull swarm load rule (txt_migrate.missile_load)."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import missile_chains as mc  # noqa: E402

spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

COLS = ["Missile", "pCltDoFunc", "pCltHitFunc", "pSrvDoFunc", "pSrvHitFunc", "Param1", "CltParam1", "sHitPar2", "cHitPar2",
        "Range", "NextDelay", "SubMissile1", "HitSubMissile1", "CltSubMissile1", "CltHitSubMissile1", "ExplosionMissile"]


def row(name, **kw):
    r = dict.fromkeys(COLS, "")
    r.update({"Missile": name, "pCltDoFunc": "1", "pSrvDoFunc": "1"}, **kw)
    return [r[c] for c in COLS]


def skull(i, impacts_every="1"):
    nxt = f"skullswarm{i + 1}" if i < 5 else ""
    if i == 5:
        return row("skullswarm5", Range="10", SubMissile1="skullswarmimpact")
    return row(f"skullswarm{i}", pSrvDoFunc="15", pSrvHitFunc="20", pCltHitFunc="25", Param1=impacts_every, sHitPar2="1",
               cHitPar2="1", Range="10", SubMissile1="skullswarmimpact", HitSubMissile1=nxt, CltHitSubMissile1=nxt)


def swarm(impacts_every="1"):
    """Median 2012's skull swarm rows, the columns that make missiles (values of its missiles.txt / missiles.bin)."""
    return [row("skullswarmcenter", pSrvDoFunc="15", pCltDoFunc="19", Param1="1", CltParam1="1", Range="4",
                SubMissile1="skullswarm0", CltSubMissile1="skullswarm0")] + \
           [skull(i, impacts_every) for i in range(6)] + \
           [row("skullswarmimpact", Range="13", NextDelay="4", ExplosionMissile="teethexplodered"),
            row("teethexplodered", Range="13")]


class ChainTests(unittest.TestCase):
    def test_skull_swarm_counts(self):
        total, loops = mc.analyse(mc.edges(COLS, swarm(), "server"))
        self.assertEqual(loops, [])
        # impact + its explosion = 2; skull4 = 1 + 10 impacts * 2 + skull5; ... ; center = 1 + 4 * skull0
        self.assertEqual(total["skullswarmimpact"], 2)
        self.assertEqual(total["skullswarm5"], 1)  # do 1 makes no SubMissile
        self.assertEqual(total["skullswarm4"], 22)
        self.assertEqual(total["skullswarm0"], 106)
        self.assertEqual(total["skullswarmcenter"], 425)

    def test_load_rule_halves_the_swarm(self):
        total, _ = mc.analyse(mc.edges(COLS, swarm("2"), "server"))
        self.assertEqual(total["skullswarmcenter"], 225)

    def test_client_side_uses_client_columns(self):
        total, _ = mc.analyse(mc.edges(COLS, swarm(), "client"))
        # 4 client skull0, each a chain of 6 skulls (client hit 25, one target); no client impacts (client do 1)
        self.assertEqual(total["skullswarmcenter"], 1 + 4 * 6)

    def test_fury_counts_targets(self):
        rows = [row("a", pSrvHitFunc="20", sHitPar2="3", HitSubMissile1="b"), row("b"),
                row("c", pSrvHitFunc="20", sHitPar2="0", HitSubMissile1="b")]
        total, _ = mc.analyse(mc.edges(COLS, rows, "server"))
        self.assertEqual(total["a"], 4)
        self.assertEqual(total["c"], 2)  # 0 = the skill's number: counted as 1

    def test_self_feeding_loop_is_an_error(self):
        rows = [row("a", pSrvHitFunc="29", HitSubMissile1="b"), row("b", pSrvDoFunc="15", Param1="1", Range="5",
                                                                   SubMissile1="a")]
        total, loops = mc.analyse(mc.edges(COLS, rows, "server"))
        self.assertEqual(total["a"], -1)
        self.assertTrue(any(set(lp) == {"a", "b"} for lp in loops))
        errs = [p for p in mc.problems(COLS, rows) if p[0] == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("self-feeding", errs[0][3])

    def test_client_trail_and_allowed_rows_are_no_error(self):
        rows = [row("fingermagespider", pCltDoFunc="15", CltSubMissile1="fingermagespider"),
                row("barpaincloud", pSrvHitFunc="29", pCltHitFunc="30", HitSubMissile1="barpaincloud",
                    CltHitSubMissile1="barpaincloud")]
        self.assertEqual(mc.analyse(mc.edges(COLS, rows, "client"))[0]["fingermagespider"], 1)
        self.assertEqual(mc.problems(COLS, rows), [])

    def test_heavy_monster_attack_warns(self):
        mon = (["Id", "MissA1"], [["cultist2", "skullswarmcenter"], ["other", "skullswarmimpact"]])
        warn = [p for p in mc.problems(COLS, swarm(), mon) if p[0] == "warn"]
        self.assertEqual([(p[1], p[2], p[4]) for p in warn], [("MissA1", "cultist2", "skullswarmcenter 425")])
        self.assertEqual(mc.problems(COLS, swarm("2"), mon), [])


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class MissileLoadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        tm.OUT = Path(self.temp.name) / "out"
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def write(self, rows):
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "missiles.txt").write_text(tsv(COLS, *rows), encoding="utf-8")

    def read(self, bank):
        h, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "missiles.txt")
        return {r[0]: dict(zip(h, r)) for r in rows}

    def test_rule_applies_in_both_banks(self):
        self.write(swarm())
        self.mig.missile_load()
        for bank in ("base", ""):
            got = self.read(bank)
            self.assertEqual([got[f"skullswarm{i}"]["Param1"] for i in range(6)], ["2"] * 5 + [""])
            self.assertEqual(got["skullswarmimpact"]["NextDelay"], "2")
            self.assertEqual(got["skullswarmcenter"]["Param1"], "1")
        self.assertIn("applied 6", self.mig.report[-1])
        h, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / "missiles.txt")
        self.assertEqual(mc.analyse(mc.edges(h, rows, "server"))[0]["skullswarmcenter"], 225)

    def test_changed_source_value_is_left_and_reported(self):
        rows = swarm()
        rows[-2][COLS.index("NextDelay")] = "5"
        self.write(rows)
        self.mig.missile_load()
        self.assertEqual(self.read("base")["skullswarmimpact"]["NextDelay"], "5")
        self.assertIn("NOT applied", self.mig.report[-1])


if __name__ == "__main__":
    unittest.main()
