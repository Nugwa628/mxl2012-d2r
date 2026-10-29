"""tools/merge_string_overrides.py: data/d2r_string_fixes.json (bugs.md #18) and the committed file itself."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import merge_string_overrides as m  # noqa: E402

LANGS = ["enUS", "deDE", "frFR"]


def record(key, text):
    return {"Key": key, **{lang: text for lang in LANGS}}


class FixTests(unittest.TestCase):
    def setup_dir(self, d, recs, fixes):
        sd = Path(d) / "strings"
        sd.mkdir()
        (sd / "overrides.json").write_text("﻿" + json.dumps(recs), encoding="utf-8")
        f = Path(d) / "fixes.json"
        f.write_text(json.dumps(fixes), encoding="utf-8")
        return sd, f

    def test_new_key_is_added_in_every_language(self):
        with tempfile.TemporaryDirectory() as d:
            sd, f = self.setup_dir(d, [record("d2r:A", "a")], [{"key": "d2r:Lilith", "text": "Pandora"}])
            self.assertEqual(m.merge(sd, [], None, f), (1, 0, []))
            recs = json.loads((sd / "overrides.json").read_text("utf-8-sig"))
            self.assertEqual(recs[-1], record("d2r:Lilith", "Pandora"))

    def test_existing_key_is_replaced_and_the_merge_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            sd, f = self.setup_dir(d, [record("d2r:Lilith", "Lilith")], [{"key": "d2r:Lilith", "text": "Pandora"}])
            self.assertEqual(m.merge(sd, [], None, f), (0, 1, []))
            self.assertEqual(m.merge(sd, [], None, f), (0, 0, []))
            recs = json.loads((sd / "overrides.json").read_text("utf-8-sig"))
            self.assertEqual([r["enUS"] for r in recs if r["Key"] == "d2r:Lilith"], ["Pandora"])

    def test_a_key_without_the_d2r_prefix_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            sd, f = self.setup_dir(d, [record("d2r:A", "a")], [{"key": "Lilith", "text": "Pandora"}])
            with self.assertRaises(SystemExit):
                m.merge(sd, [], None, f)

    def test_the_committed_file_is_well_formed(self):
        for f in json.loads(m.FIXES.read_text("utf-8")):
            self.assertTrue(f["key"].startswith("d2r:"), f)
            self.assertTrue(f["text"] and f["why"], f)
        self.assertIn("d2r:Lilith", [f["key"] for f in json.loads(m.FIXES.read_text("utf-8"))])


if __name__ == "__main__":
    unittest.main()
