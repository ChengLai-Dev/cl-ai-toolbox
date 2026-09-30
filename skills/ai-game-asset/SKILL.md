---
name: ai-game-asset
description: 本地 AI 生成 3D 游戏美术资产的流水线：ComfyUI 出概念图 → Hunyuan3D 出几何 → Blender 减面 → UE 导入。全本地零 API 费用，仅出白模（无 UV/贴图），配合 CC0 动作库做动画。Use when 用户要本地生成 3D 模型/游戏资产、要用 ComfyUI 出模型、提到 Hunyuan3D/图生3D/减面/白模，或要把 AI 资产导入 UE 时触发。
---

# AI 游戏资产流水线（本地白模）

## 能力边界（先读这个）

| 能做 | 不能做 |
|---|---|
| 文字/图片 → 3D 网格（几何） | 出贴图、出 UV |
| 84 万面 → 2 万面减面 | 自动绑定 / 出动画（另接动作库） |
| 道具 / 环境 / 建筑 / blockout | 角色关节处的干净拓扑（需手工 retopo） |

**核心事实**：Hunyuan3D 本地版只输出 `POSITION`（减面后加 `NORMAL`），**没有 UV**，所以导入 UE 后必然是全白的。这是设计取舍，不是 bug。

**硬件前提**：8GB 显存只能跑 shape-only。贴图阶段需 21GB，必 OOM，不要尝试。

---

## 路径配置

```
{COMFY_ROOT}    = D:\Code\ComfyUI                          ComfyUI 安装根
{COMFY_APP}     = {COMFY_ROOT}\ComfyUI-0.36.0              主程序
{PYTHON}        = {COMFY_ROOT}\venv\Scripts\python.exe     venv 解释器
{CHECKPOINTS}   = {COMFY_APP}\models\checkpoints           模型目录
{MESH_OUT}      = {COMFY_APP}\output\mesh                  3D 产物输出
{COMFY_INPUT}   = {COMFY_APP}\input                        图像输入目录
{LAUNCHER}      = {COMFY_ROOT}\run_comfyui.bat             启动脚本
{DECIMATE}      = {COMFY_ROOT}\tools\decimate.py           减面脚本
{ASSETS}        = D:\Code\AI-Assets                        资产总目录
{DECIMATED}     = {ASSETS}\Decimated                       减面成品
{ANIMATIONS}    = {ASSETS}\Animations                      CC0 动作库

{BLENDER}       = C:\Program Files\Blender Foundation\Blender 5.2\blender.exe
{UE_ENGINE}     = D:\Code\UE_5.8\Engine\Binaries\Win64
```

**已安装模型**（`{CHECKPOINTS}`）

| 文件 | 大小 | 用途 |
|---|---|---|
| `hunyuan3d-dit-v2_fp16.safetensors` | 6.86 GB | 3D 生成（完整单文件，含 CLIP-Vision + VAE） |
| `hunyuan3d-dit-v2-mv-turbo.safetensors` | 4.59 GB | 多视图 turbo 版 |
| `sd_xl_base_1.0_0.9vae.safetensors` | 6.46 GB | 概念图 |

---

## 流程概览

```
① 概念图                ② 几何                    ③ 减面
ComfyUI + SDXL          Hunyuan3D shape-only       Blender Decimate
single object,          (8GB 可跑, ~6GB峰值)        84.6万 → 2万面
isolated on white       {MESH_OUT}/*.glb           14.8MB → 1.44MB
                                                        │
                        ┌───────────────────────────────┘
                        ▼
④ 导入 UE              ⑤ 白模处理               ⑥ 动画（可选）
拖拽 GLB 进            统一灰模材质               CC0 动作库 +
Content Browser        M_AI_Placeholder          IK Retargeter
```

---

## 工作流

### 0. 环境自检（每次开新会话先跑）

```powershell
& "{PYTHON}" -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.zeros(1).cuda()+1)"
```

**期望**：`2.9.1+cu128 12.8 True` + 打印出一个张量。

**若输出 `no kernel image is available`** → torch 被降级了，重装：

```powershell
& "{PYTHON}" -m pip install --no-deps --force-reinstall `
  "{COMFY_ROOT}\_wheels\torch-2.9.1+cu128-cp312-cp312-win_amd64.whl" `
  "{COMFY_ROOT}\_wheels\torchvision-0.24.1+cu128-cp312-cp312-win_amd64.whl" `
  "{COMFY_ROOT}\_wheels\torchaudio-2.9.1+cu128-cp312-cp312-win_amd64.whl"
