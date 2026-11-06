---
name: game-art-model
description: 本地图生 3D（Pixal3D / TRELLIS.2）并自动导入 UE 成为 uasset 的完整管线，含 8GB 显存参数、工作流改造、无头导入脚本与已知缺陷；另含把 poly.pizza / Sketchfab 的现成带骨骼角色导进 UE 的体检与踩坑清单。本机实测：单图约 2 分 15 秒/件、四视图约 6 分 53 秒/件，UE 导入 6 件约 1 分钟。Use when 要把 AI 生成的模型变成 UE 资产、做道具/场景件/武器/角色；或要导入现成带骨骼的角色/怪物，问「图生 3D 用什么模型」「怎么批量导进 UE」「为什么 UE 里看不到 mesh」「模型为什么是弯的/背面为什么是糊的」「为什么脚被拉长/像一把剑」「为什么动画有长度但人物不动」「为什么操作点不在模型上」时。
---

# 模型资产：AI 生成与第三方骨骼资产导入

## 快速开始

```powershell
# 1. 起服务（要 < 4483 MiB 显存占用，8GB 卡只跑一个）
cd D:\AIGamePipeline\ImagePipeline
.\venv\Scripts\python.exe .\comfy\main.py --listen 127.0.0.1 --port 8188 `
    --extra-model-paths-config D:\AIGamePipeline\UEAssetsPipeline\configs\pixal3d-paths.yaml `
    --input-directory D:\AIGamePipeline\UEAssetsPipeline\input `
    --output-directory D:\AIGamePipeline\UEAssetsPipeline\outputs --disable-auto-launch

# 2. 单图出模型
python D:\AIGamePipeline\UEAssetsPipeline\scripts\run_pixal3d.py --image <白底单件图>

# 2.5 细长物（剑/弓/杖）必须修复深度场：去弯 + 压薄，贴图不变
python D:\AIGamePipeline\UEAssetsPipeline\scripts\fix_slender.py `
    --src exports\SM_Sword_01.glb --dst exports\SM_Sword_01_Fixed.glb --target-thickness-mm 8
python D:\AIGamePipeline\UEAssetsPipeline\scripts\measure_slender.py `
    --glb exports\SM_Sword_01_Fixed.glb --ref exports\SM_Sword_01.glb

# 3. 关掉编辑器后无头导入 UE
UnrealEditor-Cmd.exe "<工程>.uproject" -run=pythonscript `
  -script="D:\AIGamePipeline\UEAssetsPipeline\scripts\ue_import.py" `
  -unattended -nopause -nosplash
```

**AI 不能直接产出 `.uasset`。** 只能生成 glb，再由 UE 自己导入。把 glb 丢进 `Content\` 不会自动识别。

第三方带骨骼资产（角色/怪物）走另一条三步线，详见 [RIGGED.md](RIGGED.md)：

```powershell
# ① 体检：bind pose / 脚骨层级 / 动画是否真有运动
blender.exe -b --factory-startup --python scripts\rig_inspect.py -- <in.glb>

# ② 转换（导出前会强制把 pose_position 复位成 POSE）
blender.exe -b --factory-startup --python scripts\glb2fbx.py -- <in.glb> <out.fbx> --height 1.8

# ③ 关编辑器 → 无头导入并把校验结果写文件
UnrealEditor-Cmd.exe "<工程>.uproject" -run=pythonscript -script="scripts\ue_rig_import.py" `
  -unattended -nop4 -nosplash -nullrhi
```

## 选哪条管线

| 需求 | 管线 | 耗时 | 代价 |
|---|---|---|---|
| 刚性道具、场景件、武器 | **单图**（主路线） | ~2 分/件 | 背面靠猜 |
| 角色、需要背面厚度 | **四视图** | ~7 分/件 | 需先有四张一致视图 |
| 已有单图结果想"精修" | 渲染回灌 | ~7 分/件 | **不增加信息，只是更规整** |
| **带骨骼、带动画的角色/怪物** | **第三方资产转换** | 10~30 分 | **必须先体检 bind pose 与骨骼层级** |

最后一条是唯一能拿到骨骼动画的路线——图生 3D 产不出动画。详见 [RIGGED.md](RIGGED.md)。

四视图的输入必须是**几何一致**的四张图。用生图模型分别抽四张不行（细节各画各的），正确做法见 [REFERENCE.md](REFERENCE.md)。

## 输入图规范（决定八成质量）

| 要求 | 原因 |
|---|---|
| 单件、不与其他物体接触 | 多物体会粘成一坨 |
| 纯白或纯色底 | 背景会被生成进模型 |
| 平视、正交，无强透视 | 透视会让模型比例失真 |
| 完整入画，留 10% 边距 | 裁切会导致缺面 |
| **细长物体必须裁紧** | 剑只占画面 10% 时，直线度必然崩 |

产品图提示词模板：`single object, orthographic front view, product shot, isolated on plain white background, even lighting, no shadow, full object in frame`。

## UE 导入

前置（一次性）：`.uproject` 里启用 `PythonScriptPlugin` 与 `EditorScriptingUtilities`。

脚本行为：清空 `/Game/Assets` → 导入 → 全部资产拍平到根目录 → 删空目录 → 确保 Nanite。
实测 6 件 40MB 级 glb，导入约 1 分钟。

> 编辑器必须先关闭。UE 会锁工程，commandlet 与编辑器不能同时开。

## 第三方骨骼资产（另一条线）

要**骨骼动画**时，图生 3D 帮不上忙，必须用现成绑定资产。这条线有三个必查项，任何一个漏掉都会浪费半天：

