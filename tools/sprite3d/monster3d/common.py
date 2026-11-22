"""Lane hdtools-monster3d: paths, settings and the GPU gate shared by the stage scripts (Windows and Linux).

WT is this checkout. EV is the lane's working folder outside the repository (stages, shots, logs, sheets). Large files,
tools and weights are in the art store (STORE): art() and tool() find them, store.py fetches them back.

Nothing machine-specific is written here. Each setting is read from, in order: its environment variable, the git-ignored
machine config (machine.json, tools/localconfig.py: key in brackets), else the default.
  MXL_M3D_DIR          [m3d_dir]        EV; default <runs folder>/hdtools/monster3d
  MXL_ART_STORE        [art_store]      the art store (owner ruling 2026-11-18); no default: art() of a moved file and
                                        tool() of a moved tree need it
  MXL_BLENDER          [blender]        Blender 4.5.9 (the version of the toolchain manifest); default: the art store's tree
                                        (Windows build) on Windows, `blender` on PATH elsewhere
  MXL_REALESRGAN       [realesrgan]     realesrgan-ncnn-vulkan 0.2.5.0; default: the art store's tree on Windows, PATH elsewhere
  MXL_TRIPOSG_SRC, MXL_TRIPOSG_WEIGHTS, MXL_HUNYUAN_SRC, MXL_HUNYUAN_WEIGHTS (the folder that holds Hunyuan3D-2mv)
                                        [triposg_src, triposg_weights, hunyuan_src, hunyuan_weights]; default: the art
                                        store's trees
On Linux /d2work/tools/env.sh sets the tool variables; machine.json holds m3d_dir and art_store.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
WINDOWS = os.name == "nt"
sys.path.insert(0, str(WT / "tools"))
import localconfig  # noqa: E402  (machine.json, the runs folder)


def setting(env: str, key: str, default=None):
    """The environment variable `env`, else machine.json's `key`, else `default` (a string or None)."""
    v = os.environ.get(env)
    if v:
        return v
    try:
        v = localconfig.machine().get(key)
    except SystemExit:
        v = None
    return str(v) if v else default


EV = Path(setting("MXL_M3D_DIR", "m3d_dir") or localconfig.runs_dir() / "hdtools" / "monster3d")
# lane hdtools-monster's frame tools (monster_sheet, monster_upscale): the copy in EV when there is one (what the rounds used),
# else this checkout's own tools (that lane is merged here)
FCOPY = EV / "tools" / "fcopy" if (EV / "tools" / "fcopy").is_dir() else WT / "tools"

# The art store (owner ruling 2026-11-18): large outputs, tools and model weights live there, not under EV.
# EV/ART-MANIFEST.json maps each moved file's logical path (its old path relative to EV) to its content hash, and each moved
# tool or weights folder to its tree in the store. `store.py` fetches files back.
_store = setting("MXL_ART_STORE", "art_store")
STORE = Path(_store) if _store else None
MANIFEST = EV / "ART-MANIFEST.json"
_manifest = None


def need_store() -> Path:
    if STORE is None:
        raise SystemExit("no art store set: MXL_ART_STORE or art_store in %s (tools/localconfig.py)" % localconfig.machine_path())
    return STORE


def manifest() -> dict:
    global _manifest
    if _manifest is None:
        _manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {"files": [], "toolchain": {}}
        _manifest["by_path"] = {f["path"]: f for f in _manifest["files"]}
    return _manifest


def object_path(sha256: str) -> Path:
    return need_store() / "objects" / "sha256" / sha256[:2] / sha256


def art(logical) -> Path:
    """A file by its logical path under EV ("fungus/round5/stages/3-tone-f/albedo.png", or an absolute path inside EV):
    the local file when it is there, else its object in the art store. Raises FileNotFoundError when neither has it."""
    p = Path(logical)
    if p.is_absolute():
        try:
            p = p.relative_to(EV)
        except ValueError:
            return p
    local = EV / p
    if local.is_file():
        return local
    entry = manifest()["by_path"].get(p.as_posix())
    if entry and object_path(entry["sha256"]).is_file():
        return object_path(entry["sha256"])
    raise FileNotFoundError("%s: not under %s and not in the art store manifest (%s)" % (p.as_posix(), EV, STORE))


def tool(old: str) -> Path:
    """A tool or weights folder by its old place under EV ("tools/blender", "weights/TripoSG"): the local folder when
    one is there (a restored copy), else its tree in the art store."""
    local = EV / old
    if local.is_dir() and any(local.iterdir()):
        return local
    tree = manifest()["toolchain"].get(old)
    return STORE / tree["tree"] if tree and STORE is not None else local


def _exe(env, key, tree, win_rel, name):
    """A tool's program: the setting, else (Windows) its exe in the art store's tree, else `name` on PATH."""
    v = setting(env, key)
    if v:
        return Path(v)
    if WINDOWS:
        return tool(tree) / win_rel
    return Path(shutil.which(name) or name)


def _dir(env, key, tree):
    v = setting(env, key)
    return Path(v) if v else tool(tree)


