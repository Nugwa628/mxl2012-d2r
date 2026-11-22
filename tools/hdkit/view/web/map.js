// Map viewer page (hdkit.view.mapview.webmap): whole-map classic / HD images from the local server, pan / zoom, cell info,
// region screenshots and renders. Cell maths: the frame of /api/info (frame.py): ground point (cx, cy) of the map sits at
// image pixel ((cx - cy) * 80 - L, (cx + cy) * 40 - T) * scale.
"use strict";
const $ = (id) => document.getElementById(id);
const cv = $("cv"), ctx = cv.getContext("2d");
const S = { info: null, frame: null, img: {}, view: { s: 1, tx: 0, ty: 0 }, sel: null, cell: null, drag: null };

function q(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, v);
  return p.toString();
}
function base() { return { map: $("map").value.trim(), source: $("source").value, work: $("work").value.trim() }; }
function status(t) { $("status").textContent = t; }
function mode() { return document.querySelector("input[name=mode]:checked").value; }

// ---- frame maths ------------------------------------------------------------------------------------------------------
function cellPx(cx, cy) {
  const f = S.frame, [L, T] = f.native_rect;
  return [((cx - cy) * 80 - L) * f.scale, ((cx + cy) * 40 - T) * f.scale];
}
function cellAt(ix, iy) {
  const f = S.frame, [L, T] = f.native_rect;
  const a = (ix / f.scale + L) / 80, b = (iy / f.scale + T) / 40;
  return [(a + b) / 2, (b - a) / 2];
}
const toImg = (x, y) => [(x - S.view.tx) / S.view.s, (y - S.view.ty) / S.view.s];
const toScr = (x, y) => [x * S.view.s + S.view.tx, y * S.view.s + S.view.ty];

// ---- loading ----------------------------------------------------------------------------------------------------------
async function json(url) {
  const r = await fetch(url);
  const d = await r.json();
  if (!r.ok || d.error) throw new Error(d.error || r.statusText);
  return d;
}
function loadImg(kind) {
  const b = base();
  const layers = kind === "classic" ? $("clayers").value.trim() : "";
  const url = "/api/image?" + q({ ...b, kind, scale: S.info.base_scale, layers });
  if (S.img[kind] && S.img[kind].url === url) return S.img[kind].p;
  const im = new Image();
  const p = new Promise((ok, bad) => { im.onload = () => ok(im); im.onerror = () => bad(new Error(kind + " render failed")); });
  im.src = url;
  S.img[kind] = { url, im, p, ready: false };
  status("rendering " + kind + " (the first time can take a while)...");
  p.then(() => { S.img[kind].ready = true; status(kind + " ready"); draw(); }).catch((e) => status(e.message));
  return p;
}
async function load() {
  const b = base();
  if (!b.map) return status("type a map path");
  status("loading " + b.map + "...");
  try {
    S.info = await json("/api/info?" + q(b));
  } catch (e) { return status(e.message); }
  S.frame = S.info.frame; S.img = {}; S.sel = null; S.cell = null;
  const lv = (S.info.levels || []).map((l) => l.level + " " + l.level_name + " (" + l.level_type + ")").join("; ");
  $("mapinfo").textContent = `${S.info.map} [${S.info.source}]  ${S.info.size_cells.join("x")} cells, act ${S.info.act}\n` +
    `levels: ${lv || "none"}\nobjects: ${S.info.objects}  walls ${S.info.wall_layers} floors ${S.info.floor_layers}\n` +
    `base scale ${S.info.base_scale}` + (S.info.notes.length ? "\n" + S.info.notes.join("\n") : "");
  history.replaceState(null, "", "?" + q(b));
  fit();
  loadImg("classic");
  if (mode() !== "classic") loadImg("hd");
}
function fit() {
  if (!S.frame) return;
  const [w, h] = S.frame.size, W = cv.width, H = cv.height;
  const s = Math.min(W / w, H / h) * 0.95;
  S.view = { s, tx: (W - w * s) / 2, ty: (H - h * s) / 2 };
  draw();
}