| 体检项 | 判据 | 实测反例 |
|---|---|---|
| bind pose 在原点 | `REST` 姿势下脚底 z ≈ 0 | Adventurer：z = −5.27 ~ −3.41，UE 里偏出 4.3m |
| 脚骨挂在小腿下 | `Foot.L` 的父级是 `LowerLeg.L` | Quaternius CharacterArmature：`Foot.L → Root`，跑起来脚被拉成尖刺 |
| 动画真的有运动 | 逐帧世界包围盒有变化 | 导出时忘了把 `pose_position` 从 `REST` 复位，24 段动画长度正确但全静止 |

三个最容易踩的坑：

- ❌ `AssetImportTask` 设了 `destination_name` → **动画被静默跳过**，只导网格
- ❌ 目标资产被蓝图引用 → `delete_asset` 失败但不报错，**替换静默无效**（只能看文件时间戳）
- ❌ 在编辑器开着时导入 → 保存失败，改动不落盘

完整流程、修骨骼的代码、故障对照表见 [RIGGED.md](RIGGED.md)。

## 验收清单（UE 内）

| 检查 | 判据 |
|---|---|
| 朝向 | 正面应朝 +X；不对就在导入时加 90° yaw |
| 缩放 | **不用手动缩放**。glb 以米为单位，UE 自动转厘米 |
| Nanite | 应已开启；38 万面必须开 |
| 碰撞 | 默认没有，需 Auto Convex Collision 或 Box |
| 贴图 | 1 材质 + 3 贴图（基础色/金属粗糙/法线） |

**不要用 `get_num_triangles` 判断是否被简化**：Nanite 网格返回的是 LOD0 回退网格（约 2k），完整几何在 Nanite 数据里，以 uasset 体积和观感为准。

## 已知缺陷（本机实测）

1. **背面是猜的**：单图只给正面，背面会被补成一整片，披风/斗篷类最明显。
2. **脸糊**：五官塌陷，单图生成的硬上限。
3. **深度场尺度失准**：单图没有深度线索，模型会把轮廓"挤出"成方棒。实测剑刃截面 4.3×4.2cm（真实应 0.6×4.5cm），护手 12cm 厚、柄首 7cm 厚——整个物体深度方向被放大 **约 6 倍**。
4. **深度方向漂移**：同一个根因还会让中心线沿深度轴漂移。实测一把剑全长 96cm 内漂 **5.3cm**，剑尖段加速下垂。它在正面渲染里**完全看不出来**（正面中心线残差只有 1.7mm）。
   - 3 和 4 是同一个错误：**深度场尺度错 + 深度场低频漂移**，修法见 `scripts\fix_slender.py`（REFERENCE.md 第 9 节）。
5. **四视图回灌不修缺陷**：输入来自同一网格，信息量不变；还会因渲染光照把贴图拉暗一档。
6. **道具用四视图性价比低**：7 分钟 vs 2 分钟，刚性道具肉眼几乎无差。

## 反模式

- ❌ 把 `.glb` 放进 `Content\` 等 UE 自动识别。它不是资产。
- ❌ 在编辑器开着时跑导入命令。会锁工程，直接失败。
- ❌ 用三角形数判断导入是否丢面。Nanite 下这个数没有意义。
- ❌ 以为裁紧输入图能修正细长物的弯曲。实测输入图轮廓已是 0.095° 直线、网格轮廓残差 1.7mm，弯曲全在深度轴，裁图无效。
- ❌ 只看正面渲染验收细长武器。弯曲与超厚都在深度轴，正面完全看不出。
- ❌ 用四视图回灌去"补背面"。不增加信息，只增加耗时。
- ❌ 直接生成刃身。武器刃身应程序化挤出，AI 只做护手/柄/装饰。

第三方骨骼资产还有几条：

- ❌ 拿到带骨骼资产直接导 UE，不做体检。bind pose / 脚骨层级 / 动画有效性，三样任缺一个都要返工。
- ❌ 看到「动画长度正常」就认为动画没问题。长度对但全帧静止是常见坑。
- ❌ 用「同一作者」推断骨架正常。实测同一作者的僵尸正常、冒险者脚骨挂错根节点。
- ❌ 删资产前不查引用者。`delete_asset` 会静默把蓝图里的引用置空。
- ❌ 以为 `import_asset_tasks` 返回成功就是替换成功。要看文件时间戳。
- ❌ 为了修资源顺手改用户的蓝图/AnimBP。资源出问题就报资源，配置问题交回用户。

## 详细资料

模型清单与许可、工作流改造细节（动态下拉框前缀、裁切链剔除）、导入脚本踩坑、多视图渲染参数、排错表，见 [REFERENCE.md](REFERENCE.md)。

第三方骨骼资产（glTF/FBX → UE）的完整流程、体检方法、修骨骼代码、故障对照表，见 [RIGGED.md](RIGGED.md)。配套脚本在 `scripts/`：

| 脚本 | 用途 |
|---|---|
| `scripts/rig_inspect.py` | Blender 体检：bind pose、骨骼层级、动画是否真有运动 |
| `scripts/glb2fbx.py` | Blender 转换：清理 → 合并 → 归一化 → 导出（含 `pose_position` 复位） |
| `scripts/ue_rig_import.py` | UE 无头导入 + 重命名 + 校验（读同目录 `ue_rig_import.json`） |
| `scripts/ue_rig_import.example.json` | 上面那个脚本的配置模板 |
| `scripts/extract_glb_texture.py` | 从 GLB 的 BIN chunk 抽内嵌贴图 |
