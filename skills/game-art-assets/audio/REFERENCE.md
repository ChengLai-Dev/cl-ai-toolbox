# 音效与 BGM 生成 · 实测数据与参数参考

本文件是 [SKILL.md](SKILL.md) 的支撑材料：全部数字来自本机真实运行（RTX 5060 8GB），
不是论文数据或估算。

## 1. 环境

| 项 | 值 |
|---|---|
| 部署路径 | `D:\AIGamePipeline\AudioPipeline` |
| GPU | RTX 5060，8123 MiB（torch 显示 7.93 GB），sm_120 |
| 驱动 | 617.42 |
| 显存实测可用 | 6.87 GB（`torch.cuda.mem_get_info()` = 6980/8123 MiB） |
| Python | 3.12.0 |

| venv | torch | 用途 |
|---|---|---|
| `envs\ace-step` | 2.7.1+cu128 | ACE-Step 1.5（上游 pin 死） |
| `envs\moss-sfx` | 2.9.0+cu128 | MOSS-SoundEffect v2.0（上游 pin 死） |

两套依赖互斥，混用直接崩。均验证过 `(12,0)` 计算能力与 bf16 matmul。

目录沿用 ImagePipeline 约定：
`vendors\`（上游源码，未改一行）、`models\`、`envs\`、`scripts\`、`configs\`、`logs\`、`outputs\`。

## 2. 模型清单

### ACE-Step 1.5（BGM）→ `models\ace-step\`，32 文件 / 7.18 GB

| 组件 | 大小 |
|---|---|
| DiT（2B turbo） | 4566 MB |
| VAE | 321.8 MB |
| 文本编码器 Qwen3-Embedding-0.6B | 1136.4 MB |
| LM `acestep-5Hz-lm-0.6B` | 1264.4 MB |

未装 `acestep-5Hz-lm-1.7B`（3.71 GB）——8GB 档用不到。
`ACESTEP_CHECKPOINTS_DIR` 由脚本自动指向 `models\ace-step`；不设的话上游会把
`checkpoints\` 建到**当前工作目录**。

### MOSS-SoundEffect v2.0（音效）→ `models\moss-sfx\`，18 文件 / 10.46 GB

| 组件 | 大小 |
|---|---|
| DiT（1.3B） | 5401.87 MB |
| 文本编码器（Qwen3-0.6B，两分片） | 3281.77 + 593.5 MB |
| DAC VAE | 1417.6 MB |
| tokenizer / scheduler / 配置 | 约 15 MB |

`model_index.json`：`dit_variant=1.3B`、`sample_rate=48000`、`max_inference_seconds=30`、
`vae_type=dac`、`text_encoder_type=qwen3`。

## 3. 实测性能

### 3.1 ACE-Step BGM

命令 `generate_bgm.py --preset trance_140 --name test_trance_180 --seed 42`
（180 秒 / 140 BPM / F minor / 8 步 / shift 3.0 / int8 / CPU offload / 0.6B LM）

| 阶段 | 耗时 |
|---|---|
| DiT 加载 + 量化 | 22.4 s |
| LM 加载 | 16.0 s |
| LM 生成 CoT 元数据 | 6.17 s |
| LM 生成音频语义码 | 28.73 s |
| DiT 扩散（8 步） | 3.19 s（0.40 s/步） |
| VAE 分块解码 | 约 6.5 s |
| **端到端** | **49.4 s** |

峰值显存 **5.89 GB**，生成后剩余 2.31 GB，速率 16.5 s / 分钟音频，产出 48 kHz 立体声 FLAC 19.29 MB。

60 秒 BGM 端到端 68.6~69.2 s（含加载）。**显存富余，可放心拉到 4~6 分钟。**

### 3.2 MOSS 音效（30 秒窗口）

| 步数 | 耗时区间 | 说明 |
|---|---|---|
| 20 | 394.5 ~ 645.6 s | 草稿，可能塌成静音 |
| 50 | 576.5 ~ 722.9 s | 生产档 |
| 100 | 1036.8 s | 更细腻的说法不成立，见第 4 节 |

显存：生成阶段峰值 **7.99 GB**，加载阶段峰值 **9.88 GB**（`from_pretrained` 一次性把三个组件读上卡），
生成后剩余 2.28 GB。

### 3.3 批量

`batch_generate.py configs\batch-demo.json`（2 音效 + 1 条 60 秒 BGM）三次运行均 `成功 3 / 失败 0`。
各任务由对应 venv 的解释器起独立进程，显存逐条释放。

## 4. 关键实验记录

### 4.1 去噪窗口：只有 30 秒可用（用户实听确认）

| 窗口 | 输出 | 判定 |
|---|---|---|
| **30 秒**（模型原生） | 清脆刀剑碰撞，有明确起振与衰减 | **可用** |
| 3~12 秒 | 连续金属噪声，辨不出是什么 | 不可用 |

代价对照：4 秒窗口 100 步只需 85.1 s，比 30 秒窗口快 8 倍，但产出的是噪声。
这是「用可用性换速度」，方向错误。

注：我曾用「包络有起振、有衰减」的指标判定 4 秒窗口已修好，**该判断是错的**——
指标只能证明信号是冲击型，不能证明内容对。教训写入 SKILL.md 反模式。

### 4.2 裁剪：模型把事件放在窗口末尾

上游 `pipeline_moss_soundeffect.py` 最后执行 `audio[:, :, :output_samples]`，永远从第 0 秒裁。
实测事件位置：8 秒窗口 → 0.65 s；30 秒窗口 → **29.5 s**；12 秒窗口 → 0.45 s。

脚本改为：取 10 ms 窗 RMS 的峰值位置，从峰值前 50 ms 起切；峰值太靠末尾时整体左移保住衰减段；
之后再裁掉头部近静音（保留 20 ms 预卷），用静音补齐到目标长度。
`meta.json` 记录 `crop_start_s` 与 `trim_head`。

### 4.3 响度

| 样本 | 原始 RMS | 增益 | 处理后 |
|---|---|---|---|
| 刀剑（峰值型） | -26.1 dBFS | -1.0 dB | 峰值 -1.0，RMS -27.0 |
| 爆炸（密集型） | -3.8 dBFS | **-16.2 dB** | RMS -20.0 |
| UI 点击 | -47 dBFS | +17.4 dB | 峰值 -1.0，RMS -29.6 |

约束是「峰值 ≤ -1 dBFS 且 RMS ≤ -20 dBFS」：峰值型的短音效按峰值拉满，密集噪声型被 RMS 压住。

### 4.4 重击/爆炸：起振是硬伤

| 版本 | 上升（10%→峰值） | 频谱重心 | 1 kHz 以上 |
|---|---|---|---|
| `imp_v2`（改写措辞，50 步） | **92 ms** | 1957 Hz | 29.1% |
| `imp_v3_100`（同措辞，100 步） | **204 ms** | 1020 Hz | 16.2% |
| `imp_test`（旧措辞含 low sub boom） | — | 66 Hz | 0.6% |
| 对照：刀剑 | 4 ms | 5350 Hz | 98.8% |
| 对照：UI 点击 | 4 ms | 2388 Hz | 77% |

三点结论：

1. **步数不是杠杆**：100 步反而更慢更暗。
2. **低频词是陷阱**：`low sub boom` 让 71.9% 能量落到 120 Hz 以下，主频 17~42 Hz，
   笔记本/显示器喇叭完全放不出来（指标却正常：峰值 -8.4 dBFS、RMS -20、无静音）。
   改成 `mid-range thud / sharp transient crack / no sub bass` 后中高频回到 29.1%。
3. **时域后处理能压到 20 ms**（`--gate-above 0.5 --transient-db 9 --highpass 60`），但属于事后修补。

### 4.5 颗粒感是固有色

| 样本 | 谱平坦度 | 8k 以上相对 1-4k |
|---|---|---|
| 刀剑 | 0.320 | -7.1 dB |
| 爆炸 | 0.206 | -2.4 dB |
| UI 点击 | 0.009 | -21.6 dB |

刀剑比爆炸更「噪」，说明颗粒感不是某一类的缺陷，而是 48 kHz + DAC VAE 的整体质感。
像素风格可接受，写实风格会显得粗糙。

### 4.6 可复现性

- 同 seed + 同步数 + 同窗口 + 同裁剪：两次运行 WAV 的 SHA256 完全一致。
- `good_sword_v2`（现行默认）与用户认可的 `len30_s50`：相关系数 **1.0000**，仅差 -0.96 dB。
- 换窗口长度会得到完全不同的样本（4 s vs 30 s 相关系数 0.001），复现必须连 `--max-seconds` 一起固定。

## 5. 脚本与参数

| 脚本 | 作用 |
|---|---|
| `generate_sfx.py` | 音效生成（MOSS） |
| `generate_bgm.py` | BGM 生成（ACE-Step），产物重命名为 `<name>.flac` |
| `batch_generate.py` | 批量，按 `type` 选对应 venv 解释器 |
| `check_audio.py` | 体检：时长/电平/静音/频段/瞬态（`--transient`） |
| `slice_candidates.py` | 诊断：从完整窗口按三种规则各切一版候选 |
| `postprocess_sfx.py` | 后处理：高通/低架/中高频提升/门限/瞬态塑形 |
| `fetch_modelscope.py` / `fetch_parallel.py` | 权重下载（ModelScope 分片 + 断点续传） |

### generate_sfx.py 关键参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--max-seconds` | **30** | 去噪窗口。**不要调小**，调小出噪声 |
| `--steps` | **50** | 20 步只做草稿，可能塌成静音 |
| `--cfg` | 4.0 | 1.0 会跳过负向前向，约 2 倍速、质量下降 |
| `--align` / `--no-align` | 开 | 按峰值对齐裁剪 |
| `--preroll` | 0.05 | 峰值前预卷秒数 |
| `--trim-head` / `--no-trim-head` | 开 | 裁掉头部近静音 |
| `--target-rms` | -20 | 响度上限（峰值固定 -1 dBFS） |
| `--cpu-offload` / `--no-cpu-offload` | 开 | 分阶段换页，峰值 13.06 → 7.99 GB |
| `--save-full` | 关 | 额外保存 30 秒完整窗口，用于诊断 |
| `--compile` | 关 | Windows 无 Triton，打开会报 `TritonMissing` |

