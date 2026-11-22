"""hdkit.view: an offline viewer and renderer for D2R's HD art (`python -m hdkit.view ...`).

  vfs.py      a logical game path resolved over a list of local roots, with the root that answered
  camera.py   the game's orthographic camera, pixel <-> world maths, tile sub-frusta
  tiling.py   tile plans, a streamed PNG writer for images larger than one GPU texture, seam checks
  gr2.py      models, skeletons, clips (the curve kinds hdkit can decode), poses and skinning on the CPU
  scene.py    a unit JSON (or a bare model, or a classic sprite card) as render entities
  gpu.py      the WebGPU device (wgpu-py), the probe and the renderer
  metrics.py  per-render measures (on-screen height, luminance, histogram, alpha coverage, texels per pixel)
  tone.py     the game's tone chain as far as it is known (x0.008, PQ, EETF; no grading LUT)
  rig.py      light rigs (light, exposure, tone) as JSON; presets `default` and `game`, or built from an env/vis file
  sheets.py   contact sheets, GIF/APNG turntables, the file watcher of `watch`
  assets.py   what the roots hold: units, models, a unit's clips; which root answers a path
  compare.py  a render against a game capture: unit mask from a twin shot, IoU with shift, luma, cap colour
  cli.py      the command line: render, sheet, turntable, watch, rig, ls, resolve, camera, compare, gate
  mcp_server.py   the same commands as a local stdio MCP server (needs the `mcp` package; nothing else imports it)
Large outputs can move into a content store by hash (hdkit/store.py, `--store-min-mb`).
"""
