# 第三方骨骼资产 · 从 glTF 到 UE

> 适用于：从 poly.pizza / Sketchfab / Fab 等处拿到**已经绑好骨骼、带动画**的角色或怪物，要导进 UE 使用。
> 不适用于：AI 图生 3D（那条线见 [SKILL.md](SKILL.md) 与 [REFERENCE.md](REFERENCE.md)）。

---

## 1. 为什么不能靠 AI 生

骨骼动画无法由图生 3D 产出。角色一律走**现成绑定资产**。
AI 生成只适合无骨骼物件（机体、道具、场景件）。

---

## 2. 找资产：能在国内直连的源

| 源 | 登录 | 可否脚本抓取 | 说明 |
|---|---|---|---|
| **poly.pizza** | 不需要 | ✅ | 首选。Quaternius 等 CC0 作者的主要分发点 |
| Sketchfab | 需要 | ❌ | 下载接口要 OAuth token |
| Fab | 需要 Epic 账号 | ❌ | 页面返回 403，走启动器 Vault |
| Mixamo | 需要 Adobe 账号 | ❌ | 动画库，模型仍需另找 |

### poly.pizza 直链规则

模型页 `https://poly.pizza/m/<id>` 的 HTML 里直接含有资源直链：

```
模型：https://static.poly.pizza/<uuid>.glb
缩略图：https://static.poly.pizza/<uuid>.jpg
```

`<uuid>` 从页面 HTML 正则 `https://static\.poly\.pizza/[0-9a-f-]{36}\.glb` 提取即可，无需登录。
先用缩略图拼一张 contact sheet 筛选，再下载选中的，省时间。

### 授权

poly.pizza 上多为 **CC0** 或 **CC-BY**。
CC-BY 必须署名：在游戏内留 Credits，写明作者与链接。
**不要**把资产授权信息写进作品集声明时含糊带过——一定要能列出每一件的来源。

---

## 3. 转换：glTF → FBX（Blender）

**UE 5.8 只有 `GLTFExporter`，没有 glTF 导入器**（`Engine/Plugins/Enterprise/GLTFExporter`）。所以必须过一遍 Blender。

```powershell
blender.exe --background --factory-startup --python `
  scripts\glb2fbx.py -- <in.glb> <out.fbx> --height 1.8
```

脚本做的事，以及每件事的原因：

| 步骤 | 原因 |
|---|---|
| 删掉名为 `Icosphere` 的网格 | poly.pizza 的 glTF 常带一个无关球体，会把包围盒撑到 2m，导致身高归一化算错 |
| 删掉所有 `*_end` EMPTY | glTF 导入产生的骨骼尾端辅助节点，会污染导出层级 |
| 合并全部蒙皮网格 | 一个角色常拆成 Body/Feet/Head/Legs/Backpack，直接导 UE 会变成 5 个 SkeletalMesh |
| 用**求值后世界包围盒**量身高 | `object.dimensions` 是局部空间；模型带 100× 父级缩放和 −90° 旋转时会严重误导 |
| `global_scale` 归一化 | Quaternius 资产常以 100× 尺度制作，实测原高 4.84m / 7.71m 都有 |
| 导出前 **`arm.data.pose_position = 'POSE'`** | 见下方「最贵的一课」 |

### 最贵的一课：`pose_position`

如果为了量身高把骨架切到 `REST`，**导出前必须切回 `POSE`**，否则 Blender 会把每一帧都按静止姿势烘一遍。

症状极具欺骗性：**24 段动画长度全部正确（如 Idle 2.083s）、时间轴有内容，但人物一动不动**。
排查时容易误判成「UE 没导入动画」或「AnimBP 没配」，实际是数据本身就是静止的。

```python
arm.data.pose_position = "REST"   # 量身高
...measure...
arm.data.pose_position = "POSE"   # ★ 必须复位
```

---

## 4. 导入前体检（三项，缺一不可）

**任何第三方骨骼资产，先体检再导入。**
三项全过再往下走，能省掉一整天。

```powershell
blender.exe --background --factory-startup --python `
  scripts\rig_inspect.py -- <asset.glb>
```

### 4.1 bind pose 是否在原点

切 `REST` 量世界包围盒，**脚底应在 z ≈ 0**。

