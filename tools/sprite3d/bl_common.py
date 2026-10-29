"""Helpers shared by the Blender (headless) scripts of the Wereowl mesh lane: numpy <-> Blender meshes, Cycles setup.

Meshes live in the build's own model space (y up, +z front, a standing figure); Blender is only a geometry engine here, nothing
is rotated into its z-up world, so every array that goes in comes out in the same axes. UVs are D2R's (v runs down the image);
Blender's v is 1 - v, and a Blender image row 0 is the bottom row, so a saved image is np.flipud of `image_array`.
"""
import bpy
import numpy as np


def mesh_object(name, pos, tris, uv=None, nrm=None):
    """Object from arrays: pos (N,3), tris (M,3); uv (N,2) per vertex (D2R v) becomes the UV layer `UVMap`; nrm (N,3) are set as
    custom split normals (the vertex normals the game mesh carries), so a bake sees the shading the engine draws."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(pos, np.float64).tolist(), [], np.asarray(tris, np.int64).tolist())
    me.update()
    if uv is not None:
        layer = me.uv_layers.new(name="UVMap")
        t = np.asarray(tris, np.int64).reshape(-1)
        c = np.asarray(uv, np.float64)[t].copy()
        c[:, 1] = 1.0 - c[:, 1]
        layer.data.foreach_set("uv", c.reshape(-1).astype(np.float32))
    for p in me.polygons:
        p.use_smooth = True
    if nrm is not None:
        me.normals_split_custom_set_from_vertices(np.asarray(nrm, np.float64).tolist())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def arrays(ob):
    """(pos (N,3), tris (M,3)) of an object (polygons are triangulated)."""
    me = ob.data
    pos = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", pos)
    me.calc_loop_triangles()
    tris = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tris)
    return pos.reshape(-1, 3), tris.reshape(-1, 3)


def select_only(*obs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or obs[0]


def cycles(samples=1, gpu=True):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    dev = "CPU"
    if gpu:
        try:
            pr = bpy.context.preferences.addons["cycles"].preferences
            for kind in ("HIP", "OPTIX", "CUDA"):
                try:
                    pr.compute_device_type = kind
                    pr.get_devices()
                    if any(d.type == kind for d in pr.devices):
                        for d in pr.devices:
                            d.use = d.type == kind
                        dev = "GPU"
                        break
                except Exception:
                    continue
        except Exception:
            pass
    sc.cycles.device = dev
    return dev


def image_target(ob, name, size, float_buffer=True, color=(0, 0, 0, 1)):
    """A material with an active image node on `ob` (what the bake writes into); returns the image."""
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=float_buffer)
    img.colorspace_settings.name = "Non-Color"
    img.generated_color = color
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.nodes.active = tex
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    return img


def image_array(img):
    """(H, W, 4) float32, Blender's row order (row 0 = bottom)."""
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def emission_material(name, color_socket_builder):
    """Material whose surface is an Emission of the node returned by `color_socket_builder(nodes)` (an output socket)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(color_socket_builder(nt.nodes), em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def bake(kind, hi, lo, extrude, ray, margin=24, normal_space="TANGENT"):
    sc = bpy.context.scene
    b = sc.render.bake
    b.use_selected_to_active = hi is not None
    b.cage_extrusion = extrude
    b.max_ray_distance = ray
    b.margin = margin
    b.margin_type = "EXTEND"
    b.use_clear = True
    b.normal_space = normal_space
    b.normal_r, b.normal_g, b.normal_b = "POS_X", "POS_Y", "POS_Z"
    if hi is not None:
        select_only(hi, lo, active=lo)
    else:
        select_only(lo)
    bpy.ops.object.bake(type=kind)
