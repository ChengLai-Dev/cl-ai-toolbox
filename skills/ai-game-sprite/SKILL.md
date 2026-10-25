---
name: ai-game-sprite
description: 本地生成 2D 游戏美术资源的三合一流水线。模式①静态图：Z-Image 文生图 → BiRefNet 抠透明底 →（可选）无缝化，产出道具/图标/背景/立绘/地块五类静态资源。模式②静态图生序列帧：任意静态图 → 去背合成纯灰底 → Wan 2.2 图生视频 49 帧 → 洪水填充抠图 → 按步态周期挑帧 → 归一/校验/写 manifest。模式③文生序列帧：Z-Image 出基础立绘 → Canny 控制图 → ControlNet 精修姿势 → Wan 2.2 → 图集。8GB 显存可跑，模型全部 MIT/BSD/Apache-2.0，产出可商用。Use when 用户要做 2D 游戏美术资源、静态美术图、道具、图标、场景背景、立绘、地块贴图、角色动画、序列帧、sprite sheet、精灵图、行走/跑步/攻击/待机循环、交付给引擎的逐帧素材，或提到 AI 生成游戏素材、walk cycle、animation frames、game art asset、prop、icon、background、tileset、pivot/anchor、atlas。
---

# 2D 游戏美术资源生成

## 模式路由（先看这张表）

```
用户给了图片路径吗？
├─ 没有
│   └─ 要动画吗？（动画/序列帧/行走/跑步/待机/攻击/受击/动起来/walk/run/idle/attack/hit）
│       ├─ 是 → --mode frames
│       └─ 否 → --mode static
└─ 有
    ├─ 要动画吗？
    │   ├─ 是 → --mode frames-from-image
    │   └─ 否 → --mode static   （--subject 描述要画什么，源图只当风格参考）
    └─ 只字未提动画 → 先问用户，别猜
```

**模式②只接受角色类静态图**。源图是场景/背景就不要用模式②（要视差/分层动起来是另一个需求，本 skill 不支持）。

`--mode static` 的 `--kind` 按产物类型选：`prop` 道具 / `icon` 图标 / `background` 场景背景 / `portrait` 角色立绘 / `tile` 地块贴图。

## 快速开始

```powershell
$S = "D:\Code\.config\opencode\skills\ai-game-sprite\scripts"

# ① 静态美术资源（交付一律 --upscale never，见模式①的许可红线）
python $S\generate.py --mode static --character crate --kind prop `
  --subject "a small wooden crate with iron bands" --seed 20261021 --upscale never

# ② 根据静态图生成序列帧
python $S\generate.py --mode frames-from-image --character hero `
  --src D:\art\hero.png --action walk --seed 20261021

# ③ 根据文字生成序列帧
python $S\generate.py --mode frames --character hero --action walk --seed 20261021

# ④ 交付前两步（见「交付前必做」一节，别跳过）
python $S\pick_gait_frames.py --src <Wan输出目录> --out <中间帧> --frames 4
python $S\fit_and_validate.py --src <中间帧> --out-dir <工程目录>/enemies/grunt `
  --asset enemy_grunt_walk_east --canvas 48x56 --anchor bottom --fps 8 --loop --facing east `
  --allow-offcenter --manifest-root <工程目录>
```

产出位置（流水线是验收区，不是工程目录）：

| 模式 | 产物 |
|---|---|
| ① | `ai-game-pipeline\game\assets\art\<kind>\<name>.png` + 同名 `.json`（seed/prompt/尺寸） |
| ②③ | `ai-game-pipeline\game\assets\sprites\<name>\atlas.png` + `manifest.json` + `frames\<action>\*.png` |

**命名规则**：流水线里所有路径都由名字派生，同名即同一份素材。给了 `--project` 时落盘名变成
`<project>__<name>`，两个工程的 `hero` 互不干扰（不加前缀时，A 工程的 walk 和 B 工程的 run 会被打进同一张图集）。