| 实测 | 结果 |
|---|---|
| Quaternius Zombie | REST z = 0 ~ 1.76 ✅ |
| Adventurer（Abandoned） | REST z = **−5.27 ~ −3.41** ❌ |
| Adventurer2 | REST z = 0 ~ 1.83 ✅ |

bind 偏移的后果：UE 里网格**偏出去 4.3 米**，操作点在模型外，且蒙皮会被错切。
这种资产直接换，不要试图修。

### 4.2 骨骼层级是否合理

重点看**脚骨是否挂在小腿下面**。

```python
for n in ("LowerLeg.L", "Foot.L", "PT.L"):
    b = arm.data.bones.get(n)
    print(n, "->", b.parent.name if b and b.parent else None)
```

实测反例：Quaternius 的 `CharacterArmature` 系列把 `Foot.L` / `PT.L` 直接挂在 `Root` 下。
**后果：跑动时脚不跟着腿走，靴子被拉成长尖刺**（看起来像一把剑）。
同作者另一个包（僵尸，`LeftFoot → LeftLeg`）是正常的——所以**同一作者不等于同一套骨架，必须每个资产单独查**。

### 4.3 动画是否真的有运动

逐帧量世界包围盒，各帧应有差异。

```python
for f in (1, 8, 16, 24):
    scene.frame_set(f)
    ...bbox...
```

全帧完全一致 = 动画是静止的，回到第 3 节的 `pose_position` 问题。

---

## 5. UE 导入

### 5.1 不要设 `destination_name`

```python
task = unreal.AssetImportTask()
task.set_editor_property("filename", FBX)
task.set_editor_property("destination_path", DEST)
task.set_editor_property("automated", True)
task.set_editor_property("replace_existing", True)
task.set_editor_property("save", True)
# ❌ 不要设置 destination_name
```

**一旦设了 `destination_name`，Interchange 就只导网格和骨架，动画被静默跳过**——日志里一句错误都没有，`imported_object_paths` 只有 1~2 条。

需要干净的名字，靠导入后 `rename_asset` 改。

### 5.2 被引用的资产删不掉

`EditorAssetLibrary.delete_asset` 对**被蓝图引用的资产**可能失败（返回 False，且不报错）。
后果：`rename_asset(path, target)` 因目标已存在而失败，新资产留在临时目录，**旧资产数据一点没变**——但你会以为替换成功了。

排查手段只有一个：**看文件时间戳**。

```powershell
Get-ChildItem <Content\...\Player> -Filter "AS_*" | Sort-Object LastWriteTime
```

如果目标资产时间戳还是旧的，就是没替换成功。

可靠做法：

1. **关闭编辑器**（否则文件锁导致保存失败）
2. 直接从磁盘删除旧 `.uasset`
3. 重新导入
4. 重命名到原路径

UE 的跨包引用是**按路径导入**的，路径不变时，重新加载后会自己接回去，不需要改蓝图。

### 5.3 无头导入的前置

`.uproject` 里临时启用 `PythonScriptPlugin`，跑完还原：

```json
{ "Name": "PythonScriptPlugin", "Enabled": true }
```

编辑器必须关闭。commandlet 与编辑器不能同时开——同时开会看到
`LogSavePackage: Error: Error saving '...uasset'`。

### 5.4 日志里看不到 `print()`

`UnrealEditor-Cmd.exe -run=pythonscript` 下 `print()` 常常不落到日志。
把结果写文件再读：

```python
open(r"D:\Code\temp\result.txt", "w", encoding="utf-8").write("\n".join(lines))
```

---

## 6. 导入后验证（在 UE 里查，不看 Blender）

```python
mesh = unreal.load_asset("/Game/Assets/Player/SK_XXX")
sub = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)

for n in ("LowerLeg_L", "Foot_L", "PT_L"):
    print(n, sub.get_bone_parent(mesh, n))

b = mesh.get_bounds()
print("feet_z =", b.origin.z - b.box_extent.z)   # 应 ≈ 0
```

| 检查 | 判据 |
|---|---|
| 脚底归零 | `origin.z − extent.z ≈ 0`（实测 −0.05cm） |
| 身高 | `extent.z × 2` ≈ 180cm |
| 骨骼层级 | `Foot_L` 的父级是 `LowerLeg_L` |
| 动画长度 | `AnimSequence.sequence_length` > 0 |
| 引用完好 | `find_package_referencers_for_asset` 里能看到蓝图 |

