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

多工程并存时用 `generate.py --project <name>` 给落盘名加前缀（`<project>__<character>`），
用 `--dest <工程>\assets` 把验收过的成品复制进目标工程；两者都不给时行为与旧版一致。

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

### 后处理模型（静态资源模式用）

| 文件                              | 大小   | ComfyUI 位置                    | 许可      |
| --------------------------------- | ------ | ------------------------------- | --------- |
| `birefnet.safetensors`            | 424MB  | `models\background_removal`     | MIT       |
| `lucida.safetensors`              | 844MB  | `models\background_removal`     | MIT       |
| `4x-UltraSharp.pth`               | 64MB   | `models\upscale_models`         | BSD-3 系  |

- **BiRefNet**：语义分割抠图，不依赖背景颜色假设，渐变/彩色/纹理背景都能抠。
  ComfyUI 0.36.0 内置节点 `LoadBackgroundRemovalModel` + `RemoveBackground`，直接吃 `background_removal` 目录里的 safetensors。
- **Lucida**：ToonOut 团队的插画专用 BiRefNet 权重，对游戏素材比通用版更对口。
- **4x-UltraSharp**：ESRGAN 血统的 4 倍超分。ComfyUI 用 `UpscaleModelLoader` + `ImageUpscaleWithModel`，
  节点内部已带分块推理（tile=512, overlap=32，OOM 自动折半），768² → 3072² 在 8GB 卡上安全。

下载：`python pipeline\download_models.py --only bgremoval` / `--only upscale`。
HuggingFace 直连国内常超时，脚本会先探测 `huggingface.co` 再退到 `hf-mirror.com`。
xet 传输协议在镜像上会卡住，脚本已强制 `HF_HUB_DISABLE_XET=1`。

## 3. 脚本职责

| 脚本                  | 作用                           | 关键参数                                                                             |
| --------------------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| `run_pipeline.py`     | 编排序列帧流程，自动启停 ComfyUI | `--character --action --engine --seed --frames --length --skip-look --no-controlnet --from-image --no-look-refine --cutout` |
| `gen_look.py`         | Z-Image 文生图 / ControlNet    | `--character --prompt --width --height --steps --seed --control-image --out`          |
| `run_wan_a14b.py`     | A14B 双 Expert + 4 步 LoRA     | `--image --action --length --seed --width --height`                                  |
| `run_wan.py`          | 5B 单模型                      | 同上                                                                                 |
| `import_frames.py`    | 抽帧、抠图、循环检测、脚底锚定 | `--character --src --action --count --auto-loop --min-loop --tolerance --use-last --cutout-mode` |
| `pack_atlas.py`       | 拼图集、写 manifest            | `--character`                                                                        |
| `post_process.py`     | 静态资源后处理（放大/抠图/无缝化） | `--src --out --upscale --cutout --seamless --target`                              |
| `prep_source.py`      | 模式②输入归一化               | `--src --out --size --cutout`                                                        |
| `comfy_client.py`     | ComfyUI HTTP 客户端（共用）     | 无（被 Wan / post_process 引用）                                                     |
| `comfy_ctl.py`        | ComfyUI 启停控制               | `start` / `stop` / `status`                                                          |
| `device_scheduler.py` | 8GB 显存下的组件搬运调度       | 无（`gen_look.py` 内部启用）                                                         |
| `make_control.py`     | 生成 ControlNet 控制图         | `--src --out --mode canny/letterbox --size`                                          |
| `edge_control.py`     | Canny 边缘图 / letterbox / 无缝化 | 无（被上面几个脚本引用）                                                           |
| `test_controlnet.py`  | ControlNet 独立验证脚本        | `--size --steps --quant --scale --style edge/silhouette --no-control`                |
| `gen_frames.py`       | 程序化 / 占位帧（后备）        | `--character --mode programmatic/ai/synthetic`                                       |
| `download_models.py`  | ModelScope 下载 Z-Image / HF 下载后处理模型 | `--only zimage/gguf/bgremoval/upscale/all`                       |
| `env_check.py`        | 环境自检                       | 无                                                                                   |
| `pick_gait_frames.py` | **交付层**：按步态周期挑帧 + 逐帧尺寸归一 | `--src --out --frames --min-t --max-t --tol --report`（见 §12.1） |
| `fit_and_validate.py` | **交付层**：归一到目标画布/锚点 + 校验 + 写 manifest | `--src --out-dir --asset --canvas --anchor --fps --loop --facing`（见 §12.2） |

