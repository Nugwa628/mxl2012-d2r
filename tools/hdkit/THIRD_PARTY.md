# Third-party code and tools in hdkit

This list moves with `hdkit/` (the HD model viewer, its browser page, the CASC cache, the sign-off wrapper and the
MCP server). Every entry is MIT-compatible. Add an entry whenever code from elsewhere is ported or bundled.

## Ported code (`view/`)

No third-party file is copied; these parts are written after the named sources, all MIT:

- Granny curve decoding (`view/curves.py`): ported from LSLib, Copyright (c) 2015 Norbyte, MIT,
  <https://github.com/Norbyte/lslib> @6f5f698 (`LSLib/Granny/Model/CurveData`).
- Pose and skinning rules (`view/gr2.py`): after Reimagined Level Editor, MIT, @3f76c75.
- COF layer order and blend rules (`view/classic.py`): after Reimagined D2R Mod Studio, MIT, @ea1a969 (`Cof.cs`).
- Cross-checks only, no code taken: aamt by Hellcommander (MIT, @a58bb5d, `Tools/DiabloII/GrannyAnim.py`),
  carbonenginejs tools-blender (MIT, @c97d43b, `carbon_gr2/curves.py`), rasen by rasenjs (MIT, @d2e115a).

## Libraries used at run time, not bundled

- CascLib by Ladislav Zezula (MIT), <https://github.com/ladislav-zezula/CascLib>: reads the game's CASC storage
  for `view/casc.py`. Loaded through the host project's site adapter; hdkit ships no CascLib binary.
- imageio-ffmpeg (BSD-2-Clause wrapper) for MP4 output in `view/sheets.py`. The ffmpeg binary it fetches is a GPL
  build: a local tool in the user's own venv, never shipped with hdkit.
- numpy (BSD-3-Clause), Pillow (MIT-CMU), wgpu-py (BSD-2-Clause): ordinary pip dependencies.

## Analysis tools, never shipped

- The game shaders were read with Microsoft's `D3DDisassemble` (d3dcompiler_47.dll, a Windows system DLL) called
  through ctypes; no binary is bundled. The colour path in `view/tone.py` (`lut_chain`, `value_curve`, `bloom`) is
  written from that disassembly. Its constants are the game's. The ACES-style matrices (sRGB/AP1/BT.2020, gamut
  expansion) are the standard published values that Unreal Engine 4's tone path also uses; no UE4 code was taken.
- capstone 5.0.7 (BSD-3-Clause, <https://github.com/capstone-engine/capstone>) was used in a local venv to search the
  game executable for where the constants are filled. It is not an hdkit dependency.
