"""Bug #504: D2R writes "<unit> says: <line>" into the chat whenever a class voice file (common\\<class>\\...) plays.
player_voice_sounds blanks the state / skill / missile sound cells that name such a row (Median's Vanquish, Raven Heart,
Female Vanquish, Mana Coil, Charged Elemental Fury); other sounds stay."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

SOUND_COLS = ["Sound", "*Index", "Channel", "FileName"]
SOUNDS = [
    ["paladin_chat_f_2", "", "vo/eax/player-dialog_sd", "common\\paladin\\pal_goodbye.flac"],
    ["femvanquish4860", "", "vo/eax/player-dialog_sd", "Common/Amazon/ama_goodbye.flac"],
    ["sorceress_chat_g_2", "", "vo/eax/player-dialog_sd", "common\\sorceress\\sor_timetodie.flac"],
    ["wussie_help_me", "", "vo/eax/dialog_sd", "act5\\soldier\\sol_helpus.flac"],
    ["baal_novacast", "", "sfx/monster-skills_sd", "act5\\monster\\baalnova.flac"],
    ["common_none", "", "", "common\\none.flac"],
]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class VoiceRowsTests(unittest.TestCase):
    def test_class_voice_files_only(self):
        self.assertEqual(tm.player_voice_rows(SOUND_COLS, SOUNDS),
                         {"paladin_chat_f_2", "femvanquish4860", "sorceress_chat_g_2"})

    def test_blank_cells(self):
        h = ["skill", "stsound", "stsoundclass", "ItemCastSound", "*sound note"]
        rows = [["Charged Elemental Fury", "baal_novacast", "sorceress_chat_g_2", "baal_novacast", "paladin_chat_f_2"],
                ["Other", "baal_novacast", "", "", ""]]
        hits = tm.blank_voice_cells(h, rows, {"paladin_chat_f_2", "sorceress_chat_g_2"})
        self.assertEqual(hits, [("Charged Elemental Fury", "stsoundclass", "sorceress_chat_g_2")])
        self.assertEqual(rows[0], ["Charged Elemental Fury", "baal_novacast", "", "baal_novacast", "paladin_chat_f_2"])
        self.assertEqual(rows[1], ["Other", "baal_novacast", "", "", ""])


class StepTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        tm.OUT = Path(self.temp.name) / "out"
        for bank in ("", "base"):
            ex = tm.OUT / "data" / "global" / "excel" / bank
            ex.mkdir(parents=True, exist_ok=True)
            (ex / "sounds.txt").write_text(tsv(SOUND_COLS, *SOUNDS), encoding="latin-1", newline="")
            (ex / "states.txt").write_text(tsv(["state", "onsound", "offsound"], ["vanquish", "paladin_chat_f_2", ""],
                                               ["vanquish_female", "femvanquish4860", ""], ["other", "baal_novacast", ""]),
                                           encoding="latin-1", newline="")
            (ex / "missiles.txt").write_text(tsv(["Missile", "TravelSound"], ["deathcoil", "wussie_help_me"]),
                                             encoding="latin-1", newline="")

    def test_step(self):
        m = tm.Migrator.__new__(tm.Migrator)
        m.report = []
        m.player_voice_sounds()
        for bank in ("", "base"):
            ex = tm.OUT / "data" / "global" / "excel" / bank
            h, rows = tm.read_tsv(ex / "states.txt")
            self.assertEqual([r[1] for r in rows], ["", "", "baal_novacast"])
            h, rows = tm.read_tsv(ex / "missiles.txt")
            self.assertEqual(rows[0][1], "wussie_help_me")
        self.assertIn("states vanquish onsound (paladin_chat_f_2)", m.report[0])
        self.assertIn("states vanquish_female onsound (femvanquish4860)", m.report[0])


if __name__ == "__main__":
    unittest.main()
