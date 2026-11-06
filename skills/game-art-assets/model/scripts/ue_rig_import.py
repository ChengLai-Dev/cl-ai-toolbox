"""UE 端：把带骨骼的 FBX 导成 uasset，并校验结果。

用法:
    1. 关闭编辑器
    2. .uproject 里临时启用 PythonScriptPlugin
    3. UnrealEditor-Cmd.exe "<工程>.uproject" -run=pythonscript ^
         -script="<本文件>" -unattended -nop4 -nosplash -nullrhi
    4. 读 <脚本目录>/ue_rig_import_result.txt

配置写在同目录的 ue_rig_import.json:
{
  "fbx": "D:/.../Adventurer2_fixed.fbx",
  "dest": "/Game/Assets/Player",
  "mesh_name": "SK_Adventurer",
  "skeleton_name": "SK_Adventurer_Skeleton",
  "physics_name": "SK_Adventurer_PhysicsAsset",
  "anim_prefix": "AS_",
  "anim_suffixes": ["Idle", "Walk", "Run", "Run_Back", "Death", "Interact"]
}

关键约束（踩过的坑，别改）:
  · 不要设 AssetImportTask.destination_name —— 设了动画会被静默跳过，只导网格
  · 目标位置已有同名资产且被蓝图引用时删不掉 —— 先关编辑器、从磁盘删旧文件
  · 导入结果一律写文件，commandlet 里 print() 经常不落日志
"""

import json
import os

import unreal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "ue_rig_import.json")
RESULT_PATH = os.path.join(SCRIPT_DIR, "ue_rig_import_result.txt")

lines = []


def log(msg):
    lines.append(str(msg))


def save():
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def classify(name, cfg):
    if name.endswith("_Skeleton"):
        return cfg["skeleton_name"]
    if name.endswith("_PhysicsAsset"):
        return cfg["physics_name"]
    if "Armature" in name or "armature" in name:
        matched = None
        for suffix in cfg.get("anim_suffixes", []):
            if name.endswith(suffix) and (matched is None or len(suffix) > len(matched)):
                matched = suffix
        if matched:
            return cfg.get("anim_prefix", "") + matched
        return None
    return cfg["mesh_name"]


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    eat = unreal.EditorAssetLibrary
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    dest = cfg["dest"]

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", cfg["fbx"])
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    # 不要设置 destination_name

    tools.import_asset_tasks([task])
    paths = [str(p) for p in task.get_editor_property("imported_object_paths")]
    log("IMPORTED %d" % len(paths))

    for path in paths:
        name = path.split("/")[-1].split(".")[0]
        target_name = classify(name, cfg)
        if not target_name or target_name == name:
            continue
        target = dest + "/" + target_name
        if eat.does_asset_exist(target):
            log("CONFLICT 已存在，跳过重命名: " + target)
            continue
        eat.rename_asset(path, target)

    log("RENAMED")

    mesh = unreal.load_asset(dest + "/" + cfg["mesh_name"])
    if mesh:
        b = mesh.get_bounds()
        log("bounds origin %s" % (b.origin,))
        log("bounds extent %s" % (b.box_extent,))
        log("feet_z %.2f   (应接近 0)" % (b.origin.z - b.box_extent.z))
        log("height_cm %.2f" % (b.box_extent.z * 2))

        sub = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        for n in cfg.get("check_bones", []):
            try:
                log("bone %-12s parent = %s" % (n, sub.get_bone_parent(mesh, n)))
            except Exception as e:
                log("bone %-12s ERR %s" % (n, e))
    else:
        log("MESH_MISSING " + cfg["mesh_name"])

    idle = unreal.load_asset(dest + "/" + cfg.get("anim_prefix", "") + "Idle")
    if idle:
        log("Idle length %.3f" % idle.get_editor_property("sequence_length"))

    anims = [p for p in eat.list_assets(dest + "/")
             if p.split("/")[-1].startswith(cfg.get("anim_prefix", ""))]
    log("ANIM_COUNT %d" % len(anims))

    for probe in (cfg["mesh_name"], cfg.get("anim_prefix", "") + "Idle"):
        p = dest + "/" + probe
        try:
            log("REFERENCERS %s : %s"
                % (probe, list(eat.find_package_referencers_for_asset(p, False))))
        except Exception as e:
            log("REFERENCERS %s ERR %s" % (probe, e))

    log("DONE")


try:
    main()
except Exception:
    import traceback
    log("EXCEPTION")
    log(traceback.format_exc())

save()