### 3.1 三条流程

**模式③（文生序列帧，`run_pipeline.py` 默认）**

```
1. gen_look.py --character <角色>_base          纯文生图出基础立绘（姿势来源）
2. make_control.py --src <角色>_base            由基础立绘生成 Canny 控制图
3. gen_look.py --character <角色> --control-image  ControlNet 精修立绘
4. run_wan_a14b.py --image <角色>.png            Wan 生成 49 帧动作视频
5. import_frames.py + pack_atlas.py             抽帧、抠图、循环检测、打图集
```

**模式②（静态图生序列帧）**

```
1. prep_source.py --src <源图>                  去背 → 合成纯灰底 → 放进 768×768 正方形画布
2. make_control.py + gen_look.py --control-image   （可选）ControlNet 精修，源图已是成品则跳过
3. run_wan_a14b.py → import_frames.py → pack_atlas.py
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

## 5.1 静态资源流水线

模式①跑四步，全部由 `post_process.py` 承担后三步，顺序固定：

```
Z-Image 出图（≤768，按目标比例）
  → ESRGAN 4x 放大（ComfyUI UpscaleModelLoader + ImageUpscaleWithModel）
  → BiRefNet 抠透明底（ComfyUI RemoveBackground）
  → 缩到目标尺寸
  → 无缝化（仅 tile）
```

**顺序为什么这样定**

| 约束 | 原因 |
|---|---|
| 放大在抠图前 | ComfyUI 的 `LoadImage` 会丢 alpha 通道。先抠后放会把透明边缘糊掉。 |
| 无缝化在缩放后 | 接缝指标要在最终分辨率上量才是真的。 |
| 缩放走预乘 alpha | 直接缩 RGBA 会在半透明边缘串色。`post_process.resize_rgba` 先乘 alpha 缩放再除回来。 |

**抠图节点链的极性（踩过坑，勿改）**

```
LoadImage → LoadBackgroundRemovalModel → RemoveBackground → InvertMask → JoinImageWithAlpha → SaveImage
```

`RemoveBackground` 返回的 mask 是 **1=前景**（`comfy/bg_removal_model.py` 里 `out.sigmoid()`），
而 `JoinImageWithAlpha` 内部会对 alpha 取反（`alpha = 1.0 - resize_mask(...)`）。
所以中间**必须插 `InvertMask`**，否则抠出来是反的。
实测：抠完四角 alpha=0、主体 alpha=254，透明占比 80%。

**ESRGAN 显存**：`ImageUpscaleWithModel` 内部已带分块推理（tile=512, overlap=32），
OOM 时自动折半到 256 再 128。768² → 3072² 在 8GB 卡上安全，实测约 40 秒。

**无缝化算法**（`edge_control.make_seamless`）

```
a = 原图
逐轴做：
  1. 搜一个卷绕偏移 k，让接缝落在原图最平的一对相邻行/列上
  2. r = roll(a, k)
  3. w = 中心带权重（中心 1，两侧 0）
  4. out = r*(1-w) + a*w
