# 模型资产管线 · 详细资料

## 1. 环境与权重

复用 ImagePipeline 的 ComfyUI 与 venv，不重复安装。ComfyUI 0.34+ 已原生集成 Pixal3D / TRELLIS.2，并移除了非商用的 `nvdiffrast` / `nvdiffrec`。

| 文件 | 大小 | 用途 |
|---|---|---|
| `diffusion_models/pixal3d_int8_convrot.safetensors` | 5.20 GB | 单图主模型 |
| `diffusion_models/pixal3d_multiview_int8_convrot.safetensors` | 5.20 GB | 四视图主模型 |
| `diffusion_models/trellis_2_int8_convrot.safetensors` | 4.89 GB | 结构/稀疏阶段 |
| `clip_vision/dino_v3_L_naf_fp32.safetensors` | 1.13 GB | 图像编码（NAF） |
| `vae/trellis_2_shape_vae_bf16.safetensors` | 1.02 GB | 形状 VAE |
| `vae/trellis_2_texture_vae_bf16.safetensors` | 0.88 GB | 贴图 VAE |
| `geometry_estimation/moge_2_vitl_normal_fp16.safetensors` | 0.62 GB | 相机 FOV（仅单图用） |
| `background_removal/birefnet.safetensors` | 0.41 GB | 去背 |

单图合计约 15.2 GB，加四视图约 20.4 GB。

**许可**：Pixal3D MIT（2026 年中由腾讯改为 MIT）、TRELLIS.2 MIT、MoGe MIT、BiRefNet MIT。输入图版权与成品商品化合规需自行确认。

## 2. 权重下载

国内实测：hf-mirror 单连接会被限速，ModelScope 单文件超过约 5GB 会断流。可靠做法是 aria2c 八线程 + 逐文件 SHA256 校验 + 失败换源。

```powershell
aria2c --file-allocation=none --check-certificate=false `
  --console-log-level=warn --summary-interval=0 `
  --timeout=30 --connect-timeout=15 --max-tries=5 --retry-wait=3 `
  --lowest-speed-limit=500K -x8 -s8 -d <模型目录> -o <文件名> <hf-mirror URL>
```

实测带宽约 8 MB/s。断点续传要加 `--continue=true --allow-overwrite=true --auto-file-renaming=false`。

## 3. 工作流改造（关键）

官方模板是按 ComfyUI 0.33 写的，在 0.43 上直接跑会失败。必须处理三件事：

### 3.1 不能按 widgets_values 位置映射

0.43 的节点新增了输入（`qef`、`fill`、`segmenter`、`resolution`、`viewport_state` 等），位置对不上。正确做法：

1. 连接关系从 UI 的 `links` 读取；
2. 其余输入取当前 schema 的 `default`；
3. 用节点 ID 覆盖模板显式设定的关键参数。

### 3.2 动态下拉框的子输入要带前缀

`RemeshMesh.sign_mode = "solid"` 会额外要求 `fill` 与 `qef`。API 里的键名不是平铺的，而是：

```
"sign_mode": "solid",
"sign_mode.fill": 20.0,
"sign_mode.qef": false
```

写错会得到一个"看起来成功、实际输出被忽略"的提示：`Failed to validate prompt for output 322 ... Output will be ignored`。

### 3.3 无默认值的必填项

- `viewport_state`（LOAD_3D）：传 `{}`。
- `ImageCropToMask.background`（COLOR）：传 `"#000000"`。
- `PrimitiveBoolean/PrimitiveInt/ComfySwitchNode`：schema 无默认，需按模板值覆盖。

### 3.4 四视图工作流的额外处理

官方多视图模板是"一张横向拼图 + 四次裁切"。直接复用会导致**每个视角被单独归一化**，比例失真。本地版改为：

- 4 个 `LoadImage` 直连 `Pixal3DMultiViewConditioning` 的 front/left/back/right；
- 删掉 `SaveImageAdvanced` 输出节点，让裁切链变成孤儿；
- 提交前只保留成品节点的祖先（否则孤儿节点会因缺输入导致整条 prompt 校验失败）。

模板原始裁剪表是横条：`x=0/1669/3182/4728`，宽 `1669/1492/1476/1608`，高 `2688`。自定义拼图后要同步改。

## 4. UE 无头导入

### 4.1 前置

`.uproject` 加入：

```json
{ "Name": "PythonScriptPlugin", "Enabled": true },
{ "Name": "EditorScriptingUtilities", "Enabled": true }
```

### 4.2 调用

编辑器必须关闭：

```
UnrealEditor-Cmd.exe "<工程>.uproject" -run=pythonscript `
  -script="scripts\ue_import.py" -unattended -nopause -nosplash
```

### 4.3 脚本流程

