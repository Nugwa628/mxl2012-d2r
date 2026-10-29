"""Tests of tools/warlock_scale.py (lane warlock): synthetic tables, no game files.

  py -3 -I -m unittest discover -s tools/tests -p "test_warlock_scale.py" -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import warlock_scale as ws  # noqa: E402

SK_HEAD = ["skill", "*Id", "charclass", "reqlevel", "maxlvl", "summon", "petmax", "srvmissile", "srvmissilea",
           "passivestat1", "passivecalc1", "passivestat2", "passivecalc2", "aurastat1", "aurastatcalc1", "calc1",
           "localdelay", "mana", "lvlmana", "manashift", "minmana", "HitShift", "EType", "EMin", "EMinLev1", "EMinLev2",
           "EMinLev3", "EMinLev4", "EMinLev5", "EMax", "EMaxLev1", "EMaxLev2", "EMaxLev3", "EMaxLev4", "EMaxLev5", "ELen",
           "ELevLen1", "ELevLen2", "ELevLen3", "EDmgSymPerCalc", "MinDam", "MinLevDam1", "MinLevDam2", "MinLevDam3",
           "MinLevDam4", "MinLevDam5", "MaxDam", "MaxLevDam1", "MaxLevDam2", "MaxLevDam3", "MaxLevDam4", "MaxLevDam5",
           "DmgSymPerCalc", "SrcDam", *[f"Param{i}" for i in range(1, 13)]]
MS_HEAD = ["Missile", "Skill", "SubMissile1", "HitSubMissile1", "ExplosionMissile", "HitShift", "EType", "EMin", "MinELev1",
           "MinELev2", "MinELev3", "MinELev4", "MinELev5", "EMax", "MaxELev1", "MaxELev2", "MaxELev3", "MaxELev4",
           "MaxELev5", "EDmgSymPerCalc", "ELen", "Range"]
MON_HEAD = ["Id", "enabled", "killable", "npc", "boss", "inTown", "Level", "Level(N)", "Level(H)", "minHP", "maxHP",
            "MinHP(N)", "MaxHP(N)", "MinHP(H)", "MaxHP(H)", "A1MinD", "A1MaxD", "A1MinD(N)", "A1MaxD(N)", "A1MinD(H)",
            "A1MaxD(H)"]
LVL_HEAD = ["Level", "L-HP", "L-HP(N)", "L-HP(H)", "L-DM", "L-DM(N)", "L-DM(H)"]
WP_HEAD = ["name", "code", "levelreq", "mindam", "maxdam", "2handmindam", "2handmaxdam"]


def put(path: Path, head, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\r\n".join("\t".join(r) for r in [head, *rows]) + "\r\n").encode("utf-8"))


def sk(**k):
    r = {c: "" for c in SK_HEAD}
    r.update({c: str(v) for c, v in k.items()})
    return [r[c] for c in SK_HEAD]


def ms(**k):
    r = {c: "" for c in MS_HEAD}
    r.update({c: str(v) for c, v in k.items()})
    return [r[c] for c in MS_HEAD]


def mon(**k):
    r = {c: "" for c in MON_HEAD}
    r.update({c: str(v) for c, v in k.items()})
    return [r[c] for c in MON_HEAD]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.excel = Path(self.tmp.name) / "excel"
        put(self.excel / "skills.txt", SK_HEAD, [
            sk(skill="Bolt", **{"*Id": 1}, charclass="war", reqlevel=1, maxlvl=20, HitShift=8, EType="mag", EMin=10,
               EMinLev1=1, EMinLev2=2, EMinLev3=3, EMinLev4=4, EMinLev5=5, EMax=20, EMaxLev1=2, EMaxLev2=4, EMaxLev3=6,
               EMaxLev4=8, EMaxLev5=10, EDmgSymPerCalc="skill('Other'.blvl)*par8+skill('Foreign'.blvl)*par8", Param8=10,
               mana=8, lvlmana=2, manashift=8, minmana=1),
            sk(skill="Other", **{"*Id": 2}, charclass="war", reqlevel=1, maxlvl=20),
            sk(skill="Foreign", **{"*Id": 3}, charclass="ama", reqlevel=1, maxlvl=20),
            sk(skill="Venom", **{"*Id": 4}, charclass="ama", reqlevel=1, maxlvl=20, HitShift=8, EType="pois", EMin=256,
               EMax=512, ELen=50),
            sk(skill="Shooter", **{"*Id": 5}, charclass="ama", reqlevel=1, maxlvl=20, srvmissilea="arrow"),
            sk(skill="Pet", **{"*Id": 6}, charclass="war", reqlevel=1, maxlvl=20, summon="imp", petmax="2",
               calc1="par1*(lvl-1)", Param1=100, passivestat1="maxhp", passivecalc1="ln34*256", Param3=10, Param4=10,
               passivestat2="damagepercent", passivecalc2="ln56", Param5=50, Param6=0),
            sk(skill="Mark", **{"*Id": 7}, charclass="war", reqlevel=6, maxlvl=20, aurastat1="normal_damage_reduction",
               aurastatcalc1="ln12", Param1=-5, Param2=-2, Param9=4),
        ])
        put(self.excel / "missiles.txt", MS_HEAD, [
            ms(Missile="arrow", ExplosionMissile="boom"),
            ms(Missile="boom", HitShift=8, EType="fire", EMin=30, EMax=50),
        ])
        put(self.excel / "monstats.txt", MON_HEAD, [
            mon(Id="imp", enabled=0, killable=1, minHP=10, maxHP=10, A1MinD=2, A1MaxD=4),
            mon(Id="zombie", enabled=1, killable=1, Level=5, **{"Level(N)": 30, "Level(H)": 60}, minHP=20, maxHP=40,
                **{"MinHP(N)": 30, "MaxHP(N)": 50, "MinHP(H)": 40, "MaxHP(H)": 60}),
        ])
        put(self.excel / "monlvl.txt", LVL_HEAD, [[str(i), str(100 * i), str(200 * i), str(300 * i), "100", "100", "100"]
                                                  for i in range(0, 121)])
        put(self.excel / "weapons.txt", WP_HEAD, [["Axe", "axe", "1", "4", "8", "", ""], ["Bow", "bow", "10", "8", "12", "", ""],
                                                     ["Sword", "swd", "20", "15", "25", "", ""], ["Maul", "mau", "30", "", "", "20", "40"]])
        self.data = ws.Data(self.excel)


class FormulaTests(Base):
    def ev(self, text, lvl=3, name="Mark"):
        ctx = ws.Ctx(self.data, "war", lvl, 6)
        return ctx.ev(self.data.skill(name), self.data.skills, text, lvl, ws.hard(lvl))

    def test_codes_and_operators(self):
        self.assertEqual(self.ev("ln12"), -5 + 2 * -2)
        self.assertEqual(self.ev("par9"), 4)
        self.assertEqual(self.ev("dm12", lvl=4), (110 * 4 * (-2 - -5)) // (100 * 10) + -5)
        self.assertEqual(self.ev("(lvl>=10)?3:((lvl>=5)?2:1)", lvl=7), 2)
        self.assertEqual(self.ev("min(lvl,2)+max(lvl,9)"), 11)
        self.assertEqual(self.ev("-min(ln12,40)"), 9)
        self.assertEqual(self.ev("(0-7)/2"), -3)   # D2's integer division truncates toward zero
        self.assertEqual(self.ev("7/2"), 3)
        self.assertEqual(self.ev("ulvl", lvl=3), ws.ulvl(3, 6))

    def test_skill_refs_count_same_class_only(self):
        self.assertEqual(self.ev("skill('Other'.blvl)", lvl=9), ws.hard(9))
        self.assertEqual(self.ev("skill('Foreign'.blvl)", lvl=9), 0)
        self.assertEqual(self.ev("skill('Missing'.blvl)", lvl=9), 0)
        self.assertEqual(self.ev("stat('energy'.accr)", lvl=1), ws.ref_stat("energy", "accr", ws.ulvl(1, 6)))

    def test_brackets(self):
        self.assertEqual(ws.bracket(10, [1, 2, 3, 4, 5], 8), 17)
        self.assertEqual(ws.bracket(10, [1, 2, 3, 4, 5], 29), 10 + 7 + 16 + 18 + 24 + 5)
        self.assertEqual(ws.level_counts(29), [1, 7, 8, 6, 6, 1])
        self.assertEqual(sum(ws.level_counts(40)), 40)


class DamageTests(Base):
    def test_elemental_with_synergy(self):
        d = ws.damage(self.data, "Bolt", 1, 1)
        self.assertAlmostEqual(d.elem, 15 * (100 + 10) / 100)   # Other at blvl 1 gives 10 %, Foreign (another class) 0
        d9 = ws.damage(self.data, "Bolt", 9, 1)
        self.assertAlmostEqual(d9.elem, (10 + 7 + 2 + 20 + 14 + 4) / 2 * (100 + 10 * ws.hard(9)) / 100)

    def test_poison_counts_its_length(self):
        self.assertAlmostEqual(ws.damage(self.data, "Venom", 1, 1).elem, (256 + 512) / 2 * 50)

    def test_damage_from_explosion_missile(self):
        table, src, missile = ws.damage_source(self.data, self.data.skill("Shooter"))
        self.assertTrue(missile)
        self.assertEqual(src[0], "boom")
        self.assertAlmostEqual(ws.damage(self.data, "Shooter", 1, 1).elem, 40)

    def test_mana(self):
        self.assertEqual(ws.mana_cost(self.data, "Bolt", 1), 8)
        self.assertEqual(ws.mana_cost(self.data, "Bolt", 11), 28)

    def test_summon(self):
        m = ws.summon_stats(self.data, "Pet", 3, 1)
        u = ws.ulvl(3, 1)
        # Median's tooltip formula: (base x L-HP + the maxhp passive) x (100 + clc1) %
        life = (10 * (100 * u) / 100 + (10 + 2 * 10)) * (1 + 200 / 100)
        self.assertAlmostEqual(m.life, life)
        self.assertAlmostEqual(m.damage, 3 * 1.0 * 1.5)
        self.assertEqual(m.count, 2)
        self.assertAlmostEqual(m.army, m.damage * 2)

    def test_weapon_reference(self):
        self.assertEqual(self.data.weapon_avg(10), 6)    # 75th percentile of the bases a level 10 character can use
        self.assertEqual(self.data.weapon_avg(40), 20)


class FitTests(Base):
    def test_fit_block_hits_target(self):
        ed = ws.Edit(self.data)
        before = [ws.damage(self.data, "Bolt", s, 1).elem for s in ws.SLVLS]
        ws.fit_block(self.data, ed, "Bolt", "Bolt", "elem", [2 * b for b in before], 1, "war")
        after = [ws.damage(self.data, "Bolt", s, 1).elem for s in ws.SLVLS]
        for b, a in zip(before, after):
            self.assertAlmostEqual(a / b, 2.0, delta=0.15)
        self.assertEqual(ed.cells[("skills", "Bolt", "EMin")][1:], ["10", "20"])

    def test_fit_cells_scales_params(self):
        ed = ws.Edit(self.data)
        target = [3 * ws.stat_value(self.data, "Mark", "normal_damage_reduction", s, 6) for s in ws.SLVLS]
        ws.fit_cells(self.data, ed, "Mark", [ws.param_group(None, "Param1", "Mark", self.data),
                                             ws.param_group(None, "Param2", "Mark", self.data)],
                     lambda s: ws.stat_value(self.data, "Mark", "normal_damage_reduction", s, 6), target)
        self.assertEqual(ed.cells[("skills", "Mark", "Param1")][2], "-15")
        self.assertEqual(ed.cells[("skills", "Mark", "Param2")][2], "-6")

    def test_param_knob_must_be_read_by_a_calc(self):
        with self.assertRaises(SystemExit):
            ws.param_group(None, "Param9", "Mark", self.data)   # Param9 is only read by code: a mechanic

    def test_fit_mana_linear(self):
        ed = ws.Edit(self.data)
        spec = ws.Spec("Bolt", "damage", "mag", ["Venom"], "")
        put_mana = self.data.skills.by["Venom"]
        put_mana[self.data.skills.ix["mana"]] = "20"
        put_mana[self.data.skills.ix["lvlmana"]] = "4"
        ws.fit_mana(self.data, ed, spec, ["Venom"])
        self.assertEqual([ws.mana_cost(self.data, "Bolt", s) for s in (1, 40)], [20, 20 + 4 * 39])

    def test_specs_cover_the_30_warlock_skills(self):
        names = [s.name for s in ws.SPECS]
        self.assertEqual(len(names), 30)
        self.assertEqual(len(set(names)), 30)
        for s in ws.SPECS:
            self.assertIn(s.role, ("damage", "weapon", "summon", "buff", "curse", "passive", "utility"))
            if s.role in ("damage", "weapon", "summon"):
                self.assertGreaterEqual(len(s.comparables), 2, s.name)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mod = Path(self.tmp.name)
        head = ["skill", "*Id", "EMin", "mana"]
        put(self.mod / ws.EXCEL / "skills.txt", head, [["Abyss", "402", "20", "23"]])
        put(self.mod / ws.EXCEL / "base" / "skills.txt", head, [["Abyss", "", "", ""]])   # Classic bank: placeholder row
        self.edits = [{"skill": "Abyss", "table": "skills", "row": "Abyss", "column": "EMin", "d2r": "20", "new": "35"},
                      {"skill": "Abyss", "table": "skills", "row": "Abyss", "column": "mana", "d2r": "23", "new": "30"}]

    def read(self, bank=""):
        return (self.mod / ws.EXCEL / bank / "skills.txt").read_text(encoding="utf-8").splitlines()[1].split("\t")

    def test_rotw_written_base_untouched(self):
        log = ws.apply(self.mod, self.edits)
        self.assertEqual(self.read()[2:], ["35", "30"])
        self.assertEqual(self.read("base")[2:], ["", ""])   # the Classic bank's placeholder rows are never written
        self.assertEqual(log, ["rotw skills: 2 cells"])
        ws.apply(self.mod, self.edits)   # idempotent
        self.assertEqual(self.read()[2:], ["35", "30"])

    def test_changed_d2r_value_stops(self):
        self.edits[0]["d2r"] = "21"
        with self.assertRaises(SystemExit):
            ws.apply(self.mod, self.edits)


if __name__ == "__main__":
    unittest.main()
