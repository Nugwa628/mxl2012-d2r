"""Contact sheets, turntable files and the watch loop of hdkit.view (CPU only; the renders come from gpu.Renderer).

  grid(cells, cols, ...)       labelled contact sheet of equally sized RGBA cells (rows x columns: e.g. modes x facings,
                               passes x facings, turntable frames), composited over a background
  write_anim(frames, path)     GIF or APNG (Pillow) or MP4 (H.264 through the ffmpeg of the imageio-ffmpeg package, a
                               local tool in the venv: owner decision 2) of RGBA frames, by the file extension
  Watcher(paths)               mtime and size snapshot of input files; `changed()` lists those that changed since the
                               last call; `watch(run, paths_of, ...)` polls and re-runs (no watchdog download: polling
                               every `every` seconds is enough for single files)

Layout helpers reuse the shape of the earlier owner sheets (title line, label strip above each cell, dark background).
"""
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = (16, 17, 20)


def font(size=13):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                       # Pillow < 10.1
        return ImageFont.load_default()


def over(rgba: np.ndarray, bg=BG) -> np.ndarray:
    """Straight-alpha RGBA over a flat sRGB colour (display-space blend, for sheets only)."""
    a = rgba[..., 3:4].astype(float) / 255.0
    return np.round(rgba[..., :3].astype(float) * a + np.asarray(bg, float) * (1 - a)).astype(np.uint8)


def grid(cells, cols: int, labels=None, row_labels=None, col_labels=None, title=None, pad=4, label_h=16, bg=BG,
         cell_bg=(30, 32, 38)) -> Image.Image:
    """cells: list of (h, w, 3|4) uint8 arrays (None = empty), row-major. Returns an RGB sheet."""
    cells = list(cells)
    h = max(c.shape[0] for c in cells if c is not None)
    w = max(c.shape[1] for c in cells if c is not None)
    rows = -(-len(cells) // cols)
    left = 0 if not row_labels else 90
    top = (24 if title else 0) + (label_h if col_labels else 0)
    W = left + cols * (w + pad) + pad
    H = top + rows * (h + pad + (label_h if labels else 0)) + pad
    sheet = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(sheet)
    f = font(13)
    if title:
        d.text((pad, 4), title, fill=(255, 255, 255), font=font(15))
    if col_labels:
        for c, t in enumerate(col_labels):
            d.text((left + pad + c * (w + pad), top - label_h + 1), str(t), fill=(255, 230, 140), font=f)
    for i, c in enumerate(cells):
        r, k = divmod(i, cols)
        x = left + pad + k * (w + pad)
        y = top + pad + r * (h + pad + (label_h if labels else 0))
        if labels:
            d.text((x + 2, y), str(labels[i])[:48], fill=(220, 220, 220), font=f)
            y += label_h
        if c is None:
            continue
        img = over(c, cell_bg) if c.shape[-1] == 4 else c[..., :3]
        sheet.paste(Image.fromarray(img), (x + (w - c.shape[1]) // 2, y + (h - c.shape[0]) // 2))
    if row_labels:
        for r, t in enumerate(row_labels):
            y = top + pad + r * (h + pad + (label_h if labels else 0)) + h // 2
            d.text((4, y), str(t)[:12], fill=(255, 230, 140), font=f)
    return sheet


def write_anim(frames, path, fps: float = 25.0, bg=BG) -> Path:
    """GIF (frames over `bg`, adaptive palette) or APNG (straight alpha kept) by the file extension."""
    p = Path(path)
    ext = p.suffix.lower()
    ms = int(round(1000.0 / fps))
    if ext == ".gif":
        ims = [Image.fromarray(over(f, bg) if f.shape[-1] == 4 else f).convert("P", palette=Image.ADAPTIVE)
               for f in frames]
        ims[0].save(p, save_all=True, append_images=ims[1:], duration=ms, loop=0, disposal=2)
    elif ext in (".png", ".apng"):
        ims = [Image.fromarray(f) for f in frames]
        ims[0].save(p, format="PNG", save_all=True, append_images=ims[1:], duration=ms, loop=0, disposal=1, blend=0)
    elif ext == ".mp4":
        write_mp4(frames, p, fps, bg)
    else:
        raise ValueError("turntable format: .gif, .png/.apng or .mp4")
    return p


def ffmpeg_exe() -> str:
    """The ffmpeg binary of imageio-ffmpeg (installed in the project venv only; GPL build, a local tool never shipped)."""
    try:
        import imageio_ffmpeg
    except ImportError as e:
        raise RuntimeError("MP4 needs the imageio-ffmpeg package in this Python (pip install imageio-ffmpeg in the venv)") from e
    return imageio_ffmpeg.get_ffmpeg_exe()


def write_mp4(frames, path, fps: float = 25.0, bg=BG) -> Path:
    """H.264 MP4 (yuv420p, CRF 18) of frames composited over `bg`; odd sizes are padded to even with `bg`."""
    import subprocess
    fr = [over(f, bg) if f.shape[-1] == 4 else np.ascontiguousarray(f[..., :3]) for f in frames]
    h, w = fr[0].shape[:2]
    H, W = h + (h & 1), w + (w & 1)
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", "%g" % fps, "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
           "-movflags", "+faststart", str(path)]
    buf = np.empty((H, W, 3), np.uint8)
    buf[:] = np.array(bg[:3], np.uint8)
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in fr:
            buf[:h, :w] = f
            pr.stdin.write(buf.tobytes())
    finally:
        err = pr.communicate()[1].decode("utf-8", "replace")
    rc = pr.returncode
    if rc:
        raise RuntimeError("ffmpeg failed (%d): %s" % (rc, err.strip()[-400:]))
    return Path(path)


def turntable_yaws(n: int, start: float = 0.0) -> list:
    """n model yaws over one full turn, clockwise on screen (decreasing yaw, as facing_yaw's sign -1)."""
    return [start - 360.0 * i / n for i in range(n)]


class Watcher:
    def __init__(self, paths=()):
        self.snap = {}
        self.set(paths)

    @staticmethod
    def _stat(p):
        try:
            st = os.stat(p)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def set(self, paths):
        self.snap = {str(p): self._stat(p) for p in paths}

    def changed(self) -> list:
        out = []
        for p, old in self.snap.items():
            new = self._stat(p)
            if new != old:
                out.append(p)
                self.snap[p] = new
        return out


def watch(run, paths_of, every: float = 1.0, max_runs: int | None = None, idle_exit: float | None = None, log=print,
          sleep=time.sleep) -> int:
    """Run `run()` once, then again whenever a file of `paths_of()` (re-read after each run, so new inputs are watched)
    changes. Stops after `max_runs` runs or `idle_exit` seconds without a change. Returns the number of runs."""
    runs = 0
    w = Watcher()
    last = time.time()
    while True:
        try:
            run()
        except Exception as e:  # noqa: BLE001  a broken input must not end the watch
            log("render failed: %r" % (e,))
        runs += 1
        w.set(paths_of())
        log("watching %d files" % len(w.snap))
        if max_runs is not None and runs >= max_runs:
            return runs
        while True:
            sleep(every)
            ch = w.changed()
            if ch:
                log("changed: %s" % ", ".join(Path(c).name for c in ch))
                last = time.time()
                break
            if idle_exit is not None and time.time() - last > idle_exit:
                return runs