1. `EditorAssetLibrary.delete_directory(DEST)` —— **只接受一个参数**，传三个会 TypeError；
2. `AssetImportTask` 批量导入，`replace_existing=True, save=True`；
3. 把所有资产 `rename_asset` 到 `/Game/Assets` 根，删空目录；
4. 读 `mesh.get_editor_property("nanite_settings")`，结构体是 **`MeshNaniteSettings`**，字段是 `enabled`（不是 `NaniteSettings.enabled`）。

### 4.4 坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 输出被忽略、无报错 | 动态下拉框子输入缺失 | 补 `xxx.sub` 键 |
| UE 里看不到 mesh | 导入建了子目录，网格被平铺到根，用户展开的是空目录 | 全部拍平、删空目录 |
| 三角形数只有 2k | Nanite 网格返回 LOD0 回退网格 | 看 uasset 体积与观感 |
| 导入后贴图/材质缺失 | 只看了顶层文件 | 递归检查，或拍平 |
| 服务端 `OSError 22` | 两个实例写同一个日志文件，句柄失效 | 每个实例独立日志 |

## 5. 多视图渲染参数（回灌用）

| 项 | 值 |
|---|---|
| FOV | 20°（模板固定值） |
| 方位 | 0 / 90 / 180 / 270，仰角 0 |
| 取景 | 四视角**同一相机距离**，对准包围盒中心，禁止逐视角自动取景 |
| 背景 | 纯白，Blender 需把 view transform 设为 Standard，否则白会变灰 |
| 光照 | 均匀、无阴影；**不要用太阳光**，否则颜色被烘暗 |
| 输出 | 每格 1024×1024，或横向条带 4096×1024 |

回灌的定位是"验证链路"，不是"修缺陷"：四张图来自同一网格，信息量不变。

## 6. 实测数据

| 项 | 数值 |
|---|---|
| 单图（木箱/宝箱级） | 约 2 分 15 秒/件 |
| 四视图 | 6 分 53 秒/件 |
| 批量 6 件 | 13 分 40 秒 |
| 峰值显存（单图） | 7518 MiB |
| 峰值显存（四视图） | 7650 MiB |
| 顶点数 | 道具 36–39 万；剑 10.9 万；弓 6.8 万 |
| GLB 体积 | 11–46 MB |
| UE 导入 6 件 | 约 1 分钟 |
| 尺寸换算 | glb 米 → UE 厘米自动转换，无需缩放 |

## 7. 已知缺陷与修法

| 缺陷 | 成因 | 修法 |
|---|---|---|
| 背面糊/穿模 | 单图无背面信息 | 换多视图生成模型（MV-Adapter 类），回灌无效 |
| 脸糊 | 单图 3D 的分辨率上限 | 角色走 MetaHuman 拓扑或手工修 |
| 薄片变厚（剑刃 4.3cm） | 深度场尺度失准，无深度线索时按轮廓尺寸反向猜测 | `fix_slender.py` 归一深度轴（第 9 节） |
| 细长物弯曲（5.3cm/96cm） | 同一个深度场错误的低频漂移，**不在画面内** | 同上 |
| 贴图偏暗 | 渲染光照被烘进颜色 | 只留白色环境光，或输出 albedo |
| 关节/铰链不可动 | 静态网格 | 拆件 + 枢轴，或绑骨 |

## 8. 后续可选

- **MV-Adapter**（ICCV 2025，开源，SDXL 底座）：真正生成几何一致的四视图；需先验证 8GB 与权重许可。
- **碰撞自动化**：`StaticMeshEditorSubsystem` 加 Box / 凸包分解。
- **减面**：场景件 38 万面偏重，Blender 减到 2–5 万再导入。

## 9. 细长物几何修复（fix_slender.py）

剑、弓、杖、枪这类"一个方向远长于另外两个方向"的物体，单图生成后必须过这一步。

### 9.1 根因（实测，非推测）

以 `SM_Sword_01` 为例（10.9 万顶点，长 0.9694m）：

| 观测 | 数值 |
|---|---|
| 输入图轮廓中心线 | 斜率 **0.095°**，全程残差 ≤2.2px —— **输入图本身是直的** |
| 网格"宽"方向中心线残差 | **1.7mm** —— 轮廓面内也是直的 |
| 网格"深"方向中心线残差 | **53.1mm** —— 弯曲全部在深度轴 |
| 刃身中段截面 | 宽 37mm × 厚 **43mm** —— 方棒，不是刃 |
| 护手 / 柄首深度 | 120mm / 73mm（合理值约 20mm / 13mm） |
| 整体比例 | 深度方向被放大 **约 6 倍** |

两个结论：
1. **不是输入图透视问题**。Pixal3D 是像素对齐 + 显式反投影，轮廓会被忠实复制；被"发明"的只有深度。
2. **变厚和变弯是同一个错误**的两个表现：深度场尺度偏大 6 倍，且带一条低频漂移。所以修法也是同一套。