```

> **装任何自定义节点后都必须重跑此自检**。自定义节点的 requirements.txt 会把 torch 拉回 CPU 版。
> **绝不安装 xformers**：预编译 wheel 只支持到 sm_89，会静默降级 torch。

### 1. 启动 ComfyUI

```powershell
& "{LAUNCHER}"
```

浏览器开 `http://127.0.0.1:8188`。

**启动参数不可改**（已写在 launcher 里）：
- `--disable-xformers`
- `--use-pytorch-cross-attention`

### 2. 出概念图

用 SDXL 文生图。**prompt 必须包含**：

```
single object, isolated on white background, front view
```

负面 prompt：`blurry, multiple objects, messy background, text, watermark`

**这个约束很重要**——3D 生成对「单物体 + 白底」的图效果最好，多物体或复杂背景会导致几何崩坏。

### 3. 图生 3D

**推荐用官方模板**：菜单 `Workflow → Browse Templates → 3D → Hunyuan 3D → image_to_model`

| 参数 | 值 |
|---|---|
| `ImageOnlyCheckpointLoader` | `hunyuan3d-dit-v2_fp16.safetensors` |
| `EmptyLatentHunyuan3Dv2.resolution` | 3072 |
| `KSampler.steps` | 20 |
| `KSampler.cfg` | 4–8 |
| `VoxelToMesh.algorithm` | `surface net` |
| `VoxelToMesh.threshold` | 0.6 |
| `VAEDecodeHunyuan3D.octree_resolution` | 256（想更细可 320，吃显存） |

**多视图 turbo 版额外要求**：`cfg` 设 `1.0`，并加 `FluxGuidance` 节点。

产物落 `{MESH_OUT}\*.glb`。

### 4. 减面（必做）

85 万面无法直接进引擎。

```powershell
& "{BLENDER}" --background --python "{DECIMATE}" -- "<输入.glb>" "<输出.glb>" <目标面数>
```

**目标面数参考**

| 用途 | 面数 |
|---|---|
| PC 主角级道具 | 20,000 – 60,000 |
| PC 普通道具 | 5,000 – 20,000 |
| 移动端 LOD0 | 5,000 – 15,000 |
| 远景 / 填充 | 500 – 2,000 |

`decimate.py` 行为：COLLAPSE 算法 + 三角化，自动补 `NORMAL`，导出 GLB。

### 5. 导入 UE

**方式 A：拖拽（首选）**
把 `.glb` 拖进 UE 的 Content Browser → Import All。UE 5.8 内置 glTF 导入器。

**方式 B：Python Console**（`Window → Python Console`，需先启用 `Python Editor Script Plugin`）

```python
import unreal
t = unreal.AssetImportTask()
t.set_editor_property("filename", "D:/Code/AI-Assets/Decimated/xxx.glb")
t.set_editor_property("destination_path", "/Game/AI_Generated")
t.set_editor_property("destination_name", "xxx")
t.set_editor_property("automated", True)
t.set_editor_property("save", True)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
print("IMPORTED:", list(t.get_editor_property("imported_object_paths")))
```

> **不要用 `UnrealEditor-Cmd.exe -run=pythonscript` 做导入**：命令包模式不写盘，会返回虚假的 `save_directory=True`。

### 6. 白模处理

导入后全白是**正常的**（无 UV）。方案：

| 方案 | 做法 | 适用 |
|---|---|---|
| **A. 统一灰模** | 建 `M_AI_Placeholder`（Base Color 0.5 灰，Roughness 0.7），所有 AI 资产共用 | **blockout、试玩**（推荐） |
| B. UE 自动 UV | Static Mesh Editor → Auto Generate UVs | 简单物体 |
| C. Blender 手展 UV | Smart UV Project | 需贴图的正式资产 |
| D. 三平面材质 | World Position 驱动，不需要 UV | 岩石、地形 |

---

## 动画接入（可选）

**关键限制**：AI 几何是三角面汤，**角色关节处（肩肘胯膝）变形会崩坏**，必须手工重拓扑。道具和环境不受影响。

### CC0 动作库（免费商用）

