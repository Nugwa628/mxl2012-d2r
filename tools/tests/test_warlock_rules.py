"""Tests of tools/warlock_scale.py round 2 (lane warlock2): Median's rules on the Warlock (rule_cells), the flat / weapon
damage model, the missile copy fit, the shared fit and the RotW-only apply. Synthetic tables, no game files.

  py -3 -I -m unittest discover -s tools/tests -p "test_warlock_rules.py" -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import warlock_scale as ws  # noqa: E402

SPELL_SYN = ("(((100+(20*ulvl))*(100+((((260*(stat('energy'.accr)+10)))/(stat('energy'.accr)+250))+"
             "(skill('DSK 2'.pst2)))))/100)-100")
ENERGY_CALC = "(((260*(stat('energy'.accr)+10)))/(stat('energy'.accr)+250))"

SK_HEAD = ["skill", "*Id", "charclass", "skilldesc", "reqlevel", "maxlvl", "skpoints", "summon", "petmax", "srvmissile",
           "srvmissilea", "calc1", "calc2", "calc5", "calc6", "mana", "lvlmana", "manashift", "minmana", "HitShift", "EType",
           "EMin", "EMinLev1", "EMinLev2", "EMinLev3", "EMinLev4", "EMinLev5", "EMax", "EMaxLev1", "EMaxLev2", "EMaxLev3",
           "EMaxLev4", "EMaxLev5", "ELen", "ELevLen1", "ELevLen2", "ELevLen3", "EDmgSymPerCalc", "MinDam", "MinLevDam1",
           "MinLevDam2", "MinLevDam3", "MinLevDam4", "MinLevDam5", "MaxDam", "MaxLevDam1", "MaxLevDam2", "MaxLevDam3",
           "MaxLevDam4", "MaxLevDam5", "DmgSymPerCalc", "SrcDam", "localdelay",
           *[f"passivestat{i}" for i in range(1, 15)], *[f"passivecalc{i}" for i in range(1, 15)],
           *[f"aurastat{i}" for i in range(1, 7)], *[f"aurastatcalc{i}" for i in range(1, 7)],
           *[f"Param{i}" for i in range(1, 21)]]
SD_HEAD = ["skilldesc", *[f"{p}{f}{i}" for i in range(1, 7) for p, f in
                          [("desc", "line"), ("desc", "texta"), ("desc", "textb"), ("desc", "calca"), ("desc", "calcb")]],
           *[f"dsc2{f}{i}" for i in range(1, 6) for f in ("line", "texta", "textb", "calca", "calcb")],
           *[f"dsc3{f}{i}" for i in range(1, 8) for f in ("line", "texta", "textb", "calca", "calcb")]]
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


def row(head, **k):
    r = {c: "" for c in head}
    for c, v in k.items():
        assert c in r, c
        r[c] = str(v)
    return [r[c] for c in head]


def block(**k):
    """An elemental block, min = max at each position."""
    v = k.pop("v")
    out = {"EMin": v[0], "EMax": v[0]}
    for i in range(1, 6):
        out[f"EMinLev{i}"] = out[f"EMaxLev{i}"] = v[i]
    out.update(k)
    return out


def sd(key, desc=(), dsc2=(), dsc3=()):
    k = {"skilldesc": key}
    for prefix, lines in (("desc", desc), ("dsc2", dsc2), ("dsc3", dsc3)):
        for i, vals in lines:
            for f, v in zip(("line", "texta", "textb", "calca", "calcb"), vals):
                k[f"{prefix}{f}{i}"] = v
    return row(SD_HEAD, **k)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.excel = Path(self.tmp.name) / "excel"
        S = SK_HEAD
        put(self.excel / "skills.txt", S, [
            # Median's source row of the spell synergy and its tooltip lines
            row(S, skill="Rain of Fire", **{"*Id": 1}, charclass="sor", skilldesc="rainoffire", reqlevel=18, maxlvl=99,
                HitShift=4, EType="fire", EDmgSymPerCalc=SPELL_SYN, **block(v=(90, 18, 9, 9, 9, 9))),
            # a Warlock spell with two D2R damage synergies and one other synergy line
            row(S, skill="Miasma Bolt", **{"*Id": 395}, charclass="war", skilldesc="miasma bolt", reqlevel=1, maxlvl=20,
                HitShift=7, EType="mag", EDmgSymPerCalc="(skill('Abyss'.blvl))*par8", Param8=10,
                **block(v=(6, 15, 22, 24, 20, 24))),
            row(S, skill="Cleave", **{"*Id": 391}, charclass="war", skilldesc="cleave", reqlevel=6, maxlvl=20, SrcDam=128,
                calc1="ln12", calc2="0", Param1=1, Param2=17, Param13=3, Param14=3),
            row(S, skill="Mirrored Blades", **{"*Id": 392}, charclass="war", skilldesc="mirrored blades", reqlevel=30,
                maxlvl=20, SrcDam=128, calc5="min((2+(lvl/5)),5)", calc6="dm12", Param1=100, Param2=270),
            row(S, skill="Summon Defiler", **{"*Id": 377}, charclass="war", skilldesc="summon defiler", reqlevel=18,
                maxlvl=20, summon="defiler", petmax="1", calc1="(par1*(lvl-1))", Param1=0, passivestat1="velocitypercent",
                passivecalc1="10", passivestat2="damagepercent", passivecalc2="par2*(lvl-1)", Param2=4),
        ])
        put(self.excel / "skilldesc.txt", SD_HEAD, [
            sd("rainoffire", dsc2=[(4, ("73", "mxl2012:DescMaxLevel2", "ModStre9c", "blvl", "x"))],
               dsc3=[(1, ("40", "Sksyn", "mxl2012:SkillnameRain", "4", "")),
                     (2, ("65", "mxl2012:strchrenghard", "mxl2012:DescFireSyn", "", "")),
                     (3, ("67", "mxl2012:DescCurrentSyn", "mxl2012:DescPctNoS", ENERGY_CALC, ""))]),
            sd("miasma bolt", desc=[(1, ("36", "StrSkill3", "", "usmc", "256"))], dsc2=[(1, ("36", "a", "b", "1", "25"))],
               dsc3=[(1, ("40", "Sksyn", "MiasmaBoltName", "2", "")), (2, ("76", "Magdplev", "AbyssName", "par8", "")),
                     (3, ("76", "AMDImm", "AbyssName", "par9", "")), (4, ("76", "Magdplev", "ChainName", "par8", ""))]),
            sd("cleave", desc=[(1, ("36", "StrSkill3", "", "usmc", "256")), (3, ("74", "StrSkillDamagePercent", "", "clc1", ""))]),
            sd("mirrored blades", desc=[(1, ("36", "StrSkill3", "", "usmc", "256"))]),
            sd("summon defiler", desc=[(1, ("36", "StrSkill3", "", "usmc", "256")), (2, ("13", "StrSkill42", "", "clc1", ""))]),
        ])
        put(self.excel / "missiles.txt", MS_HEAD, [
            row(MS_HEAD, Missile="center", HitShift=8, EType="mag", EMin=10, EMax=10, MinELev1=5, MaxELev1=5,
                EDmgSymPerCalc="(skill('Cleave'.blvl))*10"),
        ])
        put(self.excel / "monstats.txt", MON_HEAD, [row(MON_HEAD, Id="defiler", minHP=1, maxHP=1, A1MinD=1, A1MaxD=6)])
        put(self.excel / "monlvl.txt", LVL_HEAD, [[str(L), str(100 * L), str(100 * L), str(100 * L), "100", "100", "100"]
                                                  for L in range(0, 121)])
        put(self.excel / "weapons.txt", WP_HEAD, [["Sword", "swd", "1", "10", "10", "", ""]])
        self.data = ws.Data(self.excel)


def evaluate(text, values):
    """Evaluate a calc with names / stat() from `values`."""
    def resolve(name):
        return values[name]

    def call(fn, ref, parts, args):
        if fn == "stat":
            return values.get(ref, 0)
        return {"min": min, "max": max}[fn](args)
    return ws.Parser(ws.tokenize(text), resolve, call).parse()


class GateTests(unittest.TestCase):
    def test_skpoints_is_medians_text(self):
        self.assertEqual(ws.skpoints_formula(0),
                         "((ulvl)<((blvl-1-stat('skill_more'.accr))*6))?(stat('newskills'.accr)+1):1")
        self.assertEqual(ws.skpoints_formula(24),
                         "((ulvl-24)<((blvl-1-stat('skill_more'.accr))*6))?(stat('newskills'.accr)+1):1")

    def test_one_hard_point_per_6_levels(self):
        f = ws.skpoints_formula(12)
        # clvl 24, tier 12: blvl 3 -> 4 costs 1 point; blvl 4 -> 5 costs more than the character has
        self.assertEqual(evaluate(f, {"ulvl": 24, "blvl": 3, "newskills": 7}), 1)
        self.assertEqual(evaluate(f, {"ulvl": 24, "blvl": 4, "newskills": 7}), 8)
        self.assertEqual(evaluate(f, {"ulvl": 24, "blvl": 4, "newskills": 7, "skill_more": 1}), 1)

    def test_max_level_line_is_medians(self):
        # Median's own rows: tier 0 / maxlvl 99 -> cap 22, tier 18 -> 19, tier 24 -> 18
        self.assertEqual(ws.max_level_calc(0, 99), "max((min((2+(ulvl/6)),22)),2)+stat('skill_more'.accr)")
        self.assertEqual(ws.max_level_calc(18, 99), "max((min((2+((ulvl-18)/6)),19)),2)+stat('skill_more'.accr)")
        self.assertIn(",18)),2)", ws.max_level_calc(24, 99))
        self.assertIn(",20)),2)", ws.max_level_calc(0, 20))     # the Warlock's maxlvl 20 caps it
        self.assertEqual(evaluate(ws.max_level_calc(30, 20), {"ulvl": 60, "skill_more": 0}), 7)


class DescTests(unittest.TestCase):
    LINES = [("40", "Sksyn", "X", "2", ""), ("76", "Magdplev", "A", "par8", ""), ("76", "AMDImm", "A", "par9", ""),
             ("76", "Damplev", "B", "par8", "")]

    def test_damage_synergies_leave_energy_lines_come(self):
        energy = [("65", "e", "f", "", ""), ("67", "c", "p", "calc", "")]
        self.assertEqual(ws.rebuilt_dsc3(self.LINES, energy), [self.LINES[0], *energy, self.LINES[2]])

    def test_no_header_when_nothing_left(self):
        self.assertEqual(ws.rebuilt_dsc3([self.LINES[0], self.LINES[1]], []), [])
        self.assertEqual(ws.rebuilt_dsc3([self.LINES[0], self.LINES[2]], []), [self.LINES[0], self.LINES[2]])


class RuleTests(Base):
    def cells(self):
        return {(t, r, c): v for _, t, r, c, v in ws.rule_cells(self.data)}

    def test_gate_and_max_line_on_every_row(self):
        c = self.cells()
        self.assertEqual(c[("skills", "Miasma Bolt", "skpoints")], ws.skpoints_formula(0))
        self.assertEqual(c[("skills", "Mirrored Blades", "skpoints")], ws.skpoints_formula(30))
        # the maximum level line goes in the highest free dsc2 slot, with Median's texts
        self.assertEqual(c[("skilldesc", "miasma bolt", "dsc2line5")], "73")
        self.assertEqual(c[("skilldesc", "miasma bolt", "dsc2texta5")], "mxl2012:DescMaxLevel2")
        self.assertEqual(c[("skilldesc", "cleave", "dsc2calcb5")], ws.max_level_calc(6, 20))

    def test_spell_takes_medians_synergy_hitshift_and_lines(self):
        c = self.cells()
        self.assertEqual(c[("skills", "Miasma Bolt", "EDmgSymPerCalc")], SPELL_SYN)
        self.assertEqual(c[("skills", "Miasma Bolt", "HitShift")], "4")
        got = [tuple(c[("skilldesc", "miasma bolt", f"{f}{i}")] for f in ws.DSC3) for i in range(1, 8)]
        self.assertEqual(got[0][:2], ("40", "Sksyn"))
        self.assertEqual(got[1][:3], ("65", "mxl2012:strchrenghard", "mxl2012:DescMagSyn"))   # magic, not Median's fire
        self.assertEqual(got[2][:4], ("67", "mxl2012:DescCurrentSyn", "mxl2012:DescPctNoS", ENERGY_CALC))
        self.assertEqual(got[3][1], "AMDImm")                    # the damage-over-time synergy stays
        self.assertEqual(got[4:], [("",) * 5] * 3)               # both Magdplev lines are gone

    def test_outlier_rules(self):
        c = self.cells()
        self.assertEqual(c[("skills", "Cleave", "calc2")], ws.CLEAVE_FLAT)
        self.assertEqual(c[("skilldesc", "cleave", "desctexta2")], "StrSkillDamageFlat")   # first free descline
        self.assertEqual(c[("skills", "Mirrored Blades", "EType")], "mag")
        self.assertEqual(c[("skills", "Mirrored Blades", "EDmgSymPerCalc")], "10*ulvl")
        # the Defiler: maxhp in the first free passive slot, the flat damage in the next, Median's Life / Damage lines
        self.assertEqual(c[("skills", "Summon Defiler", "passivestat3")], "maxhp")
        self.assertEqual(c[("skills", "Summon Defiler", "passivecalc3")], ws.DEMON_LIFE)
        self.assertEqual(c[("skills", "Summon Defiler", "passivestat4")], "item_normaldamage")
        self.assertEqual(c[("skills", "Summon Defiler", "passivecalc4")], "min(edmx,4000)")
        self.assertEqual(c[("skilldesc", "summon defiler", "desccalca2")], "((1+(pst3/256))*(100+clc1))/100")
        self.assertEqual(c[("skilldesc", "summon defiler", "desccalca3")], "((1+pst4)*(100+pst2))/100")

    def test_apply_rules_records_values_before(self):
        ed = ws.Edit(self.data)
        n = ws.apply_rules(self.data, ed)
        self.assertGreater(n, 20)
        self.assertEqual(ed.cells[("skills", "Cleave", "calc2")][1:], ["0", ws.CLEAVE_FLAT])
        self.assertEqual(self.data.skills.get(self.data.skill("Miasma Bolt"), "HitShift"), "4")


class ModelTests(Base):
    def test_cleave_flat_rides_on_the_damage_percent(self):
        ws.apply_rules(self.data, ws.Edit(self.data))
        s, tier = 5, 6
        u = ws.ulvl(s, tier)
        d = ws.damage(self.data, "Cleave", s, tier, weapon_pct="clc1", flat_calc="clc2")
        f = 1 + (1 + 4 * 17) / 100
        self.assertAlmostEqual(d.flat, ((3 + 4 * 3) * (100 + 10 * u) // 100) * f)
        self.assertAlmostEqual(d.weapon, 10 * f)
        self.assertAlmostEqual(d.total, d.flat + d.weapon)

    def test_weapon_percent_multiplies_the_elemental_block(self):
        ed = ws.Edit(self.data)
        ws.apply_rules(self.data, ed)
        for c in ("EMin", "EMax"):
            ed.set("Mirrored Blades", "skills", "Mirrored Blades", c, 4)
        spec = ws.Spec("Mirrored Blades", "weapon", "phys", [], "", weapon_pct="(clc5*clc6)-100")
        d = ws.damage(self.data, "Mirrored Blades", 1, 24, weapon_pct=spec.weapon_pct)
        hf = ws.hit_factor(self.data, spec, 1, 24)
        self.assertAlmostEqual(d.elem, 4 * (100 + 10 * ws.ulvl(1, 24)) / 100 * hf)
        self.assertAlmostEqual(d.weapon, 10 * hf)

    def test_demon_life_follows_the_passive(self):
        ws.apply_rules(self.data, ws.Edit(self.data))
        sk = self.data.skills.by["Summon Defiler"]
        sk[self.data.skills.ix["Param15"]], sk[self.data.skills.ix["Param16"]] = "100", "10"
        m = ws.summon_stats(self.data, "Summon Defiler", 3, 18)
        u = ws.ulvl(3, 18)
        self.assertAlmostEqual(m.life, 1 * u + ((100 + 2 * 10) * 256 * (100 + u // 2) // 100) / 256)   # integer calc

    def test_missile_copy_fitted_with_its_own_synergy(self):
        ed = ws.Edit(self.data)
        want = [3 * ws.missile_elem(self.data, "center", s, 1, "war") for s in ws.SLVLS]
        ws.fit_block(self.data, ed, "Abyss", "center", "elem", want, 1, "war", tname="missiles")
        got = [ws.missile_elem(self.data, "center", s, 1, "war") for s in ws.SLVLS]
        for w, g in zip(want, got):
            self.assertAlmostEqual(g / w, 1.0, delta=0.12)
        self.assertEqual(ed.cells[("missiles", "center", "EMin")][0], "Abyss")

    def test_shared_cells_fit_several_curves(self):
        ed = ws.Edit(self.data)
        ws.apply_rules(self.data, ed)
        cl = self.data.skill("Cleave")

        def flat(s):
            return ws.Ctx(self.data, "war", s, 6).ev(cl, self.data.skills, "clc2", s, ws.hard(s))
        base = [flat(s) for s in ws.SLVLS]
        ws.fit_cells(self.data, ed, "Cleave", [[("skills", "Cleave", "Param13")], [("skills", "Cleave", "Param14")]],
                     flat, [2 * b for b in base], more=[(flat, [2 * b for b in base])])
        self.assertEqual(ed.cells[("skills", "Cleave", "Param13")][2], "6")
        self.assertEqual(ed.cells[("skills", "Cleave", "Param14")][2], "6")


class ApplyBothTests(unittest.TestCase):
    def test_rules_then_numbers_rotw_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = Path(tmp)
            head = ["skill", "calc2", "Param13"]
            put(mod / ws.EXCEL / "skills.txt", head, [["Cleave", "0", ""]])
            put(mod / ws.EXCEL / "base" / "skills.txt", head, [["Cleave", "0", ""]])
            rules = [{"skill": "Cleave", "table": "skills", "row": "Cleave", "column": "calc2", "d2r": "0", "new": "pa13"}]
            nums = [{"skill": "Cleave", "table": "skills", "row": "Cleave", "column": "Param13", "d2r": "", "new": "7"}]
            self.assertEqual(ws.apply(mod, rules, "rule ") + ws.apply(mod, nums),
                             ["rotw skills: 1 rule cells", "rotw skills: 1 cells"])
            lines = (mod / ws.EXCEL / "skills.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[1].split("\t"), ["Cleave", "pa13", "7"])
            base = (mod / ws.EXCEL / "base" / "skills.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(base[1].split("\t"), ["Cleave", "0", ""])


if __name__ == "__main__":
    unittest.main()
