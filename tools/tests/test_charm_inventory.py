"""The charm inventory switch (tools/charm_inventory.py) in the build, the classic button and the data check.
Pure: no extraction, no game files. Run: py -3 -I -m unittest discover -s tools/tests -p "test_charm_inventory.py" """
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

import build  # noqa: E402
import charm_inventory as ci  # noqa: E402
import invtabs_legacy as il  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]
INVTABS_SCRIPTS = ["invtabs_tables.py", "invtabs_hdart.py", "invtabs_art.py", "invtabs_legacy.py"]
LAYOUT = ('{\n    "type": "Panel", "name": "PlayerInventoryExpansionLayout",\n    "children": [\n'
          '        {"type": "ButtonWidget", "name": "close", "fields": {"rect": {"x": 1, "y": 2}}},\n'
          '        {"type": "ButtonWidget", "name": "MxlSendStash", "fields": {"rect": {"x": 3, "y": 4}}},\n'
          '        {"type": "InventoryGridWidget", "name": "grid"}\n    ]\n}\n')


def scripts(steps: list) -> list:
    return [s[0] for s in steps]


def write(data: Path, rels, body: str = "x") -> None:
    for rel in rels:
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_text(body, "utf-8")


class Switch(unittest.TestCase):
    def test_default_and_names(self):
        self.assertEqual(ci.CHARM_INVENTORY, "invtabs")  # the mod's charm inventory since the release after 0.1.19
        self.assertEqual(ci.CHARM_INVENTORIES, ("charminv", "invtabs"))
        with mock.patch.dict(os.environ):
            os.environ.pop(ci.ENV, None)
            self.assertEqual(ci.chosen(), ci.CHARM_INVENTORY)
            self.assertEqual(ci.chosen("invtabs"), "invtabs")
            os.environ[ci.ENV] = "invtabs"
            self.assertEqual(ci.chosen(), "invtabs")
            self.assertEqual(ci.chosen("charminv"), "charminv")  # the command line wins over the environment
            os.environ[ci.ENV] = "both"
            with self.assertRaises(SystemExit):
                ci.chosen()

    def test_the_package_and_the_build_read_the_same_switch(self):
        import package_release as pr
        self.assertEqual(pr.CHARM_INVENTORY, ci.CHARM_INVENTORY)
        self.assertEqual(pr.INVTABS_DATA, ci.INVTABS_DATA)

    def test_names_shared_with_the_legacy_tool(self):
        self.assertTrue(ci.BUTTON.search('"name": "%s"' % il.BUTTON_NAME))
        self.assertEqual([Path(rel).name for rel in ci.CLASSIC_INVENTORY], list(il.CLASSIC_INVENTORY))


