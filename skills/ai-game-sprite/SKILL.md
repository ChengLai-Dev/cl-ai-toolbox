---
name: ai-game-sprite
description: 本地生成 2D 游戏角色序列帧的完整流水线：Z-Image 出基础立绘 → Canny 控制图 → Z-Image ControlNet 精修姿势 → Wan 2.2 图生视频出 49 帧 → 洪水填充抠图 → 循环闭合检测 → Godot 图集。8GB 显存可跑，模型全部 Apache-2.0，产出可商用。Use when 用户要做 2D 角色动画、序列帧、sprite sheet、精灵图、行走/跑步/攻击/待机循环，或提到 AI 生成游戏角色素材、walk cycle、animation frames。
---

# 2D 游戏序列帧生成

## 快速开始

```powershell
# 一条命令跑完五步
python D:\Code\.config\opencode\skills\ai-game-sprite\scripts\generate.py `
  --character hero --action walk --seed 20261021
```

产出：`D:\Code\opencode-workspace\ai-game-pipeline\game\assets\sprites\hero\atlas.png` + `manifest.json`，Godot 可直接播放。

自检环境：`python D:\Code\.config\opencode\skills\ai-game-sprite\scripts\check_env.py`

## 五步流程

| 步骤       | 脚本                                 | 模型                           | 实测耗时     |
| ---------- | ------------------------------------ | ------------------------------ | ------------ |
| 1 基础立绘 | `gen_look.py`（纯文生图）            | Z-Image Turbo 6B (GGUF Q6)     | 30 秒        |
| 2 控制图   | `make_control.py`（Canny）           | 无                             | 1 秒         |
| 3 精修立绘 | `gen_look.py --control-image`        | Z-Image + Fun-Controlnet-Union | 60-70 秒     |
| 4 动画     | `run_wan_a14b.py`                    | Wan 2.2 I2V-A14B（4 步 LoRA）  | 60-140 秒    |
| 5 图集     | `import_frames.py` + `pack_atlas.py` | Pillow                         | 约 5 秒      |

`run_pipeline.py` 已自动串联全部五步，并负责停/启 ComfyUI。
**第 3 步的 ControlNet 是默认开启的，动画序列帧一律走这条流程**：它把姿势/轮廓钉死后再喂给 Wan，实测循环闭合 iou 0.742 → 0.760，抠图残留干净得多。要退回纯文生图加 `--no-controlnet`。

## 五条硬约束（违反必出废片）

1. **内存串行**：Z-Image 与 Wan 不能同时驻留（合计约 30GB > 32GB）。`run_pipeline.py` 已自动停/启 ComfyUI；手动分步时必须先关 ComfyUI 再跑 `gen_look.py`。
2. **立绘分辨率 ≤ 768×768**：1024 会触发 Windows 共享显存，出图从 32 秒退化到 863 秒。
3. **输入立绘必须是动作中姿态**：站姿输入只能得到"轻微晃动"。要跑步就先画跑步姿态。
4. **对侧协调要明确写**：用"前腿是右腿、后臂是右臂"这种同侧异向描述，否则会"同手同脚"。
5. **循环闭合靠选区间，不靠提示词**：必须 `length=49` 且 `--auto-loop`，25 帧通常只覆盖半个步态周期。

## 提示词结构

立绘 prompt 的骨架（顺序照抄这套，验证过效果）：

```
2D hand-drawn cartoon game character sprite, <视角>, <角色：发型/服装/道具>,
<动作中姿态>, the front leg is the RIGHT leg ... the back leg is the LEFT leg ...,
the front arm is the LEFT arm ... the back arm is the RIGHT arm ...,
clean flat colors, bold black outline, plain flat light gray background,
full body, entire body visible, single character, no text, no ground shadow
```

- 视角固定用 `three-quarter top-down view facing right`
- **同侧异向描述不能省**，这是"同手同脚"的唯一解法
- 写 `no ground shadow` 但模型不一定听；抠图阶段会兜住（见 REFERENCE.md「抠图」）
- Z-Image Turbo 是蒸馏模型，`guidance_scale=0.0`，**不支持 negative prompt**，所有意图都要写进正向描述

各动作的完整提示词模板见 [EXAMPLES.md](EXAMPLES.md)。

## 常用参数

| 参数                   | 默认    | 说明                                                   |
| ---------------------- | ------- | ------------------------------------------------------ |
| `--size`               | 768     | 立绘边长（正方形），上限 768                           |
| `--steps`              | 8       | Turbo 蒸馏模型 8 步足够                                |
| `--length`             | 49      | 视频帧数，低于 25 无法闭合                             |
| `--frames`             | 8       | 图集帧数，8 帧 @10fps ≈ 0.8 秒循环                     |
| `--seed`               | 1234    | 复现用                                                 |
| `--engine`             | a14b    | `5b` 更快但细节糊（75 秒，动作幅度更大）               |
| `--video-width/height` | 480/640 | 视频分辨率，比例须匹配图集画布 3:4，宽高须是 16 的倍数 |
| `--control-scale`      | 0.75    | ControlNet 强度，0.75 稳定，0.45 会让道具漂移          |
| `--tolerance`          | 250     | 背景容差 sum\|Δ\|，**不要调回 60**                     |
| `--no-controlnet`      | 关      | 跳过 ControlNet 精修（不推荐用于动画序列帧）           |
| `--look-src`           | 无      | 把现成的图当 ControlNet 的基础立绘                     |
| `--skip-look`          | 关      | 复用已有 `<character>.png`，只重跑动画与图集           |

## 验收指标

`python D:\Code\.config\opencode\skills\ai-game-sprite\scripts\preview.py <sprite_dir> --action walk` 会输出 gif 与两项指标：
`iou > 0.70` 可用；`wrap/avg < 1.0` 表示末帧接首帧比普通帧间过渡还平滑。
加 `--src <视频帧目录>` 可一并算出循环区间。

## 排错速查

| 症状                     | 处理                                                     |
| ------------------------ | -------------------------------------------------------- |
| 出图 > 5 分钟            | 内存被占；关掉游戏/浏览器，或先停 ComfyUI                |
| 出图极慢且显存占用为 0   | 模型没上 GPU；确认 `gen_look.py` 走了 `device_scheduler` |
| 动作幅度小               | 立绘不是动作姿态；改 prompt 重出                         |
| 同手同脚                 | prompt 加同侧异向描述，出 4 个 seed 挑                   |
| 循环顿挫                 | 确认 `--length 49 --auto-loop`，看日志 `loop segment`    |
| 帧脚残留灰色阴影/色带    | 抠图容差不够，调大 `--tolerance`（默认 250）             |
| `CUDA out of memory`     | 降 `--length` 或分辨率                                   |
| ComfyUI 连接拒绝         | 手动启动 `D:\Code\ComfyUI\run_comfyui.bat`               |

## 许可与文档

模型全部 Apache-2.0：无收入门槛、无注册、无署名义务，上架前只需在 Steam 做 AI 内容披露。
提示词模板与实战记录见 [EXAMPLES.md](EXAMPLES.md)，参数全集、部署步骤、许可清单、已知限制见 [REFERENCE.md](REFERENCE.md)。
