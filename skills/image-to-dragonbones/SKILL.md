---
name: image-to-dragonbones
description: 从单张角色图片生成 DragonBones 骨骼资源的完整流水线。使用 See-through (LayerDiff) 分割部件，再用 pngs2db.py 合成 DragonBones 骨骼。Use when user wants to generate DragonBones skeleton from an image, mentions "png2db", "图片转骨骼", or "image to dragonbones".
---

# Image → DragonBones 流水线

## 路径配置（改这里适配你的项目）

```
{SEE_THROUGH}    = D:\Code\see-through              （推理项目根目录）

{INPUT_DIR}      = D:\Code\CLEngine2D\assets\see_through_input   （输入图片目录）
{RAW_DIR}        = D:\Code\CLEngine2D\assets\see_through_output  （推理原始输出，含 _depth 深度图 + src_ 中间图 + PSD）
{PARTS_DIR}      = D:\Code\CLEngine2D\assets\see_through_parts   （最终干净部件 PNG，仅含非噪点部件）
{DB_DIR}         = D:\Code\CLEngine2D\assets\db_output           （DragonBones 骨骼输出）

{INFERENCE_SCRIPT} = {SEE_THROUGH}\run_inference.py         （推理脚本）
{PNG2DB_SCRIPT}    = <本skill目录>\pngs2db.py               （转换脚本）
```

## 流程概览

```
输入图片 (PNG/JPG)
    │
    ▼
See-through 推理 → {RAW_DIR}/<name>/    中间产物
  ├── LayerDiff (语义分割)               (部件 PNG, src_ 原图/头像)
  ├── Marigold  (深度估计) ─── compact 模式跳过
  └── further_extr (后处理) ─ compact 模式跳过
    │
    ▼ 自动提取最终部件
{PARTS_DIR}/<name>/                     最终部件
    │  仅含有效部件 PNG（已过滤 src_、噪点）
    ▼
pngs2db.py → {DB_DIR}/                 骨骼输出
  ├── *_ske.json    骨骼
  ├── *_tex.json    图集
  └── *_tex.png     纹理
```

## 前置条件

- See-through 项目已安装依赖、模型已下载
- Python 3.12+，依赖：`Pillow`, `numpy`, `scipy`
- CUDA 可用（RTX 5060 8GB 已验证）
- vram < 10GB → `--group_offload True` + `--resolution 768`

## 工作流

### 1. 准备输入图片

```
{INPUT_DIR}\<图片名>.png
```

单角色全身图，背景干净，分辨率建议 512~1024px。

### 2. See-through 推理

```powershell
Set-Location {SEE_THROUGH}
python.exe run_inference.py ^
    --image "{INPUT_DIR}\<图片名>.png" ^
    --output "{RAW_DIR}\<图片名>" ^
    --parts-dir "{PARTS_DIR}" ^
    --resolution 768 ^
    --num_inference_steps 10 ^
    --group_offload True ^
    --taglist full
```

**`--taglist` 参数说明**：

| 模式 | 输出部件数 | 说明 |
|------|-----------|------|
| `full` | 24 | 默认。Body (13) + Head (11) 全量输出，含 tail/wings/objects 和面部细节拆分 |
| `compact` | ~13 | Body 去掉 tail/wings/objects（剩 10）；Head 仅保留 headwear/eyewear，其他面部细节合并到 face。同时跳过 Marigold 深度估计 + further_extr 后处理，速度快很多 |

> compact 模式需要将本 skill 目录下的 `inference_utils.py` 替换到 See-through 项目中。详见 [README.md](README.md)。|

推理完成后：
- `{RAW_DIR}/<图片名>/` — 所有原始输出（部件 PNG + `_depth` 深度图 + `src_` 原图 + PSD），**中间产物**
- `{PARTS_DIR}/<图片名>/` — 仅干净的最终部件 PNG，**用于下一步骨骼转换**

**已知 bug & patch**：

scheduler 下载错误（硬编码 juggernautXL ID）→
修改 `common/utils/inference_utils.py`，在 pipe 构造前：
```python
scheduler = DPMSolverMultistepScheduler.from_pretrained(
    local_path, subfolder="scheduler"
)
```

Marigold tokenizer OverflowError →
```python
pipe.tokenizer.model_max_length = 77
```

### 3. 转换 → DragonBones

```powershell
python.exe {PNG2DB_SCRIPT} ^
    "{PARTS_DIR}\<图片名>" ^
    "{DB_DIR}" ^
    --name "<英文名>"
```

**脚本行为**：
- 自动跳过 `_depth` 深度图、`src_` 中间图
- 过滤 alpha 面积 < 20px 的噪点
- 按 Z-order 排序（legwear → topwear → head → face → front hair）
- 水平条带打包图集
- 坐标：Image top-left → DragonBones Y-up center-origin

### 4. 引擎加载

```cpp
#include <SceneGraph/DBArmatureNode.h>

auto* dbNode = new DBArmatureNode();
dbNode->LoadFromFile(
    "assets/db_output/<name>_ske.json",
    "assets/db_output/<name>_tex.json",
    "assets/db_output/<name>_tex.png",
    "Armature"
);
```

## 输出验证

- `_ske.json.version` = `"5.5"`（引擎支持 4.0~5.5）
- slot `transform.x/y` 在 ~-300~300 范围
- `_tex.json.SubTexture[].name` 与 `_ske.json.display.name` 一致
- 图集 PNG 透明度正确，无错位

## 已知问题

- 推理仅输出图片中实际存在的部件
- 骨骼平铺（全挂 root bone），无父子层级 → 需手动在 DragonBones Pro 绑定动画
- 极小部件（irides 35×6、mouth 7×4）渲染可能偏移 → 调整 `min_area` 或用 `--taglist compact` 自动合并到 face
- OOM → 降 `resolution` 或 `num_inference_steps`，确保 `group_offload=True`
- `compact` 模式下 face 是合并图（含眼睛、鼻子、嘴），不能独立换装面部子部件；如需独立换眼镜/帽子则面部细部件会保留
