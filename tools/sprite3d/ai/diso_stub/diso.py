"""Stand-in for the CUDA-only `diso` package TripoSG imports. The hierarchical (skimage marching cubes) decoder does not
use it: run the pipeline with use_flash_decoder=False."""


class DiffDMC:
    def __init__(self, *a, **k):
        raise RuntimeError("diso is not available here: run TripoSG with use_flash_decoder=False")
