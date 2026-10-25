# 实战踩坑与实测（2026-10，RTX 5060 8GB / 32GB RAM）

这一页只写「文档别处没写、但一定会踩」的东西。每条都带症状、原因、修法，能直接照做。

---

## 1. 站姿立绘 → Wan 只做「轻微晃动」

**症状**：`atlas.png` 看着角色在动，但导出的 4 帧几乎同姿态（帧间差异 <3%），游戏里像原地抖。

**原因**：Wan I2V 是「照着首帧画 49 帧」，动作幅度由**首帧的姿态张力**决定。
立绘如果是站姿或小步幅（两脚接近并拢），它没有“可以摆动的余量”，只会给你呼吸和披风抖动。
本机实测同一个角色两种立绘：

| 立绘 | 4 帧两两 IoU | 效果 |
|---|---|---|
| 小步幅（默认 walk 模板） | 0.93–0.99 | 读不出走路 |
| **宽步幅**（前腿跨远、后腿蹬直、手臂大幅前后摆） | 0.50–0.79 | 走路成立 |

**修法**：立绘 prompt 用「宽步幅」写法（见 [EXAMPLES.md](EXAMPLES.md) 的 walk 模板 · 宽步幅版），
视频 prompt 里也要重复 `the legs alternate in WIDE clear strides … then the legs swap`。
改完先跑一条，看 `pick_gait_frames.py` 的 `picked` 帧是不是明显不同再批量铺。

---

## 2. `import_frames.py --auto-loop` 挑到「最平缓」的区间

**症状**：`--auto-loop` 日志报 `loop segment: [22, 38) (iou=0.688)`，看着正常，但 4 帧几乎一样。

**原因**：`auto-loop` 找的是**最相似的一对帧**（iou 最大）。动作最平缓的地方恰好最相似，
于是挑中的区间正好是“几乎没动”的那一段。它保证的是“接得上”，不是“有动作”。

**修法**：不要用它挑交付帧。用 `pick_gait_frames.py`：
掩膜自相关找步态周期 T（同一姿势隔多少帧重现），再从 `t0` 起等距取 N 帧。
正常输出形如 `period=17 picked=[9,13,17,22] wrap_vs_avg=1.301`。

---

## 3. `Wan_frames` 是固定目录，下一条动画会覆盖上一条

**症状**：连跑三条动画后回去挑帧，发现只剩最后一条的 49 帧；前面两条的帧没了。

**原因**：`run_wan_a14b.py` 写死输出到 `ComfyUI/output/Wan_frames/`，每次只更新 `_last_run.txt`。

**修法**：**每跑完一条立刻快照**（`docs/art/tools/artgen.py` 里就是这么做的）：

```powershell
$raw = "<工程>\_work\raw\<job>"; New-Item -ItemType Directory -Force $raw | Out-Null
Copy-Item "$env:COMFY\output\Wan_frames\*.png" $raw
Copy-Item "$env:COMFY\output\Wan_frames\_last_run.txt" $raw
```

丢过一次就要重跑（约 2.5 min/条），别指望能从 atlas 反推。

---

## 4. 抠图容差写太小 → 包围盒撑爆，逐帧归一全废

**症状**：归一后 4 帧尺寸差 1.6 倍（实测 275×355 与 450×600 混在一起），小尺寸素材里角色忽大忽小。

**原因**：自己写「与边界中位色的距离 < 38」这种洪水填充，会被 Wan 的柔和地面阴影/背景渐变中途截断，
背景残留被算进不透明像素 → 包围盒贴到整幅画布。

**修法**：用管线自己的 `gen_frames.remove_background(image, tolerance=250)`：
判据是 `色差 sum|Δ| ≤ 250` **且** `饱和度 ≤ 24`，再从画布边界洪水填充。
诊断命令：

```powershell
python -c "import sys; sys.path.insert(0,r'<pipeline>\pipeline'); from gen_frames import remove_background as r; from PIL import Image; import numpy as np;
a=np.asarray(r(Image.open(r'<某帧>.png').convert('RGBA'),250)); m=a[...,3]>40; ys,xs=np.where(m); print((xs.min(),ys.min(),xs.max()+1,ys.max()+1), int(m.sum()))"
```

包围盒应该只框住角色（几百像素宽），不是整幅 480×640。

---

## 5. Wan 的 zoom / 平移漂移

**症状**：4 帧角色越来越“近”，同一套动画在不同帧大小不同。

**原因**：I2V 视频里角色会缓慢放大/位移，联合包围盒缩放只能消掉一部分。