```

- `r` 的外边界取自 `a` 的中间相邻行/列，本来就连续
- `r` 的中心正好是 `a` 的上下/左右接缝，不连续
- 用中心带权重把中心换回 `a`、边界保留 `r`，换完该轴即可无缝平铺

**为什么必须搜偏移量**

卷绕 k 之后，输出图的首尾两行取自 `a[n-k]` 与 `a[n-1-k]` —— 接缝粗糙度就是原图里
第 `n-k-1` 对相邻行的差。固定取半张（k=n/2）等于赌一把：实测 cobblestone 纹理上，
固定偏移落在差值 **19.61** 的一对上（同图相邻对的分布：min 5.17 / median 7.39 / max 25.08），
接缝比纹理自身还粗糙，2×2 平铺一眼能看见。

搜一遍 k（限制在中心带内 `[band+1, n-band-1]`，否则原图的接缝会落在权重不足 1 的过渡带上）
就能把接缝落到最平的一对上。实测同一张图：

| | 接缝差 v | 接缝差 h | 接缝/纹理粗糙度 |
|---|---|---|---|
| 固定半张偏移 | 15.80 | 12.68 | **1.99（明显有缝）** |
| 搜索最优偏移 | 4.86 | 4.31 | **0.51（无缝）** |

**两个轴必须分开做，不能把两个方向的权重用 max 合并**：合并后外边界的中点会错用原图内容，
边界反而裂开（实测接缝误差只从 127 降到 94）。逐轴做可证明两轴都连续 ——
先做纵向混合，横向混合只是在列方向做同样的线性组合，不会破坏已建立的纵向连续性（反之亦然）。

验收：接缝差应当**接近或低于**纹理自身粗糙度，而不是接近 0。
例：cobblestone 地块 4.86 vs 内部相邻行差 7.96 = 无缝。
纯渐变图 127 → 0.50。

## 5.2 模式②输入归一化

用户给的静态图要变成能喂 Wan 的立绘，必须过 `prep_source.py`：

```
原图（任意尺寸/任意背景/可能带 alpha）
  → 去背
       · 已有 alpha → 直接用
       · 洪水填充 → 透明占比 < 5% 说明没抠动，退回 BiRefNet
       · BiRefNet
  → 合成纯灰底 (236,240,245)
  → 放进 768×768 正方形画布，缩放 = min(size/h, 0.75*size/w)，居中
