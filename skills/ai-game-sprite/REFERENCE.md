# 参考手册

## 1. 环境与安装位置

| 项目         | 路径                                          | 说明                   |
| ------------ | --------------------------------------------- | ---------------------- |
| 流水线       | `D:\Code\opencode-workspace\ai-game-pipeline` | 脚本、模型、Godot 项目 |
| ComfyUI      | `D:\Code\ComfyUI\ComfyUI-0.36.0`              | 视频生成运行时         |
| ComfyUI venv | `D:\Code\ComfyUI\venv`                        | 已装 torch 2.9.1+cu128 |
| Godot        | `D:\Code\Godot\godot.exe`                     | 4.7.2                  |
| ffmpeg       | `D:\Software\ffmpeg\ffmpeg.exe`               | 预览视频用             |

硬件基线：RTX 5060 8GB（sm_120）+ 32GB RAM。下列耗时都是这台机器上的实测值。

路径可用环境变量覆盖：`AI_GAME_PIPELINE_ROOT`、`AI_GAME_COMFY_DIR`、`AI_GAME_GODOT`。

## 2. 模型清单

### Z-Image（立绘）

| 文件                                            | 大小  | 位置                                   |
| ----------------------------------------------- | ----- | -------------------------------------- |
| `z_image_turbo-Q6_K.gguf`                       | 5.5GB | `ai-game-pipeline\models\z-image-gguf` |
| `z_image_turbo-Q4_K_M.gguf`                     | 5.0GB | 同上                                   |
| `config.json`                                   | —     | 同上（架构配置，必需）                 |
| `text_encoder/model-0000X-of-00003.safetensors` | 7.5GB | `models\z-image-turbo\text_encoder`    |
| `vae/diffusion_pytorch_model.safetensors`       | 160MB | `models\z-image-turbo\vae`             |
| `tokenizer/`                                    | —     | `models\z-image-turbo\tokenizer`       |
| `scheduler/` + `model_index.json`               | —     | `models\z-image-turbo`                 |

### Z-Image ControlNet（姿势精修）

| 文件                                                    | 大小  | 位置                                |
| ------------------------------------------------------- | ----- | ----------------------------------- |
| `Z-Image-Turbo-Fun-Controlnet-Union.safetensors`        | 3.0GB | `models\z-image-controlnet`         |
| `config.json`                                           | —     | 同上（架构配置，必需）              |

### Wan 2.2（动画）