// ---- drawing ----------------------------------------------------------------------------------------------------------
function resize() {
  const r = cv.getBoundingClientRect();
  cv.width = Math.max(1, r.width | 0); cv.height = Math.max(1, r.height | 0);
  draw();
}
function diamond(x0, y0, x1, y1) {
  const pts = [cellPx(x0, y0), cellPx(x1, y0), cellPx(x1, y1), cellPx(x0, y1)].map(([x, y]) => toScr(x, y));
  ctx.beginPath(); ctx.moveTo(...pts[0]); for (const p of pts.slice(1)) ctx.lineTo(...p); ctx.closePath();
}
function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#0c0c0e"; ctx.fillRect(0, 0, cv.width, cv.height);
  if (!S.frame) return;
  const m = mode();
  ctx.imageSmoothingEnabled = S.view.s < 1;
  ctx.setTransform(S.view.s, 0, 0, S.view.s, S.view.tx, S.view.ty);
  const c = S.img.classic, h = S.img.hd;
  if ((m === "classic" || m === "overlay") && c && c.ready) ctx.drawImage(c.im, 0, 0);
  if ((m === "hd" || m === "overlay") && h && h.ready) {
    ctx.globalAlpha = m === "overlay" ? $("alpha").value / 100 : 1;
    ctx.drawImage(h.im, 0, 0);
    ctx.globalAlpha = 1;
  }
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const [W, H] = S.info.size_cells;
  if ($("grid").checked) {
    ctx.strokeStyle = "rgba(255,255,255,0.18)"; ctx.lineWidth = 1;
    const step = S.view.s * S.frame.scale * 80 < 6 ? 5 : 1;
    ctx.beginPath();
    for (let x = 0; x <= W; x += step) { ctx.moveTo(...toScr(...cellPx(x, 0))); ctx.lineTo(...toScr(...cellPx(x, H))); }
    for (let y = 0; y <= H; y += step) { ctx.moveTo(...toScr(...cellPx(0, y))); ctx.lineTo(...toScr(...cellPx(W, y))); }
    ctx.stroke();
  }
  if (S.cell) {
    diamond(S.cell[0], S.cell[1], S.cell[0] + 1, S.cell[1] + 1);
    ctx.strokeStyle = "#ffd54a"; ctx.lineWidth = 2; ctx.stroke();
  }
  if (S.sel) {
    const [x0, y0, x1, y1] = S.sel;
    diamond(x0, y0, x1 + 1, y1 + 1);
    ctx.fillStyle = "rgba(80,160,255,0.15)"; ctx.fill();
    ctx.strokeStyle = "#5aa0ff"; ctx.lineWidth = 2; ctx.stroke();
  }
}

// ---- input ------------------------------------------------------------------------------------------------------------
function cellUnder(e) {
  const r = cv.getBoundingClientRect();
  const [ix, iy] = toImg(e.clientX - r.left, e.clientY - r.top);
  const [cx, cy] = cellAt(ix, iy);
  return [Math.floor(cx), Math.floor(cy)];
}
function clampCell([x, y]) {
  const [W, H] = S.info.size_cells;
  return [Math.max(0, Math.min(W - 1, x)), Math.max(0, Math.min(H - 1, y))];
}
cv.addEventListener("mousedown", (e) => {
  if (!S.frame) return;
  S.drag = { x: e.clientX, y: e.clientY, tx: S.view.tx, ty: S.view.ty, moved: false, sel: e.shiftKey, c0: cellUnder(e) };
});
window.addEventListener("mousemove", (e) => {
  const d = S.drag;
  if (!d) return;
  if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
  if (d.sel) {
    const a = clampCell(d.c0), b = clampCell(cellUnder(e));
    S.sel = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
    $("region").textContent = "cells " + S.sel.join(",") + `  (${S.sel[2] - S.sel[0] + 1} x ${S.sel[3] - S.sel[1] + 1})`;
  } else {
    S.view.tx = d.tx + e.clientX - d.x; S.view.ty = d.ty + e.clientY - d.y;
  }
  draw();
});
window.addEventListener("mouseup", (e) => {
  const d = S.drag; S.drag = null;
  if (!d || d.moved || d.sel) return;
  const c = cellUnder(e), [W, H] = S.info.size_cells;
  if (c[0] < 0 || c[1] < 0 || c[0] >= W || c[1] >= H) return;
  showCell(c);
});
cv.addEventListener("wheel", (e) => {
  e.preventDefault();
  const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const k = Math.exp(-e.deltaY * 0.0015), [ix, iy] = toImg(mx, my);
  S.view.s = Math.min(16, Math.max(0.02, S.view.s * k));
  S.view.tx = mx - ix * S.view.s; S.view.ty = my - iy * S.view.s;
  draw();
}, { passive: false });

