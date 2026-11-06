---
name: game-art-audio
description: 本地双模型生成游戏音频：MOSS-SoundEffect v2.0 出音效（Apache-2.0，48kHz 单声道），ACE-Step 1.5 turbo 出 BGM/电音（MIT）。含三条硬约束（去噪窗口必须 30 秒、按能量峰值裁剪、响度双约束）、频段与起振验收、以及「听着是噪音／听不见／很糊」的定位方法。本机实测：音效一条约 12 分钟，180 秒 BGM 约 50 秒。Use when 要做音效、UI 音、打击声、脚步、环境循环音、BGM、电音，或问「音效出来是噪音」「爆炸声没劲/糊/听不见」「BGM 跑调」「音频怎么验收入引擎」「哪个模型能商用」时。
---

# 音效与 BGM 生成（MOSS-SoundEffect / ACE-Step）

## 快速开始

```powershell
cd D:\AIGamePipeline\AudioPipeline

# 先确认显存干净（音效加载瞬间要 9.9GB，超过 8GB 物理显存）
nvidia-smi --query-gpu=memory.used --format=csv,noheader

# 音效（约 12 分钟）
.\envs\moss-sfx\Scripts\python.exe scripts\generate_sfx.py --preset sword_clash --name my_sword

# BGM（180 秒约 50 秒）
.\envs\ace-step\Scripts\python.exe scripts\generate_bgm.py --preset trance_140 --name my_trance

# 必做验收
.\envs\moss-sfx\Scripts\python.exe scripts\check_audio.py --transient outputs\sfx\my_sword\my_sword.wav
```

两套 venv 依赖冲突（torch 2.9.0 / 2.7.1），**不能混用**。

## 选型

| 资产 | 用谁 | 说明 |
|---|---|---|
| 打击、UI、脚步、开门、金币 | **MOSS** | 中高频清晰，起振 4 ms |
| 环境循环（火、雨、风） | **MOSS**（未实测） | 理论上是连续噪声型，但本机尚未验证 |
| 重击、爆炸 | MOSS（有限） | 起振 92~204 ms，只能做远景/风格化 |
| BGM、电音（trance/house/hardstyle/future bass） | **ACE-Step** | 曲风覆盖好，8 步出片 |
| 长曲（>3 分钟） | **ACE-Step** | 显存富余，可拉到 4~6 分钟 |

## 三条硬约束（违反任一条，产出不可用）

1. **去噪窗口必须 30 秒。** `--max-seconds` 调到 3~12 秒虽然快 10 倍，但模型失去时间上下文，
   输出是连续噪声。这是用户实听确认的结论，不是推测。
2. **必须按能量峰值裁剪。** 上游从第 0 秒硬裁；30 秒窗口里事件常出现在 **29.5 秒**，
   硬裁开头拿到的是静音或半截声音。脚本默认已按 10 ms 窗 RMS 峰值对齐，并裁掉头部近静音。
3. **必须做响度双约束。** 峰值 ≤ -1 dBFS、RMS ≤ -20 dBFS。原始输出 RMS 能从 -26 跳到 -3.5，
   噪声型样本会刺耳。

## 参数档（别乱改）

| | MOSS 音效 | ACE-Step BGM |
|---|---|---|
| 去噪窗口 | **30 秒**（模型原生） | — |
| 步数 | **50** | **8** |
| CFG / shift | 4.0 / sigma 5.0 | 强制 1.0 / shift 3.0 |
| 量化 / offload | 分阶段换页（默认开） | int8 + CPU offload |
| 语言模型 | — | 0.6B（1.7B 不装） |
| 输出 | 48 kHz 单声道 WAV | 48 kHz 立体声 FLAC |

## 验收（不可跳过）

`check_audio.py --transient` 会给四项判据：

| 判据 | 合格线 | 不过会怎样 |
|---|---|---|
| 静音占比 | < 95% | 无效文件 |
| 低频占比 | < 70%（且 250 Hz 以上 > 5%） | `SUB-BASS?`：普通喇叭**完全听不见** |
| 上升（10%→峰值） | < 50 ms | 听着「糊」，声音是涌上来的 |
| 尾部/峰值 | < 0.35 | 没有衰减，像持续噪声 |

实测参照：刀剑上升 4 ms、1 kHz 以上占 98.8%；UI 点击 4 ms / 77%；重击 92 ms（同参数 100 步反而 204 ms）。

## 耗时与显存（本机 RTX 5060 8GB）

| 任务 | 耗时 | 峰值显存 |
|---|---|---|
| 音效 50 步 | 10~12 分钟 | 7.99 GB（生成）/ 9.88 GB（加载） |
| 音效 20 步 | 6.6~10.8 分钟 | 同上（**仅草稿，可能塌成静音**） |
| BGM 180 秒 | 49.4 秒 | 5.89 GB，余 2.31 GB |

**加载阶段 9.88 GB 超过物理显存**，跑之前必须关掉浏览器/游戏/其它 AI 进程。
两条线不能同时跑。

## 已知缺陷

1. **重击/爆炸只能做「缓慢涌起」**。加步数无效（100 步 204 ms 比 50 步 92 ms 更慢）。
   要近景写实爆炸 → 这个模型不合适。
2. **低频词会把声音拽进次低频**。提示词写 `low sub boom` / `deep rumble` 会导致
   72% 能量低于 120 Hz、主频 17~42 Hz，喇叭放不出。改写成 `mid-range / cracking / debris` 后
   1 kHz 以上回到 29%。
3. **颗粒感是固有色**，不是 bug。刀剑的谱平坦度 0.32 甚至高于爆炸 0.21。像素风格可接受，
   写实风格会显得粗糙。
4. **ACE-Step turbo 偶发跑调/旋律缺失**，人声与镲片带金属感 shimmer。换 `--seed` 重跑。
5. **ACE-Step 产物默认 UUID 命名**，脚本已重命名为 `<name>.flac`。

## 许可证（商用硬差异）

| | MOSS-SoundEffect | ACE-Step 1.5 |
|---|---|---|
| 许可 | **Apache-2.0** | **MIT** |
| 商用 | 无限制 | 无限制 |
| 注意 | — | 官方免责：生成物与原作的风格相似度需自行核实，建议标注 AI 参与 |

两个都能直接商用，这是当初选它们的主要原因。

## 反模式

- ❌ 调小 `--max-seconds` 换速度。出来的是噪声，不是音效。
- ❌ 用 20 步交付。会塌成「静音 + 一个点击」。
- ❌ 提示词写 `low sub boom`。会被拉进次低频，普通喇叭听不见。
- ❌ 只查「不是静音」就交付。还要查频段与上升时间。
- ❌ 靠 EQ 修「糊」。EQ 改音色不改起振；先量上升时间。
- ❌ 把重击当近景爆炸用。模型给的是 92~204 ms 的涌起。
- ❌ 两套 venv 混用。torch 版本 pin 死且互斥。

参数细节、全部实测数据、诊断工具与偏离台账见 [REFERENCE.md](REFERENCE.md)。