## 6. 诊断流程（音效听着不对时）

```
先存完整窗口
  generate_sfx.py --save-full
  ↓
看包络是平的还是有事
  ├─ 平 / 全程有声 → 内容问题：改提示词（去低频词），或换 seed
  └─ 有明显尖峰 → 裁剪问题：
        slice_candidates.py <name>_full.wav --seconds N   # 三种规则各切一版对比
  ↓
量三项指标
  check_audio.py --transient
  ├─ SUB-BASS?（低频>70% 且 250Hz 以上<5%）→ 换措辞，别用后处理硬救
  ├─ 上升 > 50ms → 时域处理（gate + transient）或判定该类别不适合
  └─ 尾部/峰值 > 0.35 → 没有衰减，是持续噪声
```

## 7. 预设

- `configs\sfx-presets.json`：22 条（UI / 战斗 / 脚步 / 门箱 / 法术 / 环境循环 / 怪物）
- `configs\bgm-presets.json`：7 条（trance_140、future_house_124、hardstyle_150、future_bass_150、
  game_boss_battle、game_exploration、game_menu）
- `configs\batch-demo.json`：批量冒烟配置（音效 20 步、BGM 60 秒）

## 8. 偏离台账（相对上游）

1. ACE-Step 权重从 ModelScope 拉（本机 Google 不可达），只取 turbo / vae / Qwen3-Embedding / 0.6B LM。
2. MOSS 的 ModelScope 仓库名是 `OpenMOSS/MOSS-SoundEffect-v2.0`（不带 `-Team`）。
3. MOSS 默认 30 秒窗口在 8GB 卡上是 22 s/步，原样跑一条要 35 分钟——但**不能靠缩窗口提速**，
   只能降步数或接受耗时。
