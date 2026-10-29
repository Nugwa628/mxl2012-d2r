"""Bone table of a D2R .skeleton: name, parent, bind-pose world position (from InverseWorldTransform).

    skel_info.py <file.skeleton> [out.json]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import d2r_model as dm  # noqa: E402


def bones(path):
    g = dm.Gr2File.read(Path(path).read_bytes())
    tree = dm.parse_tree(g)
    sk = tree["Skeletons"][0]
    out = []
    for i, b in enumerate(sk["Bones"]):
        inv = np.array(b["InverseWorldTransform"], float).reshape(4, 4)
        w = np.linalg.inv(inv)  # row vectors: translation in row 3
        out.append(dict(i=i, name=b["Name"], parent=int(b["ParentIndex"]), pos=[float(x) for x in w[3, :3]],
                        world=[[float(x) for x in r] for r in w]))
    return out


if __name__ == "__main__":
    bs = bones(sys.argv[1])
    if len(sys.argv) > 2:
        json.dump(bs, open(sys.argv[2], "w"))
    for b in bs:
        print("%3d %-34s p%3d  % .2f % .2f % .2f" % (b["i"], b["name"], b["parent"], *b["pos"]))