**交付到工程**：`--dest <工程的 assets 目录>`，验收通过后自动复制成品过去并去掉工程前缀。
静态 → `<dest>\art\<kind>\<name>.png`；序列帧 → `<dest>\sprites\<name>\{atlas.png,manifest.json}`。
不交付 `frames\` 目录（重打包用的源帧，进工程只会被 Godot 白白导入一遍）。

自检环境：`python $S\check_env.py`

## 模式①静态资源：四步流程

| 步骤 | 脚本 | 模型 | 实测耗时 |
|---|---|---|---|
| 1 出图 | `gen_look.py` | Z-Image Turbo 6B (GGUF Q6) | 30–220 秒 |
| 2 放大（可选） | `post_process.py --upscale` | 4x-UltraSharp (ESRGAN) | 30–60 秒 |
| 3 抠图 | `post_process.py --cutout` | BiRefNet / Lucida | 20–40 秒 |
| 4 无缝化 | `post_process.py --seamless` | 纯 numpy | 1 秒 |

各类型默认动作（`config.ART_KINDS`）：

| kind | 最终尺寸 | 生成尺寸 | 放大 | 抠图 | 无缝化 |
|---|---|---|---|---|---|
| `prop` | 256×256 | 768×768 | ✅ | ✅ | — |
| `icon` | 128×128 | 768×768 | ✅ | ✅ | — |
| `background` | 1536×1024 | 768×512 | ✅ | ❌ 抠了就废了 | — |
| `portrait` | 768×1024 | 576×768 | ❌ | — | — |
| `tile` | 256×256 | 768×768 | ✅ | ❌ | ✅ |

**超分是这套管线唯一的许可风险点**：`4x-UltraSharp` 的权重许可在不少环境下拿不到原文
（本机实测就是如此，包里没有 LICENSE）。所以**交付链路默认 `--upscale never`**：
目标尺寸比 768 小很多时，768 源直接 LANCZOS 缩下去，比“先 4x 再缩”更干净也更快。
只有拿到权重 LICENSE 原文、或换成 Real-ESRGAN 官方 BSD-3 权重时，才开 `--upscale auto`。

生成尺寸永远 ≤768：1024 会触发 Windows 共享显存，出图从 32 秒退化到 863 秒。
放大放在抠图之前：ComfyUI 的 `LoadImage` 会丢 alpha 通道，反过来会把透明边缘糊掉。

## 模式②静态图生序列帧：三步

| 步骤 | 脚本 | 做什么 |
|---|---|---|
| 1 归一化 | `prep_source.py` | 去背 → 合成纯灰底 (236,240,245) → 按模式③版式放进 768×768 正方形画布（角色满高居中，左右留白） |
| 2 可选精修 | `make_control.py` + `gen_look.py --control-image` | 源图是草稿/风格参考时才做；已是最终画风就加 `--no-look-refine` 省 90 秒 |
| 3 动画 | `run_wan_a14b.py` → `import_frames.py` → `pack_atlas.py` | 与模式③一致 |

**归一化不能省**。Wan 的首帧会锚定整个视频的背景；下游抠图要求「四角同色 + 低饱和 + 边界连通」三条同时成立。
归一化后角色在正方形画布里占满高度、宽度 ≤75%，这样 Wan 按 3:4 中心裁切时不会切到头脚。

## 模式③文生序列帧：五步流程

| 步骤 | 脚本 | 模型 | 实测耗时 |
|---|---|---|---|
| 1 基础立绘 | `gen_look.py`（纯文生图） | Z-Image Turbo 6B (GGUF Q6) | 30 秒 |
| 2 控制图 | `make_control.py`（Canny） | 无 | 1 秒 |
| 3 精修立绘 | `gen_look.py --control-image` | Z-Image + Fun-Controlnet-Union | 60–70 秒 |
| 4 动画 | `run_wan_a14b.py` | Wan 2.2 I2V-A14B（4 步 LoRA） | 60–145 秒 |
| 5 图集 | `import_frames.py` + `pack_atlas.py` | Pillow | 约 5 秒 |

第 3 步的 ControlNet 默认开启：它把姿势/轮廓钉死后再喂 Wan，实测循环闭合 iou 0.742 → 0.760。
要退回纯文生图加 `--no-controlnet`。

## 交付前必做：挑帧 + 归一/校验

`atlas.png` 是**验收图**，不是引擎能用的素材（尺寸、锚点、命名都不是引擎要的）。
而且 `import_frames.py --auto-loop` 挑的是「最相似的一对帧」，会落在动作最平缓的区间 ——
实测一个 48×56 的小怪，拍出来 4 帧几乎同姿态。所以交付前固定两步：

```powershell
# 第 1 步：按步态周期挑帧 + 逐帧尺寸归一
#   掩膜自相关找周期 T（同一姿势隔多少帧重现），再从 t0 起等距取 N 帧；
#   逐帧按身体高度缩放、脚底贴画布底，压掉 Wan 的 zoom 漂移（限幅 ±8%）。
python $S\pick_gait_frames.py --src <ComfyUI>/output/Wan_frames --out <中间帧目录> `
  --frames 4 --report pick.json
#   正常输出形如：period=17 picked=[9,13,17,22] wrap_vs_avg=1.301
#   报 "no period found" 说明动作幅度太小 —— 回去把立绘改成宽步幅（见「六条硬约束」第 3 条）

# 第 2 步：落到引擎画布 + 算验收数字 + 写 manifest/sidecar
python $S\fit_and_validate.py --src <中间帧目录> --out-dir <工程目录>/enemies/grunt `
  --asset enemy_grunt_walk_east --canvas 48x56 --anchor bottom --fps 8 --loop --facing east `
  --allow-offcenter --manifest-root <工程目录>
```