```

**为什么必须做**

Wan 的首帧（`start_image`）会锚定整个视频的背景。下游 `import_frames.remove_background`
的抠图要求「四角同色 + 低饱和 + 边界连通」三条同时成立。用户给的图三条都可能不满足，
于是：背景飘 → 抠不干净 → 联合包围盒撑大 → 角色在图集里被缩得比实际小。

合成纯灰底一次性满足全部三条。

**为什么缩放系数是 0.75**

Wan 的输入画布是 480×640（3:4），`WanImageToVideo` 用 `common_upscale(..., "center")` 做中心裁切。
正方形首帧会被裁成 3:4，裁掉左右各 25%。所以角色在正方形画布里最多占 75% 宽、占满高度，
中心裁切后正好完整 —— 这也是模式③提示词里 `wide empty gray margins on the left and right sides`
的作用。两个模式共用同一套版式，`prep_source` 和 `gen_look` 的产物可以互换。

**三条去背分支**（`prep_source.normalize`）

| 源图状况 | 走哪条 | 日志 |
|---|---|---|
| `--cutout none` | 不去背，直接用 | `cutout=none` |
| 源图自带 alpha（RGBA 且有半透明像素） | 沿用原 alpha，不启动 ComfyUI | `cutout=existing-alpha` |
| 平涂低饱和底 | 洪水填充（默认） | `cutout=flood(80%)` |
| 洪水填充抠不动（底色不统一 / 背景高饱和） | 退回 BiRefNet | `cutout=birefnet` |
| `--cutout birefnet` | 直接上 BiRefNet | `cutout=birefnet` |

洪水填充是否生效看**透明像素占比**：低于 5% 说明没抠动（四角底色不统一时 `corner_color` 取的均值
离真实背景太远，色差判据全部失效；背景是高饱和色时 `sat <= 24` 判据直接把背景排除）。

**两条精修分支**（`run_pipeline.py`）

| 源图性质 | 路径 | 开关 | 实测耗时 |
|---|---|---|---|
| 手绘草稿 / 风格参考 / 低完成度 | 归一化 → Canny → ControlNet 精修 → Wan | 默认 | 归一化 + Z-Image 精修 190s + Wan 130s |
| 已是最终画风（AI 出的 / 美术定稿） | 归一化 → 直接喂 Wan | `--no-look-refine` | 归一化 + Wan 120s |

### 5.2.1 分支覆盖实测

七条路径逐个跑过，指标全部达标：

| # | 路径 | 关键日志 | iou | wrap/avg |
|---|---|---|---|---|
| 1 | 模式③ 文生序列帧 | — | 0.748 | 0.734 |
| 2 | 模式② 洪水填充去背 + 不精修 | `cutout=flood(80%)` | 0.768 | 0.771 |
| 3 | 模式② BiRefNet 去背（高饱和蓝底源图） | `cutout=birefnet` | 0.764 | 0.421 |
| 4 | 模式② 源图自带 alpha | `cutout=existing-alpha` | 0.768 | 0.771 |
| 5 | 模式② ControlNet 精修 | `cutout=flood(80%)` + 精修 190s | 0.765 | 0.857 |
| 6 | 模式① 静态 prop / icon / background / portrait / tile | — | 见 §5.1 各表 | — |

> 分支覆盖测试抓到过两个只有走特定分支才会暴露的 bug：
> ① `make_seamless` 固定半张卷绕偏移，接缝落在纹理最差的一对行上（见 §5.1）
> ② `prep_source.birefnet_cutout` 把 PIL Image 对象传给了只接受路径的 `do_cutout`

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
| BiRefNet / Lucida   | MIT                | 允许         | 保留 notice                    |
| 4x-UltraSharp       | BSD-3-Clause 系    | 允许         | 保留 notice                    |
| ComfyUI             | GPL-3.0            | 允许（工具） | 分发软件本身需开源，不影响产出 |
| diffusers / PyTorch | Apache-2.0 / BSD-3 | 允许         | 保留 notice                    |
| Godot               | MIT                | 允许         | 游戏内附许可文本               |
| Pillow              | MIT-CMU            | 允许         | 保留 notice                    |

**已排除**：RMBG-1.4（BRIA 非商用许可，商用需单独购买授权）。
用同为 MIT 的 BiRefNet 替代，功能等价且不破坏「模型全部可商用」这条。

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
| **静态资源一致性** | 一套图标风格会漂 | 只能靠「固定风格前缀 + 固定 seed 家族」逐个挑；根治需 IP-Adapter for Z-Image（不可用）或角色 LoRA（需 12GB+，本机 8GB 不行）。**这是静态模式最实在的天花板** |
| 静态图分辨率 | 生成上限 768      | ESRGAN 4x 放大后缩放（质量够用，但不是原生分辨率）  |
| tile 无缝化   | 接缝连续但有中心十字纹理 | 提示词强调 `uniform detail` / `even lighting` 可减轻 |
| 场景图动起来 | 不支持            | 视差/分层是另一套需求，本 skill 明确排除               |
| **动作幅度取决于立绘** | 站姿/小步幅立绘只出“轻微晃动”（4 帧 IoU 0.93–0.99） | 立绘改宽步幅（FIELD-NOTES §1）；实测可到 0.50–0.79 |
| **首尾帧 IoU ≥0.95 达不到** | 真实步态实测 0.51–0.92 | 改看 `wrap_vs_avg ≥ 1.0`（REFERENCE §12.3）；发光类循环用程序化可得 1.000 |
| **Wan 输出目录会互相覆盖** | `ComfyUI/output/Wan_frames` 是固定路径 | 每条跑完立刻快照（FIELD-NOTES §3） |

通用化方向（未实施）：动作层（视频/动作库/程序化）→ 统一骨架 → ControlNet 生成，可消除“抽卡”。
---

## 12. 交付层：从「图集验收图」到「引擎能用的逐帧素材」（2026-10 新增）

管线自带的 `import_frames.py` / `pack_atlas.py` 是**验收用**的：192×256 画布、8 px padding、
按 `--auto-loop` 挑帧。要进引擎还得做两件事，脚本在 `scripts/` 下。

### 12.1 `pick_gait_frames.py`：按步态周期挑帧

```
python pick_gait_frames.py --src <Wan_frames> --out <中间帧> --frames 4 [--min-t 10 --max-t 28]
```

| 做什么 | 怎么做 |
|---|---|
| 找步态周期 T | 掩膜自相关：`mean IoU(f_i, f_{i+T})` 最大的 T |
| 挑帧 | 从 `t0` 起等距取 `N` 帧；`t0` 选「首尾最像」的那个（接缝最平滑） |
| 逐帧归一 | 按身体高度缩到同一值、脚底贴画布底；缩放限幅 ±8% |
| 输出 | 源分辨率的中间帧 + `--report` 的 json（周期、选中索引、`wrap_vs_avg`）|

`--auto-loop` 挑的是「最相似的一对帧」，会落在动作最平缓的区间；这个脚本换的是「一个周期」。
报 `no period found` = 动作幅度太小，回去改立绘（FIELD-NOTES §1）。

### 12.2 `fit_and_validate.py`：落画布 + 算验收 + 写 manifest

```
python fit_and_validate.py --src <中间帧> --out-dir <工程目录> --asset <asset> \
  --canvas 48x56 --anchor bottom --fps 8 --loop --facing east [--frames 4] \
  [--passthrough] [--symmetrize] [--require-empty-last] [--allow-offcenter] \
  [--allow-touch-edges] [--fill 1.0,1.0] [--margin N] [--grade gamma=0.6,sat=0.8] \
  [--manifest-root <素材根>] [--report j.json]
