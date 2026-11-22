"""The D2R folder the data tools read the base game from (CASC: D2R's own tables, HD models, sprites).

Read-only use of a game slot's folder (tools/game_slots.py): env MXL_D2R_GAME (must be the folder of slot 1 to 5) or the
slot of env MXL_SLOT. There is no default: an unset MXL_SLOT is an error, as everywhere in this repo. Slot 1 is the owner's
own game: reading its CASC is harmless, but prefer slots 2 to 5 for data work. A slot whose folder is missing is refused.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402


def read_game_dir() -> str:
    if game_slots.LINUX:  # the data tools read D2R 93847's files; the Linux slots hold D2R 3.4.95032 (other fonts, ...)
        raise SystemExit("d2r_game: the Linux game slots hold D2R 3.4, not build 93847: the data tools read D2R 93847's "
                         "files from its extraction or the shared cache (docs/setup.md), not from a Linux slot")
    path = os.environ.get("MXL_D2R_GAME")
    if path:
        if game_slots.slot_of_game_dir(path) is None:
            raise SystemExit(f"MXL_D2R_GAME {path!r} is not the folder of game slot 1 to 5: refused")
        game_slots.require_present(game_slots.slot_of_game_dir(path), "MXL_D2R_GAME", path)
        return path
    return game_slots.slot_dir(game_slots.require_present(game_slots.env_slot(), "d2r_game"))