> 推论：正面（贴图面）渲染永远看不出这两个缺陷。验收必须补俯视/侧视，或直接量数。

### 9.2 方法

骨架式广义柱体变形，目标曲线取直线（Deforming generalized cylinders without
self-intersection by means of a parametric center curve, Computational Visual Media 2018, CC-BY）：

1. PCA 求主轴 L；**横轴不能用 PCA 第二/三轴**——刃身截面近正方形时 PCA 会把宽和厚混在一起。改用"与主轴最不平行的世界轴投影到主轴垂面"作为宽度轴，叉积得深度轴。
2. 沿 L 切 200 片，逐片取截面 min/max 中点作中心线（比质心稳，护手质量不会拉偏）。
3. **中值滤波（窗口 41 片）** 剔除护手这类局部结构造成的中点跳变（实测护手两翼会让中点偏 3~4cm，占总长仅 9%，中值滤波整段剔除），再做移动平均（21 片）。
4. 平滑后的中心线减去它的线性拟合 → 曲率归零、整体朝向和长度不变。
5. 判定深度轴：**截面外扩比更小者**（刃身向宽度方向收成尖，深度方向收得少）。实测宽度 36.0、深度 12.8。歧义时用 `--depth-axis a|b` 手动指定。
6. 深度轴绕修正后中心线缩放 `k = 目标厚度 / 中段厚度`；宽度轴不缩放。
7. 法线按 `A=diag(1,1,k)` 的**逆转置**变换，切线按正向变换，保留 w。

实现上**不经过 Blender**：直接改 GLB 里 POSITION / NORMAL / TANGENT 三个 float32 访问器的字节，TEXCOORD_0、索引、贴图、材质 JSON 原样拷贝。这样贴图按构造不会变——重导出才是白模和贴图变暗的来源。

### 9.3 用法

```powershell
python scripts\fix_slender.py --src exports\SM_Sword_01.glb `
    --dst exports\SM_Sword_01_Fixed.glb --target-thickness-mm 8

python scripts\measure_slender.py --glb exports\SM_Sword_01_Fixed.glb --ref exports\SM_Sword_01.glb
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--target-thickness-mm` | 8 | 刃身中段目标厚度；单手剑 6–8、双手剑 8–10、弓臂 15–25 |
| `--bins` | 200 | 沿主轴切片数；短于 0.5m 的物体可降到 120 |
| `--median` | 41 | 中值滤波窗口，**必须宽于护手占的片数** |
| `--smooth` | 21 | 平滑窗口 |
| `--depth-axis` | auto | 自动判定与预期不符时手动指定 |
| `--no-scale` | 关 | 只去弯、不改厚度（想保留原厚度时用） |
| `--scale-only` | 关 | 只归一厚度、不拉直（弧线保留）。**弓/镰刀这类本来就该弯的物体必须用这个**；但弓的轴判定和厚度目标要手动给（中段切到的是握把，不是弓臂），实测自动判轴会挑错，未验证可用 |

### 9.4 实测效果（SM_Sword_01）

| 项 | 修复前 | 修复后 |
|---|---|---|
| 中心线最大偏差 | 53.1mm | **1.04mm** |
| 刃身中段厚度 | 43.1mm | **8.0mm** |
| 中段宽度 | 37.0mm | 37.1mm（不变） |
| 包围盒深度 | 202.8mm | 29.9mm |
| 长度 | 964.5mm | 964.5mm（不变） |
| TEXCOORD_0 哈希 | — | **完全一致** |
| 贴图 3 张哈希 | — | **完全一致** |
| 单件耗时 | — | **< 2 秒**（纯 CPU） |

### 9.5 什么时候该放弃修，改程序化

深度轴归一只能救"比例和直线度"，救不了拓扑。出现下列情况直接做程序化刃身（AI 只做护手、柄、装饰）：

- 刃身需要开血槽、有明确刃口截面（修完是椭圆截面，做不出刃口）
- 需要做 LOD 或减面到万面以内
- 同一把剑要做 3 个以上变体（长度/弧度/刃型不同）

### 9.6 单件导入（不触碰已有资产）

`ue_import_one.py` 与 `ue_import.py` 的区别：**不清空目录**，只导入一个文件、只对本次产物做平铺、平铺后强制 `save_directory`。后者踩过的"拍平后不保存导致材质引用丢失、白模"就是靠这一步规避的。

```powershell
$env:UE_IMPORT_SRC="D:\AIGamePipeline\UEAssetsPipeline\exports\SM_Sword_01_Fixed.glb"
$env:UE_IMPORT_NAME="SM_Sword_01_Fixed"
& "D:\Code\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" `
  "D:\Code\UE Projects\TestProject\TestProject.uproject" `
  -run=pythonscript -script="D:\AIGamePipeline\UEAssetsPipeline\scripts\ue_import_one.py" `
  -unattended -nopause -nosplash
```