```

| 参数 | 作用 |
|---|---|
| `--anchor bottom` | 底边水平中心（地面单位/塔基）；`center` = 画布中心（旋转件/空中 FX） |
| `--passthrough` | 源已是最终画布（程序化生成 / 上一步已归一），只清 alpha |
| `--fill fx,fy` | 内容占可用区域的比例（等级标记靠它拉开面积比） |
| `--margin` | 透明边距像素；默认 `clamp(round(min(W,H)*0.05),1,4)` |
| `--symmetrize` | 左右镜像平均（装饰件要求镜像差 ≤2%，AI 直出通常是 3–12%） |
| `--grade` | 统一调色，只动 RGB 不动 alpha（`gamma/sat/val/hue`） |
| `--require-empty-last` | 死亡套末帧不透明像素必须 = 0 |
| `--allow-offcenter` | 剪影不必居中（挥武器/迈步的包围盒本来就不对称） |
| `--allow-touch-edges` | 全屏 FX / 满画布爆心允许贴边 |
| `--manifest-root` | `manifest.json` 里 `files` 的相对根（sidecar 里仍相对本目录） |

校验项（全部会打印，非 PASS 逐条列出）：画布、四角 alpha=0、上/左/右 1–4 px 边距、
底边贴最后一行（或中心对齐）、循环 `iou_first_last` / `centroid_shift` / `wrap_vs_avg`、
末帧是否为空、左右镜像差。结果同时写 `--report`。

### 12.3 循环判据的实测口径

| 素材类型 | 首尾帧 IoU | 用什么判 |
|---|---|---|
| 真实步态（4 帧，双腿交替） | **0.50–0.92** | `wrap_vs_avg ≥ 1.0`（接缝不比普通帧间过渡差） |
| 发光类循环（只改 RGB） | **1.000** | 两种判据都过；这类用程序化，别喂 Wan |
| 死亡套（播一次） | 不适用 | 末帧不透明像素 = 0 |

「IoU ≥ 0.95」对真实步态物理达不到，强行凑只能复制首帧（循环里定格）。
详见 `FIELD-NOTES.md §6`。

### 12.4 环境变量

| 变量 | 作用 |
|---|---|
| `AI_GAME_PIPELINE_ROOT` | 管线根目录；`pick_gait_frames.py` 用它 import 管线的 `remove_background`（拿不到就退回内置的等价实现） |
