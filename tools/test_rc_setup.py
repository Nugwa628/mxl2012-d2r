"""tools/rc_setup.py (save SET-UP of the rules checks, lane rulescheck2) and the rc2 verdict helpers of game_checks.py."""
import hashlib
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402
import rc_setup  # noqa: E402


def save(merc_id=0):
    """A minimal v105-shaped save: header, mercenary fields, a quest section (3 x 48 words)."""
    d = bytearray(0x140)
    d[0:4] = b"\x55\xaa\x55\xaa"
    struct.pack_into("<I", d, rc_setup.OFF_MERC_ID, merc_id)
    d += b"Woo!" + bytes(6) + bytes(3 * 96) + b"tail"
    return rc_setup.checksum(bytes(d))


class Checksum(unittest.TestCase):
    def test_size_and_checksum_fields(self):
        s = save()
        self.assertEqual(struct.unpack_from("<I", s, 8)[0], len(s))
        self.assertEqual(rc_setup.checksum(s), s)  # the field is zeroed before the sum, so it is stable

    def test_a_changed_byte_changes_the_checksum(self):
        s = bytearray(save())
        s[0x30] = 1
        self.assertNotEqual(rc_setup.checksum(bytes(s))[12:16], save()[12:16])


class Sidecar(unittest.TestCase):
    def test_fields(self):
        s = save()
        r = rc_setup.sidecar(bytes(0x80), s)
        self.assertEqual(struct.unpack_from("<I", r, 0x34)[0], struct.unpack_from("<I", s, 12)[0])
        self.assertEqual(struct.unpack_from("<I", r, 0x38)[0], len(s))
        self.assertEqual(r[0x3C:0x5C], hashlib.sha256(s).digest())
        self.assertEqual(r[0x0C:0x2C], hashlib.sha256(r[0x2C:]).digest())
        self.assertEqual(len(r), 0x80)


class Quests(unittest.TestCase):
    def test_bits_per_difficulty(self):
        s = rc_setup.set_quest_bits(save(), 1, rc_setup.Q_BURIAL, rc_setup.DONE)
        self.assertEqual(rc_setup.get_quest(s, 1, rc_setup.Q_BURIAL), rc_setup.DONE)
        self.assertEqual(rc_setup.get_quest(s, 0, rc_setup.Q_BURIAL), 0)
        s = rc_setup.set_quest_bits(s, 1, rc_setup.Q_BURIAL, 1 << 5)  # OR, never clears
        self.assertEqual(rc_setup.get_quest(s, 1, rc_setup.Q_BURIAL), rc_setup.DONE | 1 << 5)

    def test_offset_after_woo(self):
        s = save()
        self.assertEqual(rc_setup.quest_offset(s, 2, 37), s.find(b"Woo!") + 10 + 2 * 96 + 37 * 2)

    def test_no_quest_section(self):
        with self.assertRaises(ValueError):
            rc_setup.quest_offset(bytes(64), 0, 0)


class Progression(unittest.TestCase):
    def test_unlock_never_lowers(self):
        s = rc_setup.set_progression(save(), "hell")
        self.assertEqual(s[rc_setup.OFF_PROGRESSION], 10)
        self.assertEqual(rc_setup.set_progression(s, "nightmare")[rc_setup.OFF_PROGRESSION], 10)


class Mercenary(unittest.TestCase):
    def test_experience_needs_a_mercenary(self):
        with self.assertRaises(ValueError):
            rc_setup.set_merc_experience(save(), 5)
        s = rc_setup.set_merc_experience(save(merc_id=77), 123456)
        self.assertEqual(rc_setup.merc(s), (77, 0, 123456))

    def test_level_formula(self):
        self.assertEqual(rc_setup.merc_exp_for_level(100, 1), 100 * 100 * 101)


class Edit(unittest.TestCase):
    def test_edit_rewrites_save_and_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "Rc.d2s"), "wb").write(save())
            open(os.path.join(d, "Rc.d2rl"), "wb").write(bytes(0x80))
            s = rc_setup.edit(d, "Rc", lambda b: rc_setup.set_progression(b, "nightmare"))
            self.assertEqual(open(os.path.join(d, "Rc.d2s"), "rb").read(), s)
            side = open(os.path.join(d, "Rc.d2rl"), "rb").read()
            self.assertEqual(len(side), 0x80)  # read before the write (an early version emptied it)
            self.assertEqual(side[0x3C:0x5C], hashlib.sha256(s).digest())


class Verdicts(unittest.TestCase):
    def test_death_loss(self):
        self.assertEqual(gc.death_loss(421500, 407000, 436000, 1), 290)
        self.assertEqual(gc.death_loss(407100, 407000, 436000, 10), 100)  # never below the level's start

    def test_refund(self):
        before = {"statpts": 0, "newskills": 0, "strength": 45}
        self.assertTrue(gc.refund_verdict(before, {"statpts": 20, "newskills": 7, "strength": 25}, 20, 7))
        self.assertFalse(gc.refund_verdict(before, {"statpts": 20, "newskills": 6, "strength": 25}, 20, 7))


if __name__ == "__main__":
    unittest.main()
