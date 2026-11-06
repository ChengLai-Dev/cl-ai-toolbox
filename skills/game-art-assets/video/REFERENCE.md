# 视频线部署细节

本文是 `game-art-video` 的支撑材料，记录环境构成、目录约定与迁移时的关键判断。

## 一、环境构成

| 项 | 值 |
|---|---|
| ComfyUI | **0.36.0**（注意：与图像线的 0.43.0 不同版本） |
| Python | 3.12.0 |
| torch | 2.9.1+cu128 |
| 端口 | 8191（图像线是 8188，可共存于配置但不建议同时跑） |
| 自定义节点 | `h3_simple_ui`（提供 `/h3ui` 出片台） |

**为什么视频线用 0.36 而不是升级到 0.43**：`nodes_minimax_h3.py` 在两个版本间确有差异——
0.43 新增了 `MiniMaxH3LatentUpscaleWithModel` 节点，改用 `comfy.audio.resample` 替代 torchaudio，
新增 `IMAGENET_MEAN` 处理，修改了 inpainting 的 mask 填充逻辑。这些改动对本工作流虽不致命，
但**没有理由去冒这个险**。整体搬迁零版本变化。

## 二、权重清单（37.52 GB）

| 文件 | 大小 |
|---|---|
| `diffusion_models\minimax_h3_fl2va_pruned_int4_convrot_simple.safetensors` | 15.67 GB |
| `text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14.61 GB |
| `vae\minimax_h3_video_vae_fp16.safetensors` | 4.85 GB |
| `loras\minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors` | 1.82 GB |
| `vae\minimax_h3_audio_vae_fp32.safetensors` | 0.56 GB |

`*.safetensors.aria2` 是未下完的残留控制文件，主文件完整可用，可忽略。

## 三、目录约定

```
VideoPipeline\
  comfy\              ComfyUI 0.36 程序
  venv\               Python 3.12 / torch 2.9.1+cu128
  models\             权重
  configs\            minimax_h3-paths.yaml（模型视图）
  runners\            serve.ps1 / gui.ps1
  scripts\            run_test.py（提交 + 轮询）
  workflows\          h3_i2v_knight.json / h3_i2v_knight_v2.json
  custom_nodes\       h3_simple_ui
  input\              首帧参考图
  outputs\minimax_h3\ 出片
  logs\               运行日志
  archive\            历史产出 + 旧文档
```

## 四、两个已发现的环境问题

### 1. 首帧图引用不存在

`h3_i2v_knight.json` 与 `_v2.json` 的节点 7 都写着 `"image": "ref_knight.png"`，
但源沙盒的 `input` 是空的。**这两个工作流在迁移前直接点 Run 就会报找不到图片。**

当前处理：从同类骑士图复制了一份占位首帧。有真正的 `ref_knight.png` 时直接覆盖即可，工作流不用改。

### 2. input 目录结构被 base-directory 覆盖

原启动脚本用 `--base-directory` 指向沙盒根，因此 ComfyUI 实际读的是 `沙盒根\input`（空的），
而 `ComfyUI\input`（254 张图）根本没被用上。现已统一为根目录 `input\`。

## 五、节点可用性

| 节点 | 0.36 状态 |
|---|---|
| MiniMaxH3ImageToVideo | ✅ |
| MiniMaxH3SigmaShift | ✅ |
| MiniMaxH3AddGuide | ✅ |
| MiniMaxH3ReferenceToVideo | ✅ |
| EmptyMiniMaxH3LatentAV | ✅ |
| CreateVideo / SaveVideo / VAEDecodeAudio | ✅ |
| MiniMaxH3LatentUpscaleWithModel | ⚠️ 0.43 才新增，当前工作流未使用，不影响出片 |

## 六、保留的 8GB 启动参数

一个都不能删：

```
--disable-xformers --use-pytorch-cross-attention --disable-pinned-memory --reserve-vram 0.3
```

`--disable-pinned-memory --reserve-vram 0.3` 是内存 offload 的必需项。删掉会 OOM。

## 七、端到端验证记录

提交 `h3_i2v_knight_v2.json`，240 秒完成，ffprobe 验证：

```
codec: h264 + aac    尺寸: 480x640    帧数: 73    帧率: 24/1    时长: 3.04s
```

画质、音轨、帧数、分辨率均符合预期。
