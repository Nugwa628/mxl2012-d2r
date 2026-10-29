"""Lazy handles to the Windows system DLLs the game tools use (user32, kernel32, ...).

`ctypes.windll` only exists on Windows. The game tools (game_slots, game_ctl, game_checks) are Windows-only at run time, but
their pure logic (slot rules, lock files, name checks) is unit-tested on the Linux CI runner too, so importing them must not
need the DLLs: a handle loads its DLL on first attribute access and raises a clear OSError off Windows."""
import ctypes


class Dll:
    def __init__(self, name, setup=None):
        self._name, self._setup, self._lib = name, setup, None

    def __getattr__(self, attr):
        if attr.startswith("__"):                       # copy / pickle / inspect probes
            raise AttributeError(attr)
        if self._lib is None:
            windll = getattr(ctypes, "windll", None)
            if windll is None:
                raise OSError(f"{self._name}.dll is only available on Windows (this tool drives the game and needs Windows)")
            lib = getattr(windll, self._name)
            if self._setup:
                self._setup(lib)
            self._lib = lib
        return getattr(self._lib, attr)


def available():
    return getattr(ctypes, "windll", None) is not None