class BuildSteps(unittest.TestCase):
    def test_charminv_build_is_the_build_without_invtabs(self):
        steps = build.steps_for("charminv")
        self.assertEqual(steps, build.STEPS)
        self.assertEqual(steps, [*build.DATA_STEPS, *build.ART_STEPS, *build.STRING_MERGE, ["devmenu_catalog.py"], ["wikipanel_export.py"], ["validate.py"]])
        self.assertEqual(scripts(steps).count("charm_inv.py"), 1)
        self.assertFalse(set(scripts(steps)) & set(INVTABS_SCRIPTS))  # no invtabs data, no classic Charms button

    def test_invtabs_build_adds_its_steps_after_legacy_art_and_drops_charminv_tables(self):
        steps = build.steps_for("invtabs")
        names = scripts(steps)
        self.assertNotIn("charm_inv.py", names)
        at = names.index("legacy_art.py")
        self.assertEqual(names[at + 1:at + 5], INVTABS_SCRIPTS)
        self.assertEqual([s[1] for s in steps[at + 1:at + 5]], ["build", "build", "build", "button"])
        self.assertLess(names.index("hd_ui.py"), at)                 # the classic inventory layouts exist before the button
        self.assertLess(at + 4, names.index("median_tabs.py"))
        # everything else is the CharmInv build, in the same order
        rest = [s for s in steps if s not in build.INVTABS_STEPS]
        self.assertEqual(rest, [s for s in build.STEPS if s != build.CHARMINV_STEP])
        self.assertEqual(names[-1], "validate.py")

    def test_every_step_script_exists(self):
        for step in build.INVTABS_STEPS + [build.CHARMINV_STEP]:
            self.assertTrue((TOOLS / step[0]).is_file(), step[0])

    def test_data_only(self):
        for name in ci.CHARM_INVENTORIES:
            names = scripts(build.steps_for(name, data_only=True))
            self.assertFalse(set(names) & set(INVTABS_SCRIPTS))
            self.assertEqual("charm_inv.py" in names, name == "charminv")
            self.assertEqual(names[-1], "validate.py")

    def test_command_line(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(ci.ENV, None)
            self.assertEqual(build.charm_inventory_arg([]), ci.CHARM_INVENTORY)
            self.assertEqual(build.charm_inventory_arg(["--keep-going", "--charm-inventory", "invtabs"]), "invtabs")
            self.assertEqual(build.charm_inventory_arg(["--charm-inventory=charminv"]), "charminv")
            for bad in (["--charm-inventory"], ["--charm-inventory", "none"], ["--charm-inventory=x"]):
                with self.assertRaises(SystemExit):
                    build.charm_inventory_arg(bad)
        with self.assertRaises(SystemExit):
            build.steps_for("both")


class ClassicButton(unittest.TestCase):
    """The classic inventory's Charms button exists only in a build for invtabs."""

    def test_ui_layouts_does_not_add_it(self):
        self.assertNotIn("invtabs", (TOOLS / "ui_layouts.py").read_text("utf-8"))
        import ui_layouts as ul
        try:
            texts = [ul.inventory_original(ul.table_rows()["Amazon"]), ul.inventory_expansion()]
        except (OSError, KeyError, SystemExit) as e:  # no D2R baseline layouts or no built inventory.txt here
            self.skipTest(f"ui_layouts inputs missing: {e}")
        for text in texts:
            self.assertNotIn(il.BUTTON_NAME, text)
            self.assertIn("MxlSendStash", text)

    def layouts(self, d: str, hd: bool = True) -> Path:
        lay = Path(d) / "global" / "ui" / "layouts"
        lay.mkdir(parents=True)
        for n in il.CLASSIC_INVENTORY + (il.HD_INVENTORY if hd else ()):
            (lay / n).write_text(LAYOUT, "utf-8")
        return lay

    def test_button_step_adds_it_once_to_both_classic_layouts_only(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            lay = self.layouts(d)
            self.assertEqual(ci.built_for(Path(d)), "charminv")
            self.assertEqual(il.main(["button", "--out", d]), 0)
            self.assertEqual(il.main(["button", "--out", d]), 0)  # idempotent
            for n in il.CLASSIC_INVENTORY:
                self.assertEqual((lay / n).read_text("utf-8").count(il.BUTTON_NAME), 1)
            for n in il.HD_INVENTORY:
                self.assertEqual((lay / n).read_text("utf-8"), LAYOUT)
            self.assertEqual(ci.built_for(Path(d)), "invtabs")

    def test_button_step_fails_without_a_layout_or_with_an_hd_button(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as out:
            lay = self.layouts(d)
            (lay / il.CLASSIC_INVENTORY[1]).unlink()
            self.assertEqual(il.main(["button", "--out", d]), 1)
            self.assertIn("is missing", out.getvalue())
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as out:
            lay = self.layouts(d)
            (lay / il.HD_INVENTORY[0]).write_text(il.add_button_to_layout(LAYOUT), "utf-8")
            self.assertEqual(il.main(["button", "--out", d]), 1)
            self.assertIn("HD has its own button", out.getvalue())


class DataProblems(unittest.TestCase):
    def tree(self, d: str, invtabs: bool, button: bool, charminv: bool) -> Path:
        data = Path(d)
        write(data, ["global/excel/armor.txt"])
        write(data, ci.CLASSIC_INVENTORY, il.add_button_to_layout(LAYOUT) if button else LAYOUT)
        if invtabs:
            write(data, ci.INVTABS_DATA)
        if charminv:
            write(data, ci.CHARMINV_DATA)
        return data

    def test_a_charminv_build(self):
        with tempfile.TemporaryDirectory() as d:
            data = self.tree(d, invtabs=False, button=False, charminv=True)
            self.assertEqual(ci.data_problems(data, "charminv"), [])
            self.assertEqual(ci.built_for(data), "charminv")
            wrong = ci.data_problems(data, "invtabs")
            self.assertEqual(len(wrong), len(ci.INVTABS_DATA) + 2 + 2)  # its files, the two buttons, CharmInv's two tables
            self.assertTrue(all("--charm-inventory invtabs" in w for w in wrong))

    def test_an_invtabs_build(self):
        with tempfile.TemporaryDirectory() as d:
            data = self.tree(d, invtabs=True, button=True, charminv=False)
            self.assertEqual(ci.data_problems(data, "invtabs"), [])
            self.assertEqual(ci.built_for(data), "invtabs")
            wrong = ci.data_problems(data, "charminv")
            self.assertEqual(len(wrong), len(ci.INVTABS_DATA) + 2)       # a dead button and unused files in a CharmInv package
            self.assertTrue(any("opens nothing with CharmInv" in w for w in wrong))

    def test_a_half_switched_tree(self):
        with tempfile.TemporaryDirectory() as d:
            data = self.tree(d, invtabs=True, button=False, charminv=True)
            self.assertEqual(len(ci.data_problems(data, "invtabs")), 4)  # no button twice, CharmInv's tables twice
            self.assertEqual(len(ci.data_problems(data, "charminv")), len(ci.INVTABS_DATA))

    def test_a_layout_that_is_not_in_the_folder_is_not_judged(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            write(data, ci.INVTABS_DATA)
            self.assertEqual(ci.data_problems(data, "invtabs"), [])
            self.assertEqual(ci.data_problems(Path(d) / "none", "charminv"), [])


if __name__ == "__main__":
    unittest.main()
