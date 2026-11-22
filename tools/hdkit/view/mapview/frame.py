"""The pixel frame shared by the classic and the HD map renders, so the same cell lands on the same pixel in both.

Classic iso (D2): the top corner of cell (x, y)'s floor diamond is at native pixel ((x - y) * 80, (x + y) * 40); a floor
tile is 160 x 80. HD (camera.py): world x, z = 10 x cell x, y (2 units per sub-tile), the game camera puts one unit along x
at (12, 6) px at scale 1, so a cell step is (120, 60) px: the HD render of a classic frame at scale s uses HD scale
s * 80 / 120 and the world origin on the frame's pixel of cell corner (0, 0).

A frame covers a cell range (x0..x1, y0..y1 inclusive): the bounding box of its ground diamonds, `rise` native px above
(tall walls, trees, models) and `drop` below, times `scale`.
"""
from __future__ import annotations

from dataclasses import dataclass

CELL_DX, CELL_DY = 80, 40          # native px per cell step (half a floor tile)
HD_PER_CLASSIC = 80.0 / 120.0      # HD camera scale per classic scale for the same cell size
DEFAULT_RISE = 360
DEFAULT_DROP = 40


@dataclass
class Frame:
    x0: int
    y0: int
    x1: int
    y1: int
    scale: float = 1.0
    rise: int = DEFAULT_RISE
    drop: int = DEFAULT_DROP

    # native rectangle
    @property
    def left(self) -> int:
        return (self.x0 - (self.y1 + 1)) * CELL_DX

    @property
    def right(self) -> int:
        return ((self.x1 + 1) - self.y0) * CELL_DX

    @property
    def top(self) -> int:
        return (self.x0 + self.y0) * CELL_DY - self.rise

    @property
    def bottom(self) -> int:
        return (self.x1 + self.y1 + 2) * CELL_DY + self.drop

    @property
    def native_size(self):
        return self.right - self.left, self.bottom - self.top

    @property
    def size(self):
        w, h = self.native_size
        return max(1, int(round(w * self.scale))), max(1, int(round(h * self.scale)))

    def native_px(self, cx: float, cy: float):
        """Native pixel (in the frame) of the ground point at cell coordinates (cx, cy) (fractions allowed)."""
        return (cx - cy) * CELL_DX - self.left, (cx + cy) * CELL_DY - self.top

    def px(self, cx: float, cy: float):
        nx, ny = self.native_px(cx, cy)
        return nx * self.scale, ny * self.scale

    def cell_at(self, px: float, py: float):
        """Cell coordinates (fractional) of the ground point under output pixel (px, py)."""
        nx = px / self.scale + self.left
        ny = py / self.scale + self.top
        a = nx / CELL_DX          # x - y
        b = ny / CELL_DY          # x + y
        return (a + b) / 2.0, (b - a) / 2.0

    def near(self, cx: float, cy: float, side: float = 3.0, below: float = 12.0, reach: float = 0.0) -> bool:
        """Whether something standing at cell (cx, cy) can show in the frame: its ground point (with `reach` > 0 the
        corners of the reach x reach cells from it, a merged chunk) within the frame widened by `side` cells to the
        sides and above and `below` cells below (a tall piece standing below the frame reaches up into it). On the
        screen, not in a box of cells: a crop's rectangle covers cells far outside its own cell range."""
        pts = [(cx + a, cy + b) for a in (0.0, reach) for b in (0.0, reach)] if reach else [(cx, cy)]
        xs = [(a - b) * CELL_DX for a, b in pts]
        ys = [(a + b) * CELL_DY for a, b in pts]
        return not (max(xs) < self.left - side * 2 * CELL_DX or min(xs) > self.right + side * 2 * CELL_DX
                    or max(ys) < self.top - side * 2 * CELL_DY or min(ys) > self.bottom + below * 2 * CELL_DY)

    def hd_scale(self) -> float:
        return self.scale * HD_PER_CLASSIC

    def hd_origin(self):
        """Output pixel of the HD world origin (cell corner 0, 0)."""
        return self.px(0, 0)

    def as_dict(self) -> dict:
        w, h = self.size
        ox, oy = self.px(0, 0)
        return {"cells": [self.x0, self.y0, self.x1, self.y1], "scale": self.scale, "rise": self.rise, "drop": self.drop,
                "size": [w, h], "native_rect": [self.left, self.top, self.right, self.bottom],
                "origin_px": [ox, oy], "cell_step_px": {"x": [CELL_DX * self.scale, CELL_DY * self.scale],
                                                        "y": [-CELL_DX * self.scale, CELL_DY * self.scale]},
                "hd_scale": self.hd_scale(),
                "pixel_of_cell": "px = origin_px + cx * cell_step_px.x + cy * cell_step_px.y (ground, cell corner)"}


def parse_cells(spec: str | None, width: int, height: int):
    """'x0,y0,x1,y1' (inclusive; negative counts from the end) or None for the whole map -> clamped (x0, y0, x1, y1)."""
    if not spec:
        return 0, 0, width - 1, height - 1
    v = [int(s) for s in str(spec).replace(":", ",").split(",")]
    if len(v) == 2:
        v = v + v
    if len(v) != 4:
        raise ValueError("cells: x0,y0,x1,y1")
    x0, y0, x1, y1 = [(a + n if a < 0 else a) for a, n in zip(v, (width, height, width, height))]
    x0, x1 = sorted((max(0, min(width - 1, x0)), max(0, min(width - 1, x1))))
    y0, y1 = sorted((max(0, min(height - 1, y0)), max(0, min(height - 1, y1))))
    return x0, y0, x1, y1