BLENDER = _exe("MXL_BLENDER", "blender", "tools/blender", "blender-4.5.9-windows-x64/blender.exe", "blender")
ESRGAN = _exe("MXL_REALESRGAN", "realesrgan", "tools/esrgan", "realesrgan-ncnn-vulkan.exe", "realesrgan-ncnn-vulkan")
TRIPOSG_SRC = _dir("MXL_TRIPOSG_SRC", "triposg_src", "tools/triposg-src")
TRIPOSG_WEIGHTS = _dir("MXL_TRIPOSG_WEIGHTS", "triposg_weights", "weights/TripoSG")
HUNYUAN_SRC = _dir("MXL_HUNYUAN_SRC", "hunyuan_src", "tools/hunyuan-src")
# run_hunyuan.py wants the folder that holds Hunyuan3D-2mv
_hw = setting("MXL_HUNYUAN_WEIGHTS", "hunyuan_weights")
HUNYUAN_WEIGHTS = Path(_hw) if _hw else tool("weights/Hunyuan3D-2mv").parent


def _token() -> str:
    """--token <monster token> on any stage script's command line (taken out of sys.argv), else MXL_M3D_TOKEN, else the
    Hardliner's."""
    if "--token" in sys.argv:
        i = sys.argv.index("--token")
        token = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return token
    return os.environ.get("MXL_M3D_TOKEN") or "~k"


TOKEN = _token()
NAMES = {"~k": "hardliner", "2(": "fungus"}
NAME = NAMES.get(TOKEN) or "".join(c if c.isalnum() else "%02x" % ord(c) for c in TOKEN.lower())
# one folder per monster under EV (stages, shots, logs, scratch); the first one, the Hardliner, has EV itself.
# venv, weights, tools, tmp, cache and d2r (vanilla donor files) are shared.
HOME = EV if TOKEN == "~k" else EV / NAME
# MXL_M3D_ROUND=<name>: a later round of the same monster keeps its stages, shots and logs in HOME/<name>
if os.environ.get("MXL_M3D_ROUND"):
    HOME = HOME / os.environ["MXL_M3D_ROUND"]
STAGES = HOME / "stages"
# file direction numbers of an 8-direction monster, clockwise on screen from "down" (the monster faces the camera)
CLOCKWISE_8 = (4, 0, 5, 1, 6, 2, 7, 3)
DIR_NAMES_8 = ("down-left", "up-left", "up-right", "down-right", "down", "left", "up", "right")

def squash_u(img, strip, fill=0):
    """An (h, w, ...) image in an atlas layout squeezed into the left (1 - strip) of its width (bilinear), the right `strip`
    filled with `fill`: the layout of a mesh whose u was scaled by (1 - strip) (s5_build.py --strip)."""
    import numpy as np
    from PIL import Image
    if not strip:
        return img
    h, w = img.shape[:2]
    keep = int(round(w * (1 - strip)))
    small = np.asarray(Image.fromarray(img).resize((keep, h), Image.BILINEAR))
    out = np.empty_like(img)
    out[...] = fill
    out[:, :keep] = small
    return out


COUNTER = (r"[int]((Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -SampleInterval 2 -MaxSamples 1)"
           r".CounterSamples | Measure-Object CookedValue -Sum).Sum")
CPU_COUNTER = r"[int](Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 3 -MaxSamples 1).CounterSamples[0].CookedValue"


def _pwsh_int(command) -> int:
    try:
        out = subprocess.run(["pwsh", "-NoProfile", "-Command", command], capture_output=True, text=True).stdout.strip()
    except OSError:
        return -1
    return int(out) if out.isdigit() else -1


def _linux_reading():
    """(gpu %, cpu %) on Linux from hdkit.gpugate.read_linux (amdgpu gpu_busy_percent, /proc/stat); -1 where unread."""
    try:
        from hdkit import gpugate
        gpu, _src, cpu = gpugate.read_linux()
    except Exception as e:  # noqa: BLE001  (another lane owns gpugate: a changed reader must not stop a stage)
        print("gpu reading failed: %r" % (e,), flush=True)
        return -1, -1
    return (int(round(gpu)) if gpu is not None else -1), (int(round(cpu)) if cpu is not None else -1)


def cpu_percent() -> int:
    """The machine's CPU load in percent over a few seconds (-1 when it cannot be read)."""
    return _pwsh_int(CPU_COUNTER) if WINDOWS else _linux_reading()[1]


def gate_state():
    out = subprocess.run([sys.executable, "tools/game_slots.py", "status"], cwd=WT, capture_output=True, text=True).stdout
    held = [line.split(":")[0] for line in out.splitlines() if line.startswith("slot") and "lock free" not in line]
    gpu = _pwsh_int(COUNTER) if WINDOWS else _linux_reading()[0]
    return held, gpu


def gpu_gate(wait: int = 0, limit: int = 25) -> bool:
    """True when no game slot is locked and the GPU's 3D load is under `limit` percent; waits up to `wait` seconds."""
    end = time.time() + wait
    while True:
        held, gpu = gate_state()
        if not held and 0 <= gpu < limit:
            print("gate open: no slot locked, gpu %d%%" % gpu, flush=True)
            return True
        if time.time() >= end:
            print("gate closed: locked %s, gpu %d%%" % (held or "none", gpu), flush=True)
            return False
        time.sleep(15)


if __name__ == "__main__":
    sys.exit(0 if gpu_gate(int(sys.argv[1]) if len(sys.argv) > 1 else 0) else 1)
