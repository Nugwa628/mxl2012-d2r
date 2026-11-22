"""The game's orthographic camera: world <-> pixel maths and the sub-frustum of any pixel rectangle (for tiles).

Axes: y up; the camera looks down at elevation `el` from azimuth `az` (az 0 = from +z; D2R's camera is az 45, looking
along (-1, -k, -1)). The basis (right r, up u, towards the camera w) is the one of tools/sprite3d/cam_fit.py:

  r = (cos a, 0, -sin a),  u = (-sin a sin e, cos e, -cos a sin e),  w = (sin a cos e, sin e, cos a cos e)

A world point P lands on pixel  sx = ox + k (P.r),  sy = oy - k (P.u)  where (ox, oy) is the pixel of the world origin and k
the pixels per world unit. Its depth is P.w (larger = nearer the camera).

Scale. The HD ground grid in a 1600x900 capture: one sub-tile step is 24 px across and 12 px down, and a sub-tile is 2
world units, so one unit along x or z is (12, 6) px. A unit along x is 1/sqrt(2) of a unit across the screen, so
k = 12 sqrt(2) = 16.97 px per unit at that size; a unit of height is then k cos(el) = 14.70 px at el 30 (the value
docs measured for maps).

Game camera read from the 3.3 executable (lane hdtools, viewer/re/REPORT.md): orthographic, elevation exactly 30 degrees,
azimuth -135 degrees in the engine's own yaw (the same view direction as az 45 in this basis: looking along (-1, -k, -1)),
vertical view 53.03 world units at zoom 1 whatever the resolution, so k = screen height / 53.03 (16.97 at 900 px, the
ground-grid value above; 20.4 at 1080 px); the base width behind 53.03 is medium confidence (42.43 is the other branch).
The 34.3 degree unit fit of monster3d rule 7 was a fit artefact; it stays only as EL_UNITS_FIT for old comparisons.
"""
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_SPRITE3D = Path(__file__).resolve().parents[2] / "sprite3d"
if str(_SPRITE3D) not in sys.path:
    sys.path.insert(0, str(_SPRITE3D))
import cam_fit as _cam_fit  # noqa: E402

GAME_AZ = 45.0            # this basis; the engine's yaw for the same view is -135
GAME_EL = 30.0            # read from the executable (viewer/re/REPORT.md)
EL_MAPS = GAME_EL         # docs/maps-hd-method.md: map pieces, the same camera
EL_UNITS_FIT = 34.3       # monster3d METHOD rule 7: an old corpse-shot fit, superseded by GAME_EL
VIEW_HEIGHT_UNITS = 53.03   # vertical ortho extent at zoom 1 (5 sqrt(200) * 3/4)
K_1600x900 = 12.0 * math.sqrt(2.0)    # px per world unit in a 1600x900 capture (see above)
# Feet pixel of the player's sub-tile in a 1600x900 HD capture at zoom 1. The shot cuts of monster3d rounds 10/11 used
# y 428; corpse renders matched the game masks only 8..11 px lower (viewer p1, p2, and p4: dy +9.5 median over 6 corpse
# fits in two runs, dx 0), so the anchor is (800, 437.5). A sub-tile step is (24, 12) px (p4 ground-shift measure).
FEET_1600x900 = (800.0, 437.5)
FEET_OLD_CUT_1600x900 = (800.0, 428.0)


def unit_pixel(dx: float, dy: float, height: float = 900.0) -> tuple:
    """Screen pixel of the feet of a unit dx, dy sub-tiles from the player (harness sub-tile coordinates) in an HD capture
    `height` px high (16:9, zoom 1): (24 (dx - dy), 12 (dx + dy)) px per step from FEET_1600x900, all scaled by height/900."""
    s = float(height) / 900.0
    return (s * (FEET_1600x900[0] + 24.0 * (dx - dy)), s * (FEET_1600x900[1] + 12.0 * (dx + dy)))


def k_for_height(screen_h: float, zoom: float = 1.0) -> float:
    """Pixels per world unit for a screen height (the game's ortho view is VIEW_HEIGHT_UNITS / zoom high)."""
    return float(screen_h) * float(zoom) / VIEW_HEIGHT_UNITS


