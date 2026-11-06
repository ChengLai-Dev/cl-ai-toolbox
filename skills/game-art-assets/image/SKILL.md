---
name: game-art-image
description: 本地双模型（FLUX 3 Image Klein / MOSS-Image）生成 2D 游戏静态美术图，含选型决策、参数档、出图后校验与已知缺陷规避。本机实测 55 张，FLUX 1024² 约 35 秒、MOSS 约 116 秒，8GB 显存可稳定跑。Use when 要生成道具、图标、立绘、地块、场景背景、宣传图，或问「FLUX 和 MOSS 该用哪个」「出图参数怎么设」「背景不干净/有棋盘格怎么办」「中文文字总出错」「出图后怎么验证能不能进引擎」时。
---

# 图像资产生成（FLUX 3 Klein / MOSS-Image）

## 快速开始

```powershell
# 1. 查显存（必须 < 4483 MiB，即总显存 55%）
nvidia-smi --query-gpu=memory.used --format=csv,noheader

# 2. 起服务（二选一，8GB 装不下两个）
cd D:\AIGamePipeline\ImagePipeline
.\venv\Scripts\python.exe .\comfy\main.py --listen 127.0.0.1 --port 8188 `
    --extra-model-paths-config .\configs\flux3-paths.yaml `
    --output-directory <输出目录> --disable-auto-launch
```

就绪判据：`http://127.0.0.1:8188/system_stats` 返回 200。
切换模型：停旧进程 → 等显存 < 4483 MiB → 换 `-paths.yaml` 起新的。**不要两个同时跑。**

## 选型：两个模型强弱项互补，别只用一个

| 资产类型 | 选谁 | 依据 |
|---|---|---|
| UI 图标、像素资产 | **MOSS** | 矢量干净度更好，更接近可用图标 |
| 写实材质、高细节道具 | **FLUX** | 锐度 3.87× |
| 角色立绘（单体） | **FLUX** | 不加装饰、不出多视图 |
| 角色转面参考表 | **MOSS** | 会主动输出三视图/五视图 |
| 场景氛围图、宣传图 | **MOSS** | 构图更大胆，色彩更饱和 |
| 像素场景背景 | **FLUX** | 纵深与像素结构更规整 |
| 中文文字 | **MOSS** | FLUX 会出语义替代错字 |
| 英文文字 | 两者皆可 | 都能拼对 |
| 批量试错迭代 | **FLUX** | 快 3.3× |
| 等距 isometric 资产 | **FLUX** | MOSS 在此组合下出棋盘格 |

## 参数档（用官方模板默认，别乱改）

| | FLUX 3 Klein | MOSS-Image |
|---|---|---|
| 步数 | 16（蒸馏版） | 25 |
| CFG | 1.0 | 2.5 |
| sampler / scheduler | `euler` / `simple` | `er_sde` / `simple` |
| shift | 内置 μ=ln(6.93) | 内置 5.0 |
| 负向提示 | 空 | `nsfw, worst quality, bad anatomy, watermark, jpeg artifact` |
| SLG | — | 单层 `22`，0.0–0.5 |

三条硬结论：

1. **别调 `alpha`（timestep shift）**。实测同 seed 下 `alpha=16` 与默认档肉眼无差别，不是调节杠杆。
2. **负向提示别留空**（MOSS）。空字符串与官方模板不一致。
3. **上采样器默认关掉**。开了两边各自用自家 LLM 改写提示词，A/B 就无意义了。要开须接受 MOSS 耗时 ×3.7。

## 速度（本机实测，含加载与解码）

FLUX 35.0 s / MOSS 116.0 s @1024²；512² 时 11.2 / 37.9 s；竖版 1024×1536 时 51.0 / 172.0 s。
峰值显存 7482–7673 MiB，55 张 0 次 OOM。8 小时窗口：FLUX ≈820 张，MOSS ≈250 张（快 3.3×）。
完整分辨率对照表见 [REFERENCE.md](REFERENCE.md)。

## 出图后必做校验

肉眼看着对 ≠ 能进引擎。

| 检查项 | 判据 |
|---|---|
| 背景纯净度（四角 12% 标准差） | < 3 才算纯色底；干净底 0.5–2，画进内容 > 6 |
| 透明底 | 有 alpha 且边缘无白边 |
| 像素画真伪（零差分比例） | < 0.05 基本不是像素画 |
| 文字正确性 | **中文必过 OCR**，FLUX 会出语义替代错字 |
| 尺寸 | 目标尺寸的整数倍 |

**棋盘格要专门查**：背景区 FFT 周期峰，棋盘格 160–234，正常图 15–137。浅灰底上肉眼极易漏看。

## 三个已知缺陷

1. **MOSS 棋盘格 —— 定向触发**：`isometric` + 「纯色底/单件」组合才触发。实测 16 个道具图标中 3 张触发，其余 13 张背景标准差 < 1，与 FLUX 同级。**不是普遍缺陷。**
2. **FLUX 中文错字 —— 语义替代**：「丹药铺」出成「丹**菊**铺」，`菊` 是真实汉字。好消息是这能用 OCR 拦截后重抽，不是笔画崩坏。
3. **MOSS 多视图倾向**：提示词含 `character sheet` 时按字面输出三视图。要单张立绘走 FLUX。

**地块两者都不合格**：FLUX 边缘是硬切方形不是菱形 footprint；MOSS 菱形正确但带棋盘格。一律要后期 seamless。

## 许可证（商用是硬差异）

| | FLUX 3 Klein | MOSS-Image |
|---|---|---|
| 许可 | FLUX Kommunity License | **Apache-2.0** |
| 商用出图 | 年营收 < $5M | 无限制 |
| 商用微调 | **不允许** | 允许 |

要 LoRA 微调或营收不确定 → **只能走 MOSS**。完整实测数据、指标口径、逐用例表与未做项见 [REFERENCE.md](REFERENCE.md)。

## 反模式

- ❌ 只用一个模型。强弱项互补，单模型必在某类资产上吃亏。
- ❌ 调 `alpha`。实测无效。
- ❌ 开着上采样器做 A/B。两边各自改写提示词，对比无意义。
- ❌ 信一致性直方图指标。MOSS 多视图会压低数值，是假象。
- ❌ 拿裸出图的等距水井当透明底资产。棋盘格会被抠图工具当真实像素。