**修法**：`pick_gait_frames.py` 逐帧按**身体高度**归一（每帧 bbox 高度缩到同一值、脚底贴画布底），
缩放系数限幅 ±8%（防武器/披风撑大 bbox 引起抖动）。之后再用**联合包围盒**落画布——
两步的顺序不能反：先逐帧归一（消漂移），再统一缩放（保证动画不逐帧缩放）。

---

## 6. 「首尾帧 alpha 掩膜 IoU ≥ 0.95」对真实步态不成立

**症状**：按 0.95 卡，所有行走动画全部不合格。

**原因**：4 帧走路是「接触—过渡—反侧接触—过渡」，末帧和首帧本来就差半个步幅。
48×56 上双腿交替约占剪影 15–20%，掩膜 IoU 上限大约 0.85–0.92。

**实测**（15 套 5 种体型 × 3 朝向）：首尾帧 IoU **0.51–0.92**，质心位移 0.2–2.7 px。

**修法**：改看 `wrap_vs_avg = 首帧↔末帧 IoU ÷ 相邻帧 IoU 均值`：
**≥ 1.0 表示接缝比普通帧间过渡更平滑**（不会跳帧），实测这批是 1.01–1.38。
强行凑 0.95 只能复制首帧 → 循环里出现“定格”，是更坏的动画。

**例外**：纯发光类循环（水晶呼吸、光环脉动）只改 RGB 不动 alpha，IoU 恒为 **1.000**、位移 0.000，
两种判据都过。这类别喂 Wan，程序化画更快更稳（见第 8 条）。

---

## 7. 死亡套末帧必须全透明 —— AI 视频保证不了

**症状**：AI 出的“倒地”序列最后一帧还留着半截身体，引擎靠销毁兜底，会闪一下。

**修法**：死亡用**程序化塌陷**（基于本体立绘）：`压扁 + 小角度倾斜 + 淡出/压暗`，最后一帧直接输出全透明。
两个必须做对的细节：

1. 先把本体缩到 88% 再摆到画布底边中点 —— 倾斜时不会顶到左/右/上边缘（有透明边距要求）。
2. 倾斜后若仍越界，就整帧按底边中点继续缩（最多 4 次），别硬塞。

大角度旋转在 48×56 上只会得到一团斜糊块，角度控制在 3–12°。

---

## 8. 什么时候该程序化，别硬喂 Wan

| 素材 | 用 Wan 的问题 | 程序化怎么做 |
|---|---|---|
| 水晶/宝珠待机呼吸 | 整块晶体漂移、缩放，掩膜对不上 | 只改 RGB 亮度 + 核心辉光，alpha 恒定 → IoU 1.000 |
| 地面光环/减速圈 | 会跟着镜头漂 | 椭圆环（地面按 0.6 压扁）+ 符文点亮，alpha 恒定 |
| 弹道（箭/炮弹/冰锥） | 32×12 这个尺寸下采样必糊 | 矢量画（4× 超采样后 LANCZOS），2–3 帧就够 |
| 命中火花 | 形状不受控、中心容易填满 | 4 角星 + 核心 + 火星，逐帧放大淡出 |
| 死亡塌陷 | 末帧透明无法保证 | 见第 7 条 |

程序化素材的**登记口径**：manifest 里 `method` 写 `procedural vector draw` / `ai-static + procedural`，
不要和 AI 出图混写；对上游披露时“AI 生成”和“程序化生成”要分开说。

---

## 9. 静态件的「朝向」与「空槽」写不清楚

**症状 A**：交叉弩/炮塔出成 X 形或俯视圆盘，旋转时读不出在瞄哪。

- 修法：不要只写 `facing right`。写**剪影语义**：
  `a horizontal stock lying left to right, a sharp bolt tip sticking out at the right end, the bowstring pulled back to the left, the whole silhouette clearly points to the right like a stretched arrow, no trigger box at the back`。

**症状 B**：要「空底座」，模型硬给你画上晶体/炮管。

- 修法：Z-Image 无 negative prompt，把所有“不要”写进正向并**逐项列举**：
  `the top is empty with no crystal and no gem and no roof and no cannon, a small empty brass claw cradle on the flat top`。
- 一次不成就换措辞重出（本机 2 次内能出）。同一批里第 1 张就要 `read_image` 验收，别攒到最后。

---

## 10. 多套动画放同一目录时的 manifest

**症状**：`enemies/grunt/` 有 walk_east / walk_south / walk_north / die 四套，
每套都写 `manifest.json` → 只有最后一套生效。

**修法**（引擎侧通常有这几种读法，先看对方契约）：

- 一个目录一个 `manifest.json`，顶层 `{"assets": [...]}` 一次声明多套，**每套必须给 `file`/`files`**；
- `manifest.json` 里的 `files` 通常相对**素材根目录**；
- 同名 sidecar（`<asset>.json`）里的 `files` 相对**本目录**，两者别写反。