def facts(height: float = 900.0, zoom: float = 1.0, el: float = GAME_EL, az: float = GAME_AZ) -> dict:
    """The camera this module renders with, as numbers: projection, angles, scale at a screen height, feet pixel."""
    k = k_for_height(height, zoom)
    r, u, w = basis(az, el)
    s = float(height) / 900.0
    return {"projection": "orthographic", "elevation_deg": el, "azimuth_deg": az, "engine_yaw_deg": -135.0,
            "view_height_units": round(VIEW_HEIGHT_UNITS / zoom, 4), "screen_height_px": height, "zoom": zoom,
            "px_per_unit": round(k, 4), "px_per_unit_height": round(k * math.cos(math.radians(el)), 4),
            "subtile_step_px": [round(24.0 * s * zoom, 4), round(12.0 * s * zoom, 4)], "subtile_units": 2.0, "tile_units": 10.0,
            "feet_px_16x9": [round(FEET_1600x900[0] * s, 3), round(FEET_1600x900[1] * s, 3)], "near_far": [10.0, 10000.0],
            "basis": {"right": [round(float(x), 6) for x in r], "up": [round(float(x), 6) for x in u],
                      "towards_camera": [round(float(x), 6) for x in w]},
            "facing": "yaw = yaw0 + sign * dir64 * 5.625 (yaw0 %g, sign -1); key k -> dir64 8k, 0 = screen bottom, "
                      "clockwise" % GAME_AZ,
            "el_units_fit_old": EL_UNITS_FIT,
            "sources": "3.3 executable read (lane hdtools viewer re/REPORT.md); ground-grid and feet measures (viewer p4)"}


def basis(az: float, el: float):
    """(r, u, w) of tools/sprite3d/cam_fit.py, reused as it is."""
    return _cam_fit.basis(az, el)


def rot_y(deg: float) -> np.ndarray:
    """3x3 turn about +y; positive turns +z towards +x."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def facing_yaw(dir64: float, yaw0: float = GAME_AZ, sign: float = -1.0) -> float:
    """Model yaw (degrees) for a game facing dir64 (0..63: 0 faces the screen's bottom, then clockwise on screen).

    A model looks along +z at yaw 0, so it faces the camera (the screen's bottom) at yaw = az; turning clockwise on the
    screen lowers the yaw. `yaw0` and `sign` stay parameters so that a fit can check them."""
    return yaw0 + sign * dir64 * (360.0 / 64.0)


def key_dir64(key: int) -> int:
    """Facing key 0..7 (0 = the screen's bottom, then clockwise) -> its dir64."""
    return (int(key) % 8) * 8


@dataclass
class OrthoCamera:
    el: float = GAME_EL
    az: float = GAME_AZ
    k: float = K_1600x900          # px per world unit

    def basis(self):
        return basis(self.az, self.el)

    def to_pixels(self, P, origin) -> np.ndarray:
        r, u, _w = self.basis()
        P = np.asarray(P, float)
        return np.stack([origin[0] + self.k * (P @ r), origin[1] - self.k * (P @ u)], -1)

    def depth(self, P) -> np.ndarray:
        return np.asarray(P, float) @ self.basis()[2]

    def matrix(self, origin, rect, dmin: float, dmax: float) -> np.ndarray:
        """4x4 (column vectors) world -> clip space of the pixel rectangle rect = (x0, y0, w, h) of an image whose world
        origin lands on pixel `origin`. Depth: 0 at dmax (nearest), 1 at dmin. Tiles of one image share pixel centres exactly,
        so they stitch without seams."""
        r, u, w = self.basis()
        x0, y0, tw, th = rect
        span = max(dmax - dmin, 1e-6)
        M = np.zeros((4, 4))
        M[0, :3] = 2.0 * self.k / tw * r
        M[0, 3] = 2.0 * (origin[0] - x0) / tw - 1.0
        M[1, :3] = 2.0 * self.k / th * u
        M[1, 3] = 1.0 - 2.0 * (origin[1] - y0) / th
        M[2, :3] = -w / span
        M[2, 3] = dmax / span
        M[3, 3] = 1.0
        return M


def ndc_to_pixels(ndc, rect) -> np.ndarray:
    """Inverse of the x/y part of `matrix` for a tile: NDC (x, y) -> pixel of the whole image."""
    x0, y0, tw, th = rect
    ndc = np.asarray(ndc, float)
    return np.stack([x0 + (ndc[..., 0] + 1.0) * tw / 2.0, y0 + (1.0 - ndc[..., 1]) * th / 2.0], -1)
