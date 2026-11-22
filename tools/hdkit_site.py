"""Site adapter of hdkit for this repository: what "a test run is in progress" means here.

hdkit (tools/hdkit) is general and moves to its own repository later; the rules of this machine stay here. A GPU job waits
while any game slot lock of tools/game_slots.py is held (game.lock.N and the old single game.lock in the shared lock folder,
machine.json `shared_lock_dir` or env MXL_LOCKS), whichever project holds it.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _machine() -> dict:
    try:
        import localconfig
        return localconfig.machine()
    except Exception:  # noqa: BLE001  (no machine config)
        return {}


def store_root() -> str:
    """The art store for large outputs (owner ruling 2026-11-18): MXL_ART_STORE, else machine.json `art_store`, else
    D:\\mxl2012-art (the Windows place)."""
    return os.environ.get("MXL_ART_STORE") or _machine().get("art_store") or r"D:\mxl2012-art"


# ---- in-game sign-off (hdkit.signoff.config) ---------------------------------------------------------------------------------
# What this project adds to the general sign-off tool: the units it knows, its slots, lock names, evidence places and the
# game-run framework (tools/game_checks.py with game_ctl / game_slots). machine.json `hdkit_signoff` (same keys) overrides
# per machine, e.g. {"m3d_ev": "/d2work/migrated/mxl2012-runs/hdtools/monster3d", "linux": {"dev_plugin": ".../mxl2012-core.dll"}}.

def signoff_settings() -> dict:
    import localconfig
    tools = Path(__file__).resolve().parent
    runs = Path(localconfig.runs_dir())
    # the monster stages: the same setting as tools/sprite3d/monster3d/common.py (MXL_M3D_DIR, machine.json m3d_dir)
    m3d = os.environ.get("MXL_M3D_DIR") or _machine().get("m3d_dir") or str(runs / "hdtools" / "monster3d")
    s = {
        "runs_root": str(runs),
        "ev": str(runs / "hdtools" / "viewer" / "p8"),
        "m3d_ev": str(m3d),
        "art_store": store_root(),
        "units": {"2(": {"id": "fungus1", "name": "fungus", "stage": "fungus/round11/stages/5-r11a"}},
        "area": 2, "slot": 2, "slots": [2, 5],
        "lock_holder": "hdtools-viewer",
        "windows": {"heavy_lock": str(runs / "tools" / "heavy_lock.py"), "heavy_token": "game",
                    "worktree_root": str(tools.parent),
                    # lanes hdtools-monster3d and hdtools-monster are merged into this checkout: its own scripts
                    "gamerun": str(tools / "sprite3d" / "monster3d" / "g6_gamerun.py"),
                    "framework_tools": str(tools), "m3d_env": "MXL_M3D_DIR", "framework_env": "MXL_M3D_FRAMEWORK",
                    "check": "mon_moves", "runner": "g6_movecap.py"},
        "linux": {"framework_tools": str(tools), "plugin_dest": "d2rloader/plugins/mxl2012-core.dll",
                  "mod_data": "mxl2012.mpq/data", "env": {"MXL_CHAR": "Montest", "MXL_DRAWCAP_PROBE": "1"}},
        "framework_env": {"run": "MXL_RUN", "slot": "MXL_SLOT", "runs": "MXL_RUNS"},
    }
    over = _machine().get("hdkit_signoff") or {}
    if over:
        from hdkit.signoff import config
        s = config.merge(s, over)
    return s


def lock_globs() -> list:
    root = os.environ.get("MXL_LOCKS")
    if not root:
        try:
            import localconfig
            root = localconfig.machine().get("shared_lock_dir") or ""
        except Exception:  # noqa: BLE001  (no machine config: no locks known)
            root = ""
    return [os.path.join(root, "game.lock*")] if root else []


# ---- CASC on demand (hdkit.view.casc.from_site) ------------------------------------------------------------------------------
# Owner ruling 2026-11-19 (decision 3): base files are read from a game slot's CASC on demand and kept in a capped,
# git-ignored cache inside the project on C: (not the art store); the research extract viewer/re/casc seeds it.

CASC_CACHE_GB = 4.0


def casc_game_dir() -> str:
    """The game folder whose CASC is read: MXL_D2R_GAME / MXL_SLOT as tools/d2r_game.py, else slot 5 (a 3.3 test copy;
    never the owner's slot 1 by default)."""
    import game_slots
    if os.environ.get("MXL_D2R_GAME") or os.environ.get("MXL_SLOT"):
        import d2r_game
        return d2r_game.read_game_dir()
    return game_slots.slot_dir(5)


def _hdtools_runs() -> Path:
    import localconfig
    return Path(localconfig.runs_dir()) / "hdtools" / "viewer"


def casc_cache_dir() -> str:
    """<runs>/hdtools/viewer/cache/casc (the runs folder is git-ignored by the coordinator checkout)."""
    return str(_hdtools_runs() / "cache" / "casc")


def casc_cache_gb() -> float:
    return CASC_CACHE_GB


def casc_seeds() -> list:
    """Read-only copies made before the cache existed: the dump research's 191 MB (shaders, env/vis)."""
    p = _hdtools_runs() / "re" / "casc" / "data"
    return [str(p)] if p.is_dir() else []


class _CascStorage:
    """tools/native.py's CascLib wrapper as the storage object hdkit.view.casc expects."""

    def __init__(self, game_dir):
        import native
        self.native = native
        self.handle = native.open_casc(game_dir)

    def read(self, name: str) -> bytes:
        return self.native.casc_read(self.handle, name)

    def close(self):
        if self.handle:
            self.native.casc.CascCloseStorage(self.handle)
            self.handle = None


def casc_opener(game_dir):
    return _CascStorage(game_dir)


def game_dir_free(game_dir) -> bool:
    """No run holds the game folder: its slot lock is free and no game process runs from it (unknown folders: free)."""
    import game_slots
    n = game_slots.slot_of_game_dir(game_dir)
    if n is None:
        return True
    try:
        if game_slots.lock_info(n) is not None:
            return False
        return not game_slots.slot_processes(game_slots.slot_dir(n))
    except SystemExit:
        return False
