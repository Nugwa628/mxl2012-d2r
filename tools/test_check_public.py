"""tools/check_public.py's mention rule: the built-in (encoded) copy compiles and flags what machine.json's list flags, our
own name passes, game terms pass, and machine.json's list wins when it has one. The names are built from pieces here so
that this file does not spell them out itself."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import check_public as cp  # noqa: E402

OTHER = "D2R-" + "XL"
WORD = "sis" + "ter"


class MentionRule(unittest.TestCase):
    def setUp(self):
        self.builtin = cp.load_mentions({})

    def hits(self, line, mentions=None):
        return [s for _, s in cp.scan_mentions(line, self.builtin if mentions is None else mentions)]

    def test_builtin_copy_flags_the_names(self):
        self.assertTrue(self.builtin)
        for line in (f"as {OTHER} does", f"the {WORD} project", f"the {WORD.title()} repo", "C:/Users/x/mxl-" + "d2r/tools",
                     "Median 2." + "14.4 rows", "Median XL 2." + "1x"):
            self.assertTrue(self.hits(line), line)

    def test_our_own_name_and_game_terms_pass(self):
        for line in (f"{OTHER} 2012 0.1.0", f"{OTHER}-2012-Downloader.exe", f"the {WORD.title()}s' Burial Grounds quest",
                     f"{WORD.title()}s of the Sightless Eye", f"{WORD.title()}s to the Slaughter", "version 2.140", "mxl2012-core"):
            self.assertEqual(self.hits(line), [], line)

    def test_machine_list_wins(self):
        mine = cp.load_mentions({"public_check_patterns": ["forbidden"]})
        self.assertEqual(self.hits("a forbidden word", mine), ["forbidden"])
        self.assertEqual(self.hits(f"as {OTHER} does", mine), [])

    def test_machine_list_matches_the_builtin_copy_when_present(self):
        pats = cp.MACHINE.get("public_check_patterns")
        if not pats:
            self.skipTest("no machine.json public_check_patterns on this machine")
        self.assertEqual([r.pattern for r in self.builtin], pats, "re-encode MENTION_FALLBACK (check_public.py docstring)")


if __name__ == "__main__":
    unittest.main()