| 文件                                                        | 大小   | ComfyUI 位置              |
| ----------------------------------------------------------- | ------ | ------------------------- |
| `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`          | 13.3GB | `models\diffusion_models` |
| `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`           | 13.3GB | `models\diffusion_models` |
| `wan2.2_ti2v_5B_fp16.safetensors`                           | 9.3GB  | `models\diffusion_models` |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors`                    | 6.4GB  | `models\text_encoders`    |
| `wan_2.1_vae.safetensors`                                   | 242MB  | `models\vae`（A14B 专用） |
| `wan2.2_vae.safetensors`                                    | 1.3GB  | `models\vae`（5B 专用）   |
| `wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors` | 1.2GB  | `models\loras`            |
| `wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors`  | 1.2GB  | `models\loras`            |

## 3. 脚本职责

| 脚本                  | 作用                           | 关键参数                                                                             |
| --------------------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| `run_pipeline.py`     | 编排五步，自动启停 ComfyUI     | `--character --action --engine --seed --frames --length --skip-look --no-controlnet` |
| `gen_look.py`         | Z-Image 文生图 / ControlNet    | `--character --prompt --width --height --steps --seed --control-image`               |
| `run_wan_a14b.py`     | A14B 双 Expert + 4 步 LoRA     | `--image --action --length --seed --width --height`                                  |
| `run_wan.py`          | 5B 单模型                      | 同上                                                                                 |
| `import_frames.py`    | 抽帧、抠图、循环检测、脚底锚定 | `--character --src --action --count --auto-loop --min-loop --tolerance --use-last`   |
| `pack_atlas.py`       | 拼图集、写 manifest            | `--character`                                                                        |
| `device_scheduler.py` | 8GB 显存下的组件搬运调度       | 无（`gen_look.py` 内部启用）                                                         |
| `make_control.py`     | 生成 ControlNet 控制图         | `--src --out --mode canny/letterbox --size`                                          |
| `edge_control.py`     | Canny 边缘图 / letterbox 工具  | 无（被上面两个脚本引用）                                                             |
| `test_controlnet.py`  | ControlNet 独立验证脚本        | `--size --steps --quant --scale --style edge/silhouette --no-control`                |
| `gen_frames.py`       | 程序化 / 占位帧（后备）        | `--character --mode programmatic/ai/synthetic`                                       |
| `download_models.py`  | ModelScope 下载 Z-Image        | `--only zimage/gguf/all`                                                             |
| `env_check.py`        | 环境自检                       | 无                                                                                   |

### 3.1 标准流程（`run_pipeline.py` 默认）

```
1. gen_look.py --character <角色>_base          纯文生图出基础立绘（姿势来源）
2. make_control.py --src <角色>_base            由基础立绘生成 Canny 控制图
3. gen_look.py --character <角色> --control-image  ControlNet 精修立绘
4. run_wan_a14b.py --image <角色>.png            Wan 生成 49 帧动作视频
5. import_frames.py + pack_atlas.py             抽帧、抠图、循环检测、打图集
```

第 1 步也可以用 `--look-src <png>` 换成手画的立绘，这样第 2 步的控制图就来自你的手稿。

### 3.2 ControlNet

| 项目       | 值                                                                                 |
| ---------- | ---------------------------------------------------------------------------------- |
| 模型       | `models\z-image-controlnet\Z-Image-Turbo-Fun-Controlnet-Union.safetensors`         |
| 大小       | 3.0GB                                                                              |
| 管线类     | `diffusers.pipelines.z_image.pipeline_z_image_controlnet.ZImageControlNetPipeline` |
| 显存调度   | `device_scheduler.py`（与 transformer 共享模块，不能用 accelerate offload）        |
| 控制图     | `make_control.py --mode canny` 生成的黑底白线图，**必须正方形**                    |
| 接入方式   | `gen_look.py --control-image <png> --control-scale <float>`                        |
| 开关       | `run_pipeline.py` 默认开启，`--no-controlnet` 退回纯文生图                         |
| 实测       | 立绘 512×512/8 步：60.5 秒（无 ControlNet 为 31.9 秒）                             |
| 收益       | 循环闭合 iou 0.742 → 0.760；抠图干净度大幅改善                                     |

**只作用于立绘阶段**，Wan 视频阶段没有任何控制通道。

能力边界：控制图默认由基础立绘反推，所以 ControlNet 钉死的是基础立绘已有的姿势，
**不能凭空造出姿势**。要按指定姿势生成，只能手画或程序生成基础立绘再 `--look-src`。

## 4. 关键参数

### 立绘（Z-Image）

| 参数       | 推荐                             | 说明                                 |
| ---------- | -------------------------------- | ------------------------------------ |
| 分辨率     | 768×768                          | 1024 会触发共享显存，慢 6 倍         |
| steps      | 8                                | Turbo 蒸馏模型，8 步足够             |
| guidance   | 0.0                              | Turbo 无 CFG，不支持 negative prompt |
| 提示词结构 | 视角 + 动作 + 服装 + 背景 + 风格 | 必须写清动作中姿态                   |
| 设备调度   | `device_scheduler.py`            | 不调度则整个去噪循环跑在 CPU 上      |

### 动画（Wan）

| 参数      | A14B      | 5B      |
| --------- | --------- | ------- |
| length    | 49        | 49      |
| 分辨率    | 480×832   | 480×832 |
| steps     | 4（LoRA） | 20      |
| cfg       | 1.0       | 5.0     |
| sampler   | euler     | uni_pc  |
| scheduler | simple    | simple  |
| shift     | 5.0       | 8.0     |

### 图集

| 参数          | 默认    | 说明                                            |
| ------------- | ------- | ----------------------------------------------- |
| `--count`     | 8       | 帧数；8 帧 @10fps ≈ 0.8 秒循环                  |
| `--auto-loop` | 开启    | RGB 特征 + 镜像惩罚找闭合区间                   |
| `--min-loop`  | 16      | 最小循环区间长度                                |
| `--tolerance` | 250     | 背景容差 sum\|Δ\|，要能覆盖地面阴影与地平线色带 |
| 画布          | 192×256 | 改 `config.py` 的 `FRAME_W/FRAME_H`             |

### 低分辨率测试档

| 阶段     | 生产值  | 低分辨率档 | 像素比 | 实测耗时                 |
| -------- | ------- | ---------- | ------ | ------------------------ |
| 立绘     | 768×768 | 512×512    | 1/2.25 | 29-32 秒（含 20 秒装载） |
| 视频     | 480×640 | 240×320    | 1/4    | 60-70 秒（49 帧）        |
| 整条链路 | ~3 分钟 | —          | —      | ~110 秒                  |

- 视频宽高必须是 16 的倍数，比例取 3:4 与图集画布 192×256 一致
- `length` 不要压：49 是循环闭合的下限
- 240×320 画面明显变糊，只适合验证链路通不通，不适合判断成片质量

## 5. 抠图：为什么必须用洪水填充

纯色差阈值去不掉地面阴影。实测色值（sum\|ΔR\|+\|ΔG\|+\|ΔB\| 口径）：

| 区域           | 颜色              | 距背景  |
| -------------- | ----------------- | ------- |
| 背景           | (236, 240, 245)   | 0       |
| 地面阴影       | (189, 187, 185)   | 160     |
| 地平线色带     | (173, 172, 172)   | 204     |
| 白鞋 / 白信封  | (255, 255, 255)   | 44      |
| 黑色描边       | (0, 0, 0)         | 721     |

阈值要 >204 才能吃掉色带，但那样白鞋（44）会跟着被吃掉——纯色差无解。

`gen_frames.remove_background()` 改成结构判断：

1. 只把**低饱和**像素当背景候选。绿衣/棕包/肤色饱和度高，天然排除；黑描边饱和度低但色差大，也排除。
2. 在候选里做**从画布边界的洪水填充**。背景、地面阴影、地平线色带互相连通且贴着边界，会被整片冲掉。
3. 角色的白鞋、白信封被黑色描边封闭，与边界不连通，因此保留。

实现是纯 numpy（不引入 scipy），每轮向四邻域各扩一格，收敛即停。
实测 240×320 帧 **8-17 毫秒/帧**，比原来的逐像素 Python 循环快约 100 倍。

残留会连锁污染下游：色带撑满联合包围盒 → 角色在图集里被缩得比实际小；
残留像素也污染 `frame_vector` 的姿态特征 → 循环检测 iou 被拉低。
修抠图后 iou 从 0.617 提升到 0.760。

## 6. 设备调度：8GB 显存下为什么不能自己搬

三个重模型单看都塞不进 8GB：

| 组件         | 占用   | 说明                          |
| ------------ | ------ | ----------------------------- |
| text_encoder | 7.67GB | Qwen3 36 层 bf16              |
| transformer  | 4.75GB | GGUF Q4_K_M                   |
| controlnet   | 2.96GB | Fun-Controlnet-Union bf16     |

所以同一时刻只让一个重模型驻留显存，其余常驻内存，按需搬运。

两个坑：

1. **不能用 diffusers 的 `enable_model_cpu_offload()`**。accelerate 的 `CpuOffload.pre_forward` 里有 `if current_device == self.execution_device: return` 的短路；Z-Image 的 controlnet 与 transformer **共享** `all_x_embedder` / `noise_refiner` / `context_refiner` / `rope_embedder` / `t_embedder`（见 `ZImageControlNetModel.from_transformer`）。controlnet 先上显存会让 transformer 的「首个参数」显示为 cuda，accelerate 于是认为权重已在目标设备而跳过搬运，transformer 本体留在 CPU → `F.linear` 报 device mismatch。纯 txt2img 管线没有 controlnet，不共享模块，不复现此 bug。
2. **纯文生图路径也必须显式调度**。diffusers 的 `DiffusionPipeline` 不会自动把组件搬上 GPU，`_execution_device` 在所有组件都在 CPU 时就返回 `cpu`，整个去噪循环会跑在 CPU 上（6B 模型实测几十分钟起，显存占用为 0）。`device_scheduler.py` 对两条路径统一负责。

调度策略（去噪循环内 controlnet 与 transformer 交替调用）：

```
text_encoder 编码   -> 只有 text_encoder 在显存
vae 编码控制图     -> 只有 vae 在显存
controlnet 前向     -> 只有 controlnet 在显存
transformer 前向    -> 只有 transformer 在显存
vae 解码输出       -> 只有 vae 在显存
```

注意：纯文生图没有 controlnet，回不到 `cn_post`，transformer 必须在 text encoder
编码结束时就搬回显存，否则去噪整段跑在 CPU 上。

## 7. 验收指标

`import_frames.py --auto-loop` 会打印：

```
loop segment: [12, 30) of 49  (iou=0.622)
```

- `iou` 越高越好，>0.70 可用
- 更可靠的验收：末帧→首帧像素差异 / 平均相邻帧差异 < 1.0 即平滑

`scripts/preview.py` 会同时给出 iou 上下文、wrap/avg 比值和 gif 预览：

```powershell
python scripts\preview.py "D:\Code\opencode-workspace\ai-game-pipeline\game\assets\sprites\hero" --action walk
```

## 8. 排错

| 症状                   | 根因                      | 处理                                            |
| ---------------------- | ------------------------- | ----------------------------------------------- |
| 立绘 300+ 秒           | 内存被 ComfyUI 或游戏占用 | 关掉其他程序；确认 ComfyUI 已停                 |
| 立绘 800+ 秒           | 分辨率 1024 触发共享显存  | 降到 768                                        |
| 立绘极慢且显存占用为 0 | 模型没上 GPU              | 确认 `gen_look.py` 走了 `device_scheduler`      |
| 动作幅度小             | 输入立绘是站姿            | 立绘改动作姿态                                  |
| 同手同脚               | 立绘解剖错误              | prompt 写“前腿是右腿、后臂是右臂”，出 4 seed 挑 |
| 循环顿挫               | 区间未闭合                | `length=49` + `--auto-loop`                     |
| 帧脚残留灰色阴影/色带  | 抠图容差不够              | 调大 `--tolerance`（默认 250）                  |
| `value_not_in_list`    | 模型不在 ComfyUI 对应目录 | 检查 diffusion_models/text_encoders/vae/loras   |
| `HTTP 400`             | 节点参数或文件名错误      | 用 curl 提交 payload 看 `node_errors`           |
| ComfyUI 连接拒绝       | 进程未启动                | `run_comfyui.bat`                               |
| Godot 报 manifest 缺失 | 资源未导入                | `godot --headless --path game --import`         |

## 9. 许可台账

| 组件                | 许可证             | 商用         | 义务                           |
| ------------------- | ------------------ | ------------ | ------------------------------ |
| Z-Image Turbo       | Apache-2.0         | 允许         | 再分发模型时保留声明           |
| Z-Image ControlNet  | Apache-2.0         | 允许         | 同上                           |
| Wan 2.2 全系        | Apache-2.0         | 允许         | 同上                           |
| LightX2V LoRA       | Apache-2.0         | 允许         | 同上                           |
| ComfyUI             | GPL-3.0            | 允许（工具） | 分发软件本身需开源，不影响产出 |
| diffusers / PyTorch | Apache-2.0 / BSD-3 | 允许         | 保留 notice                    |
| Godot               | MIT                | 允许         | 游戏内附许可文本               |
| Pillow              | MIT-CMU            | 允许         | 保留 notice                    |

**生成物**：上述模型均不主张输出权利，无署名义务，无收入门槛。

**上架前**：

1. Steam Content Survey 申报 Pre-Generated AI 内容
2. 保留人工修改记录（分层文件、prompt 日志）
3. 避免复刻已发行游戏角色形象

**已排除**：SD3.5（$1M 门槛 + 注册 + 署名）、FLUX dev（非商用）、Qwen-Image-2.1（研究许可）、Mixamo（中国区不可用 + 禁训练模型）。

## 10. 换机器部署

```powershell
# 1. 运行时
cd D:\Code\opencode-workspace\ai-game-pipeline
.\tools\setup.ps1