| 资源 | 内容 | 位置 |
|---|---|---|
| **KayKit 完整包** | 500MB / 2091 文件。`Rig_Medium`+`Rig_Large` 双骨架，含 **CombatMelee / CombatRanged / MovementBasic / MovementAdvanced / General / Simulation / Special / Tools** 全分类，每组带 FBX+GLB+`.blend` 源文件。**额外含 30+ 完整角色模型 + 297 武器道具 + 贴图** | `{ANIMATIONS}\KayKit\` |
| **Quaternius UAL1** | 23.8MB，120+ 动画（FBX） | `{ANIMATIONS}\UAL1_Standard.fbx` |

### 绑定方案

| 类型 | 方案 |
|---|---|
| 双足人形 | AccuRIG（免费桌面，初次需登录）/ Blender Rigify |
| 非人形 | Blender Rigify 的 `Basic Quadruped` / `Wolf` meta-rig |

**不要依赖 Mixamo**：国区不支持，只收双足人形，且有后端故障传闻。

### 接入步骤

```
AI 几何 → Blender 重拓扑 → 绑定 → UE IK Retargeter → 动作库
```

---

## 已验证记录

| 环节 | 实测结果 |
|---|---|
| torch 2.9.1+cu128 | sm_120 真实计算通过 |
| SDXL 出图 | 1024×1024 成功 |
| Hunyuan3D shape-only | 846,578 三角面 / 14.8MB GLB |
| Blender 减面 | 846,578 → 20,000 面 / 1.44MB |
| UE 5.8 导入 | StaticMesh + 材质自动创建，4827 tris |

---

## 排查

| 症状 | 原因 / 处理 |
|---|---|
| `no kernel image is available` | torch 被降级 → 见「0. 环境自检」重装 |
| 模型不出现在下拉框 | 重启 ComfyUI |
| ComfyUI 图片找不到 | `LoadImage` 读 `{COMFY_INPUT}`，把图从 output 复制过去 |
| 导入后全白 | **正常**，无 UV。见「6. 白模处理」 |
| UE 编辑器看向天空卡死 | 见「显存不足」 |
| 生成结果畸形 | prompt 没加 `single object, isolated on white` |

### 显存不足（8GB 边界）

**症状**：看向天空 / 大面积场景时卡顿，`nvidia-smi` 显示显存接近 8151 MiB 上限。

**原因**：Lumen + Nanite + VirtualTextures + SkyAtmosphere + VolumetricCloud 同时开启，天空是 Lumen GI 的最坏情况。

**临时缓解**（编辑器控制台，按 `~`）
```
r.Lumen.DiffuseIndirect.Allow 0
r.Lumen.Reflections.Allow 0
r.Nanite 0
r.VolumetricFog 0
```

**永久修改**：`Config\DefaultEngine.ini` 的 `[/Script/Engine.RendererSettings]` 段。

**另外**：编辑器视图取消勾选 **Realtime**（`Ctrl+R`）。

---

## 下载源速查（实测）

| 源 | 速度 | 用途 |
|---|---|---|
| **ModelScope** | **130–220 MB/s** | 模型首选 |
| hf-mirror.com | 147 MB/s（可能只缓存前半段） | 备选 |
| 上海交大 pytorch 镜像 | 23 MB/s | torch wheel |
| 清华 PyPI | 16–44 MB/s | 普通 pip 包 |
| gh-proxy.com | 300+ KB/s | GitHub |
| GitHub 直连 | 26 KB/s | **不可用** |
| OpenGameArt | 20–28 KB/s | 很慢 |

**aria2 多线程下载**

```powershell
& "C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\aria2.aria2_Microsoft.Winget.Source_8wekyb3d8bbwe\aria2-1.37.0-win-64bit-build1\aria2c.exe" `
  -c -x 16 -s 16 -k 1M --check-certificate=false -d "<目录>" -o "<文件名>" "<URL>"
```

**注意**：curl 需加 `--ssl-no-revoke`，否则报 `CRYPT_E_NO_REVOCATION_CHECK`。

---

## 命令速查

```powershell
# 环境自检
& "{PYTHON}" -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.zeros(1).cuda()+1)"

# 启动 ComfyUI
& "{LAUNCHER}"

# 减面
& "{BLENDER}" --background --python "{DECIMATE}" -- "<输入.glb>" "<输出.glb>" 20000

# 列出 3D 产物
Get-ChildItem "{MESH_OUT}" -Filter *.glb | Sort-Object LastWriteTime -Descending

# 查显存
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```