`fit_and_validate.py` 打印 PASS/FAIL 并逐条列出问题（画布、四角、边距、锚点、循环 IoU/质心、
末帧是否为空、左右镜像差）。同目录多套动画（walk_east/south/north + die）时它会把
`manifest.json` 自动合并成 `{"assets": [...]}`，`files` 写成相对 `--manifest-root` 的路径。

常用开关：

| 开关 | 什么时候用 |
|---|---|
| `--passthrough` | 源已经是最终画布（程序化生成、或上一步已归一）——**别再缩一次** |
| `--symmetrize` | 装饰件/徽章要求左右对称（AI 直出通常差 3–12%，镜像平均后为 0） |
| `--require-empty-last` | 死亡套：末帧不透明像素必须 = 0 |
| `--allow-offcenter` | 挥武器/迈步的剪影本来就不居中，别按包围盒居中判 |
| `--allow-touch-edges` | 全屏 FX、满画布爆心（半径 = 半画布）必须贴边 |
| `--grade gamma=0.6,sat=0.9` | 统一调色，只动 RGB 不动 alpha（循环闭合靠掩膜） |

## 六条硬约束（违反必出废片）

1. **内存串行**：Z-Image 与 Wan 不能同时驻留（合计约 30GB > 32GB）。流水线会自动停/启 ComfyUI；手动分步时必须先 `python comfy_ctl.py stop` 再跑 `gen_look.py`。
2. **生成分辨率 ≤ 768×768**：1024 会触发 Windows 共享显存，出图从 32 秒退化到 863 秒。
3. **输入立绘必须是「大动作」姿态**：站姿或小步幅输入只能得到“轻微晃动”（Wan 会照着首帧画完 49 帧）；走路要**宽步幅**——前腿跨远、后腿蹬直、手臂大幅前后摆。
4. **对侧协调要明确写**：用“前腿是右腿、后臂是右臂”这种同侧异向描述，否则会“同手同脚”。
5. **循环闭合靠选区间，不靠提示词**：必须 `length=49`（下限）且挑帧；25 帧通常只覆盖半个步态周期。
6. **一条动画跑完立刻快照 Wan 原始帧**：`ComfyUI/output/Wan_frames` 是固定目录，下一条会把它覆盖掉（本机实测丢过一整套帧，只能重跑）。

## 提示词结构

五类静态模板与各动作的立绘/视频模板见 [EXAMPLES.md](EXAMPLES.md)。骨架：

```
<类型前缀>, <主体>, <视角/构图>, <风格>, <背景>, <约束>
```

