"""Blender 端 glTF -> FBX 转换（给 UE 用）。

用法:
    blender.exe -b --factory-startup --python glb2fbx.py -- ^
        <in.glb> <out.fbx> [--height 1.8]

做的事:
    1. 删掉无关网格（poly.pizza 的 glTF 常带一个 Icosphere，会撑大包围盒）
    2. 删掉所有 EMPTY（glTF 导入产生的骨骼尾端辅助节点）
    3. 合并全部蒙皮网格（否则 UE 会拆成多个 SkeletalMesh）
    4. 用求值后的世界包围盒量身高，按 --height 归一化
    5. ★ 导出前把 pose_position 复位成 POSE ★

第 5 步漏掉的话，24 段动画会全部变成静止姿势，但长度正常——
表现为「动画有时间轴但人物一动不动」，极难排查。
"""

import sys
import os

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    if len(argv) < 2:
        raise SystemExit("usage: -- <in.glb> <out.fbx> [--height 1.8]")
    src, dst = argv[0], argv[1]
    height = 1.8
    if "--height" in argv:
        height = float(argv[argv.index("--height") + 1])
    return src, dst, height


def skinned_meshes():
    out = [o for o in bpy.data.objects
           if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    return out or [o for o in bpy.data.objects if o.type == "MESH"]


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
    zs = [p.z for p in pts]
    return min(zs), max(zs)


def main():
    src, dst, target_h = parse_args()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)

    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    keep = skinned_meshes()

    # 1 + 2: 清理
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o, do_unlink=True)
        elif o.type == "MESH" and o not in keep:
            print("DROP_MESH", o.name)
            bpy.data.objects.remove(o, do_unlink=True)

    # 3: 合并
    if len(keep) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for m in keep:
            m.select_set(True)
        bpy.context.view_layer.objects.active = keep[0]
        bpy.ops.object.join()
        body = bpy.context.view_layer.objects.active
    elif len(keep) == 1:
        body = keep[0]
    else:
        raise SystemExit("no mesh found in " + src)

    body.name = os.path.splitext(os.path.basename(dst))[0]
    print("MERGED", body.name, "slots", len(body.data.materials))

    # 4: 量身高（REST），随后必须复位
    factor = 1.0
    if arm is not None:
        arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        lo, hi = world_bbox([body])
        h = hi - lo
        factor = target_h / h if h > 0 else 1.0
        print("REST_HEIGHT %.4f  TARGET %.2f  FACTOR %.6f" % (h, target_h, factor))

        # ★ 关键：复位成 POSE，否则导出的动画全是静止姿势
        arm.data.pose_position = "POSE"
        bpy.context.view_layer.update()
        assert arm.data.pose_position == "POSE", "pose_position 未复位"

    # 5: 导出
    bpy.ops.export_scene.fbx(
        filepath=dst,
        use_selection=False,
        object_types={"ARMATURE", "MESH"},
        add_leaf_bones=False,
        global_scale=factor,
        bake_anim=True,
        bake_anim_use_all_actions=True,
        bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0,
        mesh_smooth_type="FACE",
        apply_scale_options="FBX_SCALE_ALL",
        colors_type="SRGB",
        path_mode="COPY",
    )
    print("FBX_WRITTEN", dst, os.path.getsize(dst))


main()
