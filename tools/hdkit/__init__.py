"""hdkit: a general library for D2R's HD art (models, skeletons, clips, textures, cards) and their offline rendering.

The package holds code only: no game art, no mod-specific rules. Paths to game files come from the caller (a list of local
roots, see `hdkit.view.vfs`); site rules (which lock folders mean "the GPU is busy") come from an optional adapter module
`hdkit_site` beside the package, so the library can move to its own repository unchanged.

  hdkit.gpugate   may a GPU job run now: lock folders and GPU and CPU load (Windows counters, Linux amdgpu sysfs and load average)
  hdkit.view      the offline viewer and renderer (`python -m hdkit.view render ...`)
"""