---

## 7. 故障对照表

| 症状 | 原因 | 修法 |
|---|---|---|
| 操作点离模型很远（几米） | bind pose 偏移 | 换资产，别修 |
| 脚被拉成长尖刺 / 像一把剑 | 脚骨父级是 `Root` | 重挂父级 + 重烘（第 8 节） |
| 人物被拉成一把剑（整体） | 用**别的骨架**的动画驱动本网格 | 换回本骨架的动画 |
| 动画有长度但完全不动 | 导出时 `pose_position='REST'` | 复位 `POSE` 重导 |
| 只导进网格，动画全丢 | 设了 `destination_name` | 去掉该设置 |
| 替换后毫无变化 | 资产被引用，删除失败 | 关编辑器 + 磁盘删除 + 重导 |
| 材质是灰的 | 贴图 payload 提取失败 | 从 GLB 手动抽图（第 9 节） |
| 材质槽 9 个、想压成 1 个 | 顶点色导入不可靠 | 用材质实例逐槽换，别赌顶点色 |

---

## 8. 修骨骼：重挂父级 + 重烘世界矩阵

当层级不对（脚挂在 `Root`）但又必须用这个资产时：

**只改父级不够**——原来的动画曲线是相对旧父级写的，改完会错。必须重烘。

```python
FOOT = ["Foot.L", "PT.L", "Foot.R", "PT.R"]
REPARENT = {"Foot.L": "LowerLeg.L", "PT.L": "Foot.L",
            "Foot.R": "LowerLeg.R", "PT.R": "Foot.R"}

# 1) 先在原骨架上采样每段动画、每帧的脚骨世界矩阵
samples = {}
for act in bpy.data.actions:
    arm.animation_data.action = act
    per = {}
    for f in range(int(act.frame_range[0]), int(act.frame_range[1]) + 1):
        scene.frame_set(f); bpy.context.view_layer.update()
        per[f] = {n: arm.pose.bones[n].matrix.copy() for n in FOOT}
    samples[act.name] = per

# 2) 编辑模式改父级（改 parent 不会移动骨骼，rest 保持不变）
bpy.ops.object.mode_set(mode="EDIT")
for child, parent in REPARENT.items():
    arm.data.edit_bones[child].parent = arm.data.edit_bones[parent]
bpy.ops.object.mode_set(mode="OBJECT")

# 3) 用记录的世界矩阵重新 K 帧（先父后子）
for act in bpy.data.actions:
    arm.animation_data.action = act
    for f, mats in sorted(samples[act.name].items()):
        scene.frame_set(f)
        for n in ("Foot.L", "PT.L", "Foot.R", "PT.R"):
            pb = arm.pose.bones[n]
            pb.matrix = mats[n]
            bpy.context.view_layer.update()
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("rotation_quaternion", frame=f)
            pb.keyframe_insert("scale", frame=f)
```

**注意**：Blender 5.x 的 `Action` 没有 `.fcurves` 了（改成了 layer/strip/channelbag）。
需要直接操作曲线时用 `action.layers[...]`，或者干脆走上面这种「采样 + 重新打帧」的路线，绕开 API 差异。

---

## 9. 贴图与材质

- glTF 内嵌贴图在 Blender→FBX 时常丢（UE 报 `UInterchangeTextureFactory: Invalid translator couldn't retrieve a payload`）。
- 直接从 GLB 的 BIN chunk 里把 image 抽出来存 PNG，再单独导入：见 `scripts/extract_glb_texture.py`。
- Quaternius 一类资产的"贴图"其实是一条 **32×32 调色板色带**，导入后是纯色块，不是照片贴图。这是资产本身的上限，不要误判成导入失败。
- 调色板贴图导入时把 Filter 设为 `TF_NEAREST`，否则相邻色块会互相渗色。

---

## 10. 协作边界（重要）

**只改 `Content/Assets` 下的资源。不要碰用户的蓝图、AnimBP、关卡。**

- 发现蓝图配置有问题 → 告诉他改哪儿，不代劳。
- 删除任何资产前，先查引用者：

```python
unreal.EditorAssetLibrary.find_package_referencers_for_asset(path, False)
```

有引用者就停下来，先说清楚会破坏什么。
UE 的 `delete_asset` 会**静默把引用置空**，没有任何提示——删完才发现 AnimBP 里一堆 None。
