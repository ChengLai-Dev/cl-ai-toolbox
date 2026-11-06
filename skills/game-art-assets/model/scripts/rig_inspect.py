"""Blender 端骨骼资产体检。

用法:
    blender.exe -b --factory-startup --python rig_inspect.py -- <asset.glb|asset.fbx>

检查三项（缺一不可）:
    1. bind pose 是否在原点    —— 脚底应在 z≈0，否则 UE 里会整体偏移
    2. 脚骨是否挂在小腿下      —— 挂在 Root 会让脚被拉成长尖刺
    3. 动画是否真的有运动      —— 全帧包围盒不变 = 动画是静止的

结果同时打印并写到 <asset>_inspect.txt
"""

import sys
import os

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    if not argv:
        raise SystemExit("usage: -- <asset.glb|asset.fbx>")
    return argv[0]


def world_bbox(objs):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        mw = ev.matrix_world
        pts.extend(mw @ v.co for v in me.vertices)
        ev.to_mesh_clear()
    if not pts:
        return None
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def skinned_meshes():
    out = [o for o in bpy.data.objects
           if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    return out or [o for o in bpy.data.objects if o.type == "MESH"]


def main():
    path = parse_args()
    report = []

    def log(s):
        print(s)
        report.append(s)

    log("FILE " + path)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    if path.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)

    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    meshes = skinned_meshes()
    log("MESHES %d  ARMATURE %s" % (len(meshes), arm.name if arm else None))
    if arm is None:
        log("NO_ARMATURE  这个资产没有骨骼，不适用本检查")
        return

    log("BONES %d" % len(arm.data.bones))
    if arm.animation_data:
        arm.animation_data.action = None

    # ---------- 1. bind pose ----------
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    bb = world_bbox(meshes)
    height = bb[5] - bb[4]
    log("REST_BBOX x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f]"
        % (bb[0], bb[1], bb[2], bb[3], bb[4], bb[5]))
    log("REST_HEIGHT %.3f" % height)
    if abs(bb[4]) > 0.05:
        log("FAIL bind pose 不在原点：脚底 z = %.3f，UE 里会整体偏移 %.2fm"
            % (bb[4], abs(bb[4])))
    else:
        log("OK   bind pose 在原点")

    # ---------- 2. 脚骨层级 ----------
    suspects = []
    for b in arm.data.bones:
        low = b.name.lower()
        if ("foot" in low or "toe" in low or low.startswith("pt")):
            parent = b.parent.name if b.parent else None
            log("BONE %-12s -> %s" % (b.name, parent))
            if parent and parent.lower() in ("root", "armature", "body"):
                suspects.append(b.name)
    if suspects:
        log("FAIL 脚骨挂错父级：%s（应为 LowerLeg/LeftLeg 的子级）" % suspects)
    else:
        log("OK   脚骨层级正常")

    # ---------- 3. 动画运动 ----------
    arm.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    actions = [a for a in bpy.data.actions]
    log("ACTIONS %d" % len(actions))

    if arm.animation_data is None:
        arm.animation_data_create()

    preview = actions[:5]
    for act in preview:
        arm.animation_data.action = act
        start, end = [int(round(v)) for v in act.frame_range]
        frames = sorted({start, (start + end) // 2, end})
        boxes = []
        for f in frames:
            bpy.context.scene.frame_set(f)
            bpy.context.view_layer.update()
            boxes.append(world_bbox(meshes))
        span = max(
            max(abs(boxes[i][k] - boxes[0][k]) for k in range(6))
            for i in range(len(boxes))
        )
        status = "OK  " if span > 0.005 else "FAIL"
        log("%s %-42s frames %d-%d  最大位移 %.4f m"
            % (status, act.name[-40:], start, end, span))

    if len(preview) < len(actions):
        log("... 其余 %d 段未检查" % (len(actions) - len(preview)))

    out = os.path.splitext(path)[0] + "_inspect.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    log("REPORT " + out)


main()