async function showCell(c) {
  S.cell = c; draw();
  $("cellsum").textContent = "cell " + c.join(",") + " ...";
  try {
    const d = await json("/api/cell?" + q({ ...base(), x: c[0], y: c[1], near: 0.5 }));
    const cl = d.classic, lines = [`cell ${c.join(",")}  sub-tiles ${d.subtiles.join(",")}  world ${d.hd_world_box.join(",")}`];
    for (const f of cl.floors) lines.push(`floor${f.layer}: ${f.raw_hex} style ${f.style} seq ${f.sequence}` +
      (f.tile ? `  ${f.tile.dt1} #${f.tile.index_in_dt1} (${f.tile.variants} var)` : f.dword ? "  MISSING" : ""));
    for (const w of cl.walls) if (w.dword) lines.push(`wall${w.layer}: ${w.raw_hex} o${w.orientation} style ${w.style} seq ${w.sequence}` +
      (w.tile ? `  ${w.tile.dt1} (${w.tile.orientation_name})` : "  MISSING"));
    if (cl.shadow.dword) lines.push(`shadow: ${cl.shadow.raw_hex}`);
    lines.push(`blocked sub-tiles: ${cl.walk.blocked_subtiles}/25`);
    for (const o of cl.objects) lines.push(`object [${o.index}] type ${o.type} id ${o.id} @${o.x},${o.y}: ${o.name}`);
    const hd = d.hd || {};
    if (hd.error) lines.push("HD: " + hd.error);
    else {
      lines.push(`HD preset: ${hd.preset || "none"}; ${hd.entities.length} entities on/near`);
      for (const e of hd.entities.slice(0, 30)) lines.push(`  [${e.index}] ${e.name}${e.wall ? " (wall)" : ""} ` +
        (e.model || e.prefab || e.components.join(" ")).split("/").pop());
    }
    $("cellsum").innerHTML = "";
    const pre = document.createElement("pre"); pre.textContent = lines.join("\n"); $("cellsum").appendChild(pre);
    $("cellraw").textContent = JSON.stringify(d, null, 1);
  } catch (e) { $("cellsum").textContent = e.message; }
}

function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
$("shot").onclick = () => {
  if (!S.sel) return status("select a region first (shift+drag)");
  // the region's bounding box in image pixels (ground diamond, plus the frame's rise above it), drawn as shown now
  const [x0, y0, x1, y1] = S.sel, f = S.frame;
  const pts = [cellPx(x0, y0), cellPx(x1 + 1, y0), cellPx(x1 + 1, y1 + 1), cellPx(x0, y1 + 1)];
  const L = Math.min(...pts.map((p) => p[0])), R = Math.max(...pts.map((p) => p[0]));
  const T = Math.min(...pts.map((p) => p[1])) - f.rise * f.scale, B = Math.max(...pts.map((p) => p[1])) + f.drop * f.scale;
  const out = document.createElement("canvas");
  out.width = Math.max(1, Math.round(R - L)); out.height = Math.max(1, Math.round(B - T));
  const o = out.getContext("2d"), m = mode();
  o.fillStyle = "#000"; o.fillRect(0, 0, out.width, out.height);
  if ((m !== "hd") && S.img.classic && S.img.classic.ready) o.drawImage(S.img.classic.im, -L, -T);
  if ((m !== "classic") && S.img.hd && S.img.hd.ready) {
    o.globalAlpha = m === "overlay" ? $("alpha").value / 100 : 1; o.drawImage(S.img.hd.im, -L, -T); o.globalAlpha = 1;
  }
  out.toBlob((b) => download(b, `${S.info.map.replace(/\//g, "_")}_${m}_c${S.sel.join("_")}.png`));
};
$("render").onclick = () => {
  if (!S.sel) return status("select a region first (shift+drag)");
  const kind = $("rkind").value;
  const url = "/api/region?" + q({ ...base(), kind, cells: S.sel.join(","), scale: $("rscale").value,
                                   layers: kind === "classic" ? $("clayers").value.trim() : "" });
  $("rlink").innerHTML = "";
  const a = document.createElement("a"); a.href = url; a.target = "_blank";
  a.textContent = `open ${kind} render (cells ${S.sel.join(",")})`;
  a.style.color = "#8fc0ff"; $("rlink").appendChild(a);
  window.open(url, "_blank");
};

for (const r of document.querySelectorAll("input[name=mode]")) {
  r.onchange = () => { if (S.info && mode() !== "classic") loadImg("hd"); draw(); };
}
$("alpha").oninput = draw; $("grid").onchange = draw;
$("clayers").onchange = () => { if (S.info) loadImg("classic"); };
$("load").onclick = load; $("fit").onclick = fit;
$("map").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
window.addEventListener("resize", resize);

(async function init() {
  resize();
  const u = new URLSearchParams(location.search);
  try {
    const [m, d] = await Promise.all([json("/api/maps?source=mod"), json("/api/maps?source=d2r")]);
    const dl = $("maps");
    for (const k of m.maps) { const o = document.createElement("option"); o.value = k; o.label = "mod"; dl.appendChild(o); }
    for (const k of d.maps) { const o = document.createElement("option"); o.value = k; o.label = "d2r"; dl.appendChild(o); }
    $("map").value = u.get("map") || (m.default && m.default.map) || "";
    $("source").value = u.get("source") || (m.default && m.default.source) || "auto";
    $("work").value = u.get("work") || "";
  } catch (e) { status(e.message); }
  if ($("map").value) load();
})();