- 视角固定用 `three-quarter top-down view facing right`。
- Z-Image Turbo 是蒸馏模型，`guidance_scale=0.0`，**不支持 negative prompt**：所有“不要什么”都要写进正向（`no text`、`no crystal on top`、`no trigger box at the back`）。
- 需要“朝向可读”的机械件（弩炮、炮管、箭头）只写 `facing right` 不够，要写清“剪影指向右、箭口在右端”。
- 道具别选尖锐长条（剑、矛），容易和腿重叠读成“道具被腿挡住”。

## 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--upscale` | `auto` | **交付一律 `never`**（许可红线，见模式①） |
| `--size` | 768 | 生成边长上限；1024 会掉进共享显存 |
| `--length` | 49 | 视频帧数，低于 25 无法闭合 |
| `--frames` | 8 | 图集帧数；小尺寸单位用 4–6 帧短循环更好读 |
| `--seed` | 1234 | 复现用 |
| `--engine` | `a14b` | `5b` 更快但细节糊（动作幅度更大） |
| `--video-width/height` | 480/640 | 比例须匹配画布 3:4，宽高是 16 的倍数 |
| `--no-look-refine` | 关 | 模式②：源图已是最终画风时跳过精修（省 90 秒） |
| `--dest` | 无 | 目标工程的 `assets` 目录，验收后复制成品 |

全集（含 `--project` / `--kind` / `--subject` / `--cutout` / `--control-scale` / `--tolerance` 等）
见 [REFERENCE.md](REFERENCE.md) §4 与 `python scripts\generate.py --help`。

## 验收指标

**序列帧**：`fit_and_validate.py` 全 PASS，另加两项——

| 指标 | 判据 | 在哪看 |
|---|---|---|
| 循环接缝 | `wrap_vs_avg ≥ 1.0`（首帧↔末帧 IoU ÷ 相邻帧 IoU 均值） | manifest 的 `loop_metrics`；<0.9 会顿一下 |
| 动作幅度 | 4 帧两两 IoU 落在 0.5–0.9 | 全 >0.95 = 几乎没动，回第 3 条硬约束改立绘 |

`iou > 0.70` 是 `preview.py` 的粗筛判据，仍可用。**不要**把「首尾帧 IoU ≥ 0.95」当验收线：真实步态
（双腿交替）物理上达不到，实测 4 帧步态是 0.50–0.92；强行凑 0.95 只能复制首帧，循环就废了。
纯发光类循环（只改 RGB 不动 alpha）可以做到 IoU = 1.000，这类用程序化生成，别喂 Wan。

**静态资源**：尺寸对不对、透明通道干净（四角 alpha=0、主体 alpha=255、上/左/右留 1–4 px 边距）、
tile 的接缝差已接近纹理自身粗糙度。

```powershell
python $S\preview.py --static "...\tile\test_tile.png"
python $S\preview.py "...\sprites\hero" --action walk
```

## 排错

症状 → 原因 → 修法见 [FIELD-NOTES.md](FIELD-NOTES.md)：站姿立绘只出晃动、auto-loop 挑到平缓区间、
Wan 输出目录互相覆盖、抠图容差写太小导致包围盒撑爆、Wan zoom 漂移、死亡末帧不透明、
静态件朝向读不出来等 2026-10 实测记录。

## 许可与文档

模型全部可商用：Z-Image / ControlNet / Wan 2.2 / LightX2V LoRA = Apache-2.0，BiRefNet = MIT。
**例外的两处**：`4x-UltraSharp` 权重许可需要自己出示原文（拿不到就别开超分）；ComfyUI 是 GPL-3.0
工具（不影响产出的 PNG）。上架前只需在 Steam 做 AI 内容披露。

用程序化补出来的素材（纯矢量画的弹道、粒子、光环、发光脉动、死亡塌陷）**不含 AI 生成内容**，
交付登记时要把 AI 出图和程序化分开写，两样都不能含糊成“手绘”。

参数全集、部署步骤、许可清单见 [REFERENCE.md](REFERENCE.md)；提示词模板见 [EXAMPLES.md](EXAMPLES.md)。