# 2. Z-Image 模型
cd pipeline
..\.venv\Scripts\python.exe download_models.py

# 3. ControlNet 模型
#    下载 Z-Image-Turbo-Fun-Controlnet-Union.safetensors 与 config.json
#    放到 models\z-image-controlnet\

# 4. Wan 模型（ComfyUI 目录）
#    从 ModelScope Comfy-Org/Wan_2.2_ComfyUI_Repackaged 下载
#    注意 allow_file_pattern 会保留 split_files 子目录，需手动移到 models 根目录

# 5. 启动 ComfyUI
D:\Code\ComfyUI\run_comfyui.bat

# 6. 自检
..\.venv\Scripts\python.exe env_check.py
```

启动参数必须含：`--disable-xformers --use-pytorch-cross-attention --lowvram`（sm_120 适配）。

## 11. 已知限制与路线图

| 限制         | 现状              | 解法                                                  |
| ------------ | ----------------- | ----------------------------------------------------- |
| 角色身份漂移 | 长视频会变脸      | 角色 LoRA（需 12GB+）                                 |
| 解剖错误     | 概率性            | Z-Image ControlNet（已部署，默认开启，见 3.2）        |
| 循环不严格   | 近似闭合          | 自动检测已缓解；严格闭合需动作库驱动                  |
| 动作种类     | 靠 prompt 描述    | 骨架驱动：MediaPipe（任意视频）/ CMU BVH（2605 动作） |
| 8GB 显存     | 1024 分辨率不可用 | 换 16GB 可上 Z-Image Base + A14B fp8                  |
| 地面阴影     | 已解决            | 洪水填充抠图（见第 5 节）                             |
| 视频无控制   | Wan 阶段只能抽卡  | 换 Wan Fun-Control 或自建动作层                       |

通用化方向（未实施）：动作层（视频/动作库/程序化）→ 统一骨架 → ControlNet 生成，可消除“抽卡”。
