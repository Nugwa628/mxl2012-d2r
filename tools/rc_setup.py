"""Character SET-UP for the rules checks (lane rulescheck2): edits of a closed test character's save with our own code.

Coordinator ruling (lane_rules, "PLAYER PATH vs SET-UP", 2026-10-28): a check may set up a mid-game character (level,
points, quest flags, difficulty unlocked, gear, a hired mercenary) by harness or by a save written with our own tools, as
long as the ACTION being judged stays on the player path. This module is the save half; every edit is named in the
check's note.

D2R 3.3 save (v105) header, measured on the slots' saves (docs/save-format.md): the 1.x header moved 16 bytes down.
  0x14 status, 0x15 progression (difficulty unlock: expansion 5 = Nightmare, 10 = Hell, 15 = all done), 0x18 class,
  0x1b level, 0x98-0x9a one byte per difficulty (bit 7 = the one last played, low bits = act), 0xa1 u16 mercenary dead,
  0xa3 u32 mercenary id (0 = none), 0xa7 u16 name index, 0xa9 u16 hireling id, 0xab u32 mercenary experience.
Quest words ("Woo!" + 10 bytes, 48 u16 words per difficulty): word q bit b is the game's quest flag (q, b) (1.14d reader
`0x65c310`, D2R `0x325c50`; mxl2012-runs/rulescheck2/re332/findings.md).
After an edit the checksum and D2RLoader's `.d2rl` sidecar are made again (a mismatch hides the character).
"""
import hashlib
import os
import struct

OFF_PROGRESSION = 0x15
OFF_DIFFICULTY = 0x98
OFF_MERC_ID = 0xA3
OFF_MERC_HIRELING = 0xA9
OFF_MERC_EXP = 0xAB
PROGRESSION = {"normal": 0, "nightmare": 5, "hell": 10}  # expansion titles: Slayer 5, Champion 10, Patriarch/Matriarch 15

# Quest flags the rules checks set (word, bit); the item gates are 1.14d `0x55cc90` = D2R `0x4734f0`
Q_BURIAL = 2  # the Burial Grounds quest: Kashya hires after bit 0 (D2R NPC table 0x237ea60 +0x10 = quest + 1)
Q_RADAMENT, Q_GOLDEN_BIRD, Q_PRISON_OF_ICE = 9, 20, 37
QUEST_ITEM_GATE = {"ass": (Q_RADAMENT, 5), "xyz": (Q_GOLDEN_BIRD, 5), "tr2": (Q_PRISON_OF_ICE, 8)}
DONE = 0x1001  # bit 0 (completed) + bit 12 (seen in an earlier game), as a finished quest is saved


def checksum(d):
    """The save with its size and checksum fields made again (rotate-left-1 + byte sum with the field zeroed)."""
    d = bytearray(d)
    d[8:12] = len(d).to_bytes(4, "little")
    d[12:16] = b"\0\0\0\0"
    c = 0
    for b in d:
        c = ((c << 1) | (c >> 31)) & 0xFFFFFFFF
        c = (c + b) & 0xFFFFFFFF
    d[12:16] = c.to_bytes(4, "little")
    return bytes(d)


def sidecar(sidecar_bytes, save):
    """D2RLoader's `.d2rl` for `save`: save checksum (+0x34), size (+0x38), SHA-256 of the save (+0x3c), body hash (+0x0c)."""
    r = bytearray(sidecar_bytes)
    struct.pack_into("<I", r, 0x34, struct.unpack_from("<I", save, 12)[0])
    struct.pack_into("<I", r, 0x38, len(save))
    r[0x3C:0x5C] = hashlib.sha256(save).digest()
    r[0x0C:0x2C] = hashlib.sha256(bytes(r[0x2C:])).digest()
    return bytes(r)


def quest_offset(save, difficulty, word):
    i = bytes(save).find(b"Woo!")
    if i < 0:
        raise ValueError("no quest section ('Woo!')")
    return i + 10 + difficulty * 96 + word * 2


def get_quest(save, difficulty, word):
    return struct.unpack_from("<H", save, quest_offset(save, difficulty, word))[0]


def set_quest_bits(save, difficulty, word, bits):
    """OR the bits (a mask) into quest word `word` of `difficulty` (0 Normal, 1 Nightmare, 2 Hell)."""
    s = bytearray(save)
    o = quest_offset(s, difficulty, word)
    struct.pack_into("<H", s, o, struct.unpack_from("<H", s, o)[0] | bits)
    return bytes(s)


def set_progression(save, difficulty):
    """Unlock a difficulty (the title byte); never lowers it."""
    s = bytearray(save)
    s[OFF_PROGRESSION] = max(s[OFF_PROGRESSION], PROGRESSION[difficulty])
    return bytes(s)


def merc(save):
    """(mercenary id, hireling id, experience); id 0 = no mercenary."""
    return (struct.unpack_from("<I", save, OFF_MERC_ID)[0], struct.unpack_from("<H", save, OFF_MERC_HIRELING)[0],
            struct.unpack_from("<I", save, OFF_MERC_EXP)[0])


def set_merc_experience(save, exp):
    if merc(save)[0] == 0:
        raise ValueError("the character has no mercenary")
    s = bytearray(save)
    struct.pack_into("<I", s, OFF_MERC_EXP, exp)
    return bytes(s)


def merc_exp_for_level(level, exp_per_level):
    """Hireling experience at which `level` starts: Exp/Lvl * L * L * (L + 1) (1.13c's hireling formula, D2R the same)."""
    return exp_per_level * level * level * (level + 1)


def edit(saves_dir, name, fn):
    """Apply fn(bytes) -> bytes to <name>.d2s of a CLOSED character, fix the checksum and the sidecar. Returns the new bytes."""
    p = os.path.join(saves_dir, name + ".d2s")
    s = checksum(fn(open(p, "rb").read()))
    open(p, "wb").write(s)
    sp = os.path.join(saves_dir, name + ".d2rl")
    if os.path.exists(sp):
        old = open(sp, "rb").read()  # read before the write opens (and empties) the file
        open(sp, "wb").write(sidecar(old, s))
    return s