`fit_and_validate.py` 已经按这个口径合并，`--manifest-root` 指定相对根。

---

## 11. 耗时基准（可以直接拿去排期）

| 阶段 | 本机实测 |
|---|---|
| Z-Image 768×768 / 8 步（含启停 ComfyUI、BiRefNet 抠图） | **96–160 s / 张** |
| Wan 2.2 I2V-A14B，41–49 帧 @480×640（4 步 LoRA） | **113–145 s / 条** |
| 一条「立绘 → 行走」全链路 | 约 **4.5 min** |
| 15 套行走（5 体型 × 3 朝向，含重试与挑帧） | 约 **3 h** 墙钟 |
| 显存 | Z-Image 峰值 5.6 GB；桌面占 2.3 GB 时仍可跑 |

批量出图前的两条纪律：出图前 `comfy_ctl.py stop`（Z-Image 与 ComfyUI 抢内存）；
ComfyUI 热启后不要反复重启（抠图冷启 30–50 s，热启几秒）。

---

## 12. 交付前自查（30 秒）

- [ ] `fit_and_validate.py` 全 PASS（或只剩“循环 IoU”这一条已知争议）
- [ ] 帧数 / fps 与需求文档逐条对齐
- [ ] 三朝向是**三套独立图**，不是水平镜像（镜像会把左上光变成右上光）
- [ ] 静态件朝向可读：把炮塔旋转 90°/180° 看一眼还认不认得出
- [ ] 死亡套最后一帧不透明像素 = 0
- [ ] 透明底无灰边：棋盘底 1:1 看四边
- [ ] manifest/sidecar 齐全，`files` 路径能直接采到文件
- [ ] seed / prompt / 耗时记进日志（复现与披露都要）

---

## 13. 重跑任何「只改元信息」的步骤前，先快照 + 对账渲染环境

**症状**：素材早就验收完了，只是补个 manifest 字段、重跑一遍归一脚本。跑完所有判据照样 PASS、
manifest 里的 SHA256 也照样「自洽」——**但文件字节变了**，而且变的是**不该动的成品**。

**原因**：渲染链的 Python 环境和素材生成时不是同一套。
LANCZOS 重采样的实现在 **Pillow 大版本之间变过**，逐像素差 1 LSB 就足以让 PNG 字节全变。
典型的错法是「图省事用系统 python」，而素材当初是项目 venv 跑出来的。

**实测（本项目 Pathwarden，2026-10-25）**：

| 环境 | `PIL.__version__` | `numpy` | 结果 |
|---|---|---|---|
| `ai-game-pipeline\.venv\Scripts\python.exe`（素材生成时用的） | **13.0.0** | **2.5.4** | 重跑后与已验收文件**逐字节相同** |
| 系统 `python 3.12` | 12.1.1 | 2.2.6 | 同一份脚本重跑，**31 张不该动的成品被刷出字节差异** |

发现不了的原因：`validate-*.json` 全部 PASS，manifest 的 `sha256_frames[]` 是按**新文件**重算的，
自己和自己永远一致 —— 只有拿**改动前的哈希**对账才看得出来。

**三条纪律**：

1. **记环境**：每个项目在 manifest 或管线脚本注释里写死渲染环境（`python -V` + `PIL.__version__` + `numpy.__version__`），
   并在交付清单里注明"重跑必须用这个解释器"。
2. **重跑前快照、重跑后对账**：动任何"只改元信息/只改参数"的步骤前，先对全量产物做一次 `sha256` 快照，
   跑完 diff 一遍；**不是目标文件的差异一律回退，用正确解释器重跑**，不要"反正判据都过了"就交。
3. **优先项目 venv**：不要用系统 python 跑素材链；没 venv 就先建一个并锁版本。

```powershell
# 快照（改动前）
$root = "game\assets\art"
Get-ChildItem -Recurse $root -Filter *.png | ForEach-Object {
  "$($_.FullName.Replace("$PWD\",""))  $((Get-FileHash $_.FullName -Algorithm SHA256).Hash)"
} | Set-Content docs\art\_pipeline-logs\sha-before.txt

# 重跑后对账：把当前哈希与 sha-before.txt 逐行比对，非目标文件的差异必须为 0
```

**顺带一条同源教训（验收链的盲区）**：只查「首尾帧 IoU」的验收链，遇到**每一帧都完全相同**的素材会判 PASS
（同帧自然 IoU=1.000）。所以除了哈希对账，还要在链路里加一条硬检查：
**声明 `frames=N` 就必须有 N 个不同的 `sha256`**（本项目就有 6 帧光环逐字节全同、一路 PASS 到人工复审才被抓出来的案例）。