4. 8GB 卡走 ACE-Step 官方 6-8GB 档。
5. ACE-Step「主模型齐全」校验被收窄到实际拥有的四个组件（只收窄范围，缺件仍报错）。
6. Windows 无 Triton，MOSS 的 `@torch.compile` 会抛 `TritonMissing`，用 `TORCHDYNAMO_DISABLE=1` 退回 eager。
7. MOSS 上游 `save_audio()` 依赖 torchcodec（还需 FFmpeg），改用 `soundfile` 写 PCM_16。
8. MOSS 分阶段换页改为默认开启（上游默认关），峰值 13.06 → 7.99 GB。
9. 裁剪改为按能量峰值对齐 + 头部静音裁剪（上游从第 0 秒硬裁）。

`vendors\` 下上游代码全程未改，所有适配集中在 `scripts\`。

## 9. 未完成 / 待验证

| 项 | 状态 |
|---|---|
| 22 条音效预设全量生产 | 未做（约 4.5 小时），只验证了刀剑、UI 点击、脚步、怪物、爆炸几类 |
| `explosion` 新措辞验证 | 未跑；`impact_heavy` 的新措辞已验证有效 |
| 环境循环类（火/雨/风）音质 | 未验证 |
| 像素复古化（降采样/bitcrush） | 未实现，仅讨论 |
| 配音（人声） | 本机未部署，MOSS v2 是音效模型不做语音 |
