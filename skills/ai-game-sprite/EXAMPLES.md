# 提示词模板与实战记录

## 静态资源提示词模板（模式①）

五类各一套，`<SUBJECT>` 换主体描述即可。模板在 `scripts/generate.py` 的 `STATIC_PROMPTS` 里。

### prop（道具）

```
2D hand-drawn game item sprite, <SUBJECT>, three-quarter top-down view facing right,
clean flat colors, bold black outline, simple cel shading, plain flat light gray background,
single object, centered, entire object visible, no text, no ground shadow,
wide empty gray margins on the left and right sides of the frame
```

例：`<SUBJECT>` = `a small wooden crate with iron bands`
道具别选尖锐长条（剑、矛），容易和腿重叠读成"道具被腿挡住"。

### icon（图标）

```
2D game UI icon, <SUBJECT>, flat vector style, bold dark outline, limited saturated palette,
centered, plain flat white background, single icon, no text, no border,
wide empty margins on every side of the frame
```

例：`<SUBJECT>` = `a small blue potion flask with a cork stopper`

### background（场景背景）

```
2D hand-drawn game background, <SUBJECT>, wide establishing shot, clean flat colors,
simple cel shading, even lighting, no characters, no creatures, no text,
empty open foreground space in the center
```

例：`<SUBJECT>` = `a sunlit medieval village street with stone walls and market stalls`
背景不抠透明底，要靠「中央留空」给玩法元素留位置。

### portrait（角色立绘）

```
full body 2D hand-drawn character portrait, <SUBJECT>, three-quarter top-down view facing right,
clean flat colors, bold black outline, simple cel shading, plain flat light gray background,
full body, entire body visible from head to shoes, single character, no text, no ground shadow,
wide empty gray margins on the left and right sides of the frame
```

例：`<SUBJECT>` = `a female blacksmith in a leather apron holding a hammer`

### tile（地块贴图）

```
seamless tileable 2D game ground texture, <SUBJECT>, top-down view, clean flat colors,
even lighting, uniform detail, no shadows, no objects, no borders,
repeating pattern across the whole frame
```

例：`<SUBJECT>` = `cracked gray cobblestone pavement`
`uniform detail` 和 `even lighting` 不能省 —— 这两个词直接决定无缝化的接缝观感。

---

## 角色占位符

模板里用 `<CHAR>` 代表角色设定段，换角色时只改这一段：

```
a young courier with short blond hair wearing a mint green hoodie with the hood down,
a brown leather crossbody satchel across the chest, dark gray shorts, white sneakers,
holding a small white letter envelope in the right hand
```

角色段建议包含：年龄感 → 发型发色 → 上衣（颜色+款式）→ 下装 → 鞋 → 手持道具。
道具别选尖锐长条（剑、矛），容易和腿重叠读成"道具被腿挡住"。

---

## walk（行走）

**立绘 prompt**（动作中姿态，同侧异向描述）：

```
2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right,
<CHAR>,
walking mid-stride, the front leg is the RIGHT leg stepping forward to the right,
the back leg is the LEFT leg trailing behind, the front arm is the LEFT arm swinging forward,
the back arm is the RIGHT arm swung behind, upright torso,
clean flat colors, bold black outline, simple cel shading, plain flat light gray background,
full body, entire body visible from head to shoes, single character, no text, no ground shadow,
wide empty gray margins on the left and right sides of the frame
```

**视频 prompt**：

```
2D cartoon game character walking in place, three-quarter top-down view facing right,
full body visible, steady walking cycle with the legs alternating forward and backward,
the front leg is the RIGHT leg while the back arm is the RIGHT arm, the LEFT arm swings forward,
arms bent at the elbows, torso upright, clean flat colors, bold black outline,
plain light gray background, smooth continuous walking motion, game sprite animation
```

### walk · 宽步幅版（**2026-10 起推荐默认用这个**）

上面那版立绘的步幅偏小。实测：小步幅立绘喂 Wan 只会得到“轻微晃动”（4 帧两两 IoU 0.93–0.99）；
换成宽步幅后是 0.50–0.79，走路才成立。**判定输入够不够用**：把立绘缩到目标尺寸，看两脚间距能不能读出“跨出去”。

**立绘 prompt**：

```
2D hand-drawn cartoon game character sprite, <CHAR>,
walking mid-stride in a WIDE split step, the RIGHT leg planted far forward with the foot flat
on the ground, the LEFT leg stretched far behind with the heel lifted,
the LEFT arm swung far forward, the RIGHT arm swung far back, torso leaning slightly forward,
three-quarter top-down view, side profile facing right, clean flat colors, bold dark warm outline,
simple cel shading, light from the upper left, plain flat light gray background,
full body, entire body visible from head to feet, single character, no text, no ground shadow,
wide empty gray margins on the left and right sides of the frame
```

**视频 prompt**：

```
2D cartoon game character walking cycle, side profile facing right, full body visible,
the legs alternate in WIDE clear strides, the right leg steps far forward and the left leg
swings far back, then the legs swap, each foot lifts off the ground,
the arms swing opposite to the legs, readable walking cadence, clean flat colors,
bold black outline, plain light gray background,
smooth continuous looping walk cycle, game sprite animation
```

### 三朝向（east / south / north）只改一句

同一角色要出三套（**不许靠水平镜像补**：镜像会把左上光变成右上光）。立绘与视频 prompt 各换一句：

| 朝向 | 立绘里的视角句 | 视频 prompt 里的视角句 |
|---|---|---|
| `east` | `three-quarter top-down view, side profile facing right` | `side profile facing right` |
| `south` | `three-quarter top-down view, front view facing the viewer` | `front view, walking toward the camera` |
| `north` | `three-quarter top-down view, back view, seen from behind` | `seen from behind, back view, walking away from the camera` |

back view 的立绘要补一句背面才有信息的细节（`crossed leather straps on the back`、`the back of the hood`），
否则模型容易把正面特征画到背面，三套朝向识别会崩。

### 机械件 / 道具的「朝向可读」补丁

`facing right` 对塔炮、弩炮、箭头这类东西不够用 —— 出成 X 形或俯视圆盘时，旋转起来读不出在瞄哪。
把**剪影语义**写死：

```
..., a horizontal wooden stock lying left to right, a sharp iron bolt tip sticking out at the right end,
a short curved bow mounted across the stock near the right end with the bowstring pulled back to the left,
a brass pivot collar under the middle of the stock,
the whole silhouette clearly points to the right like a stretched arrow, no trigger box at the back, ...
```

### 「空槽」补丁（要底座不要成品）

Z-Image 无 negative prompt，所有“不要”都要写进正向并**逐项列举**，否则它会自作主张把晶体/炮管画上去：

```
..., a low circular stone plinth with a brass ring socket on the flat top,
empty platform with no weapon and no roof and no character, ...
```

出了就 `read_image` 看一眼，不对就换措辞重出（本机 2 次内能出），别攒到批量最后再返工。

## idle（待机）

**立绘 prompt**：

```
2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right,
<CHAR>,
standing still in a relaxed ready stance, both feet planted shoulder width apart,
the RIGHT arm holds the prop lowered beside the right thigh, the LEFT arm relaxed at the side,
upright posture, clean flat colors, bold black outline, simple cel shading,
plain flat light gray background, full body, entire body visible from head to shoes,
single character, no text, no ground shadow,
wide empty gray margins on the left and right sides of the frame
```

**视频 prompt**：

```
2D cartoon game character standing idle, three-quarter top-down view facing right, full body visible,
subtle breathing motion, the chest and shoulders rise and fall gently, slight hair and cloth sway,
arms relaxed, feet planted, clean flat colors, bold black outline, plain light gray background,
smooth continuous subtle idle loop, game sprite animation
```

## attack（攻击）

**立绘 prompt**：

```
2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right,
<CHAR>,
dynamic slash attack pose, the RIGHT arm extended forward to the right swinging the prop
diagonally downward, the LEFT arm pulled back behind the body for balance,
the front leg is the RIGHT leg bent forward, the back leg is the LEFT leg extended behind,
torso twisted to the right, clean flat colors, bold black outline, simple cel shading,
plain flat light gray background, full body, entire body visible from head to shoes,
single character, no text, no ground shadow,
wide empty gray margins on the left and right sides of the frame
```

**视频 prompt**：

```
2D cartoon game character performing one slash attack, three-quarter top-down view facing right,
full body visible, the right arm swings the prop in a fast diagonal slash from up high down to the front,
the body lunges forward, the weight shifts onto the front leg, the left arm swings back,
one decisive strike, clean flat colors, bold black outline, plain light gray background,
smooth continuous attack animation, game sprite animation
```

## hit（受击）

**立绘 prompt**：

```
2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right,
<CHAR>,
staggering back from a hit, the torso leaning back a little, the head snapped back,
the LEFT arm flung upward in shock, both feet still on the ground taking one small step back,
shocked expression, clean flat colors, bold black outline, simple cel shading,
plain flat light gray background, full body, entire body visible from head to shoes,
single character, no text, no ground shadow, no hearts,
wide empty gray margins on the left and right sides of the frame
```

**视频 prompt**：

```
2D cartoon game character knocked back by a hit, three-quarter top-down view facing right, full body visible,
the body rocks backward in shock, the head snaps back, the free arm flies up, one foot steps back,
the body sways forward again to the starting pose and the rocking motion repeats,
a back and forth rocking motion, no floating hearts, no symbols, clean flat colors,
bold black outline, plain light gray background, smooth continuous looping reaction animation,
game sprite animation
```

---

## 实战记录：模式②（静态图 → 序列帧）

源图 `assets/characters/courier_base.png`（512×512，Z-Image 出的平涂底立绘）：

```powershell
python scripts\generate.py --mode frames-from-image --character test_courier `
  --src "D:\Code\opencode-workspace\ai-game-pipeline\assets\characters\courier_base.png" `
  --action walk --seed 20261021 --no-look-refine
```

| 指标 | 结果 |
|---|---|
| 归一化去背 | 洪水填充，透明占比 80% |
| 循环闭合 iou | **0.768**（模式③同条件 0.748） |
| wrap/avg | **0.771** |
| 抠图残留 | 无 |
| 动作幅度 | 大 |

归一化把首帧背景统一成纯灰底，抠图条件比模式③更干净，iou 反而更高。

源图若是草稿或风格参考，去掉 `--no-look-refine`，会多走一遍 Canny + ControlNet 精修
（Z-Image 精修约 190 秒），把姿势和轮廓钉死后再喂 Wan，实测 iou 0.765 / wrap-avg 0.857。

### 三条去背分支的触发方式

分支很容易因为「源图恰好是平涂灰底」而永远走不到，测的时候要专门造源图：

```powershell
# 造一张高饱和背景的源图 —— 洪水填充的 sat<=24 判据必然失败，会退回 BiRefNet
python -c "from PIL import Image; import sys; sys.path.insert(0,'..\\pipeline');
from gen_frames import remove_background;
base = Image.open(r'..\\assets\\characters\\courier_base.png').convert('RGBA');
cut = remove_background(base);
c = Image.new('RGBA', base.size, (28,92,205,255)); c.paste(cut,(0,0),cut);
c.convert('RGB').save(r'D:\\Code\\temp\\src_colored.png')"

# 造一张自带 alpha 的源图 —— 直接沿用原 alpha，不启动 ComfyUI
python -c "from PIL import Image; import sys; sys.path.insert(0,'..\\pipeline');
from gen_frames import remove_background;
remove_background(Image.open(r'..\\assets\\characters\\courier_base.png').convert('RGBA')).save(r'D:\\Code\\temp\\src_alpha.png')"
```

跑完看日志里的 `cutout=` 字段确认走的哪条：

| 日志 | 分支 |
|---|---|
| `cutout=flood(80%)` | 洪水填充 |
| `cutout=birefnet` | BiRefNet |
| `cutout=existing-alpha` | 源图自带 alpha |
| `cutout=none` | 未去背 |

实测：BiRefNet 分支 iou 0.764 / wrap-avg 0.421；自带 alpha 分支 iou 0.768 / wrap-avg 0.771。

## 实战记录：模式①（静态资源）

```powershell
python scripts\generate.py --mode static --character test_crate --kind prop `
  --subject "a small wooden crate with iron bands" --seed 20261021
```

| 阶段 | 结果 |
|---|---|
| Z-Image 768×768 | 132-220 秒（取决于机器负载） |
| ESRGAN 4x | 768² → 3072²，约 40 秒 |
| BiRefNet 抠图 | 四角 alpha=0、主体 alpha=254 |
| 最终 | 256×256 透明底 PNG + 同名 `.json` |

**出图耗时抖动很大**：Z-Image + ControlNet 峰值约 7.7GB，8GB 卡上只要别的程序占了几百 MB
显存就会掉进 Windows 共享显存，32 秒能退化到 863 秒。跑之前先 `check_env.py` 看显存占用。

## 实战记录：courier（512×512 / 240×320 / 49 帧）

一次跑通两个流程的对照实测，同 seed、同提示词、同分辨率：

| 指标                   | 纯文生图 | ControlNet |
| ---------------------- | -------- | ---------- |
| 立绘耗时               | 29 秒    | 65 秒      |
| 循环闭合 iou           | 0.742    | **0.760**  |
| wrap/avg               | 0.354    | 0.773      |
| 抠图残留               | 无       | 无         |
| 动作幅度               | 大       | 偏小       |

命令：

```powershell
cd D:\Code\opencode-workspace\ai-game-pipeline\pipeline
..\.venv\Scripts\python.exe run_pipeline.py --character courier --action walk --engine a14b `
  --seed 20261021 --size 512 --steps 8 --frames 8 --length 49 `
  --video-width 240 --video-height 320 --prompt "<上面的 walk 立绘模板>" `
  --video-prompt "<上面的 walk 视频模板>"
```

新流程与手工分步跑 ControlNet 的产物字节完全一致（SHA256 相同），完全可复现。

### ControlNet 的能力边界

控制图默认由**基础立绘反推**（Canny），所以 ControlNet 钉死的是基础立绘已有的姿势，
它**不能凭空造出姿势**。想让它按指定姿势生成，只能手画/程序生成基础立绘：

```powershell
# 1. 准备一张正方形的姿势图（骨骼图、剪影、手绘都可以）
# 2. 直接当控制图用（绕过基础立绘那一步）
..\.venv\Scripts\python.exe run_pipeline.py --character hero --action walk `
  --control-image ..\assets\controlnet_test\my_pose.png --control-scale 0.75
```

`test_controlnet.py --style silhouette` 里有程序生成的行走剪影可作起点。

### 手动改控制图

```powershell
# 基础立绘 -> Canny 控制图
..\.venv\Scripts\python.exe make_control.py --src ..\assets\characters\courier_base.png `
  --out ..\assets\controlnet_test\canny_courier.png --size 512

# 用图像编辑器改 canny_courier.png（比如把剑从腿边挪开），然后：
..\.venv\Scripts\python.exe run_pipeline.py --character courier --action walk `
  --look-src ..\assets\characters\courier_base.png --seed 20261021
```

`--look-src` 指定的图会作为基础立绘（重新生成 Canny），所以改控制图要走
`--control-image` 或改完基础立绘再 `--look-src`。

---

## 低分辨率测试档

调试管线时用低分辨率，链路跑通只花约 110 秒：

| 阶段     | 生产值  | 低分辨率档 | 像素比 |
| -------- | ------- | ---------- | ------ |
| 立绘     | 768×768 | 512×512    | 1/2.25 |
| 视频     | 480×640 | 240×320    | 1/4    |

- 视频宽高必须是 16 的倍数，比例取 3:4 与图集画布 192×256 一致
- `length` 不要压：49 是循环闭合的下限
- 240×320 画面明显变糊，只适合验证链路通不通，不适合判断成片质量
---

## 实战记录：一个 48×56 小兵的完整交付（2026-10 实测）

目标：塔防游戏里一个 48×56 的步兵，三套朝向（east/south/north）+ 死亡 4 帧，帧率 8 fps。

```powershell
$S = "D:\Code\.config\opencode\skills\ai-game-sprite\scripts"

# 1) 立绘：宽步幅 + 该朝向的视角句（三套各一张）
python $S\generate.py --mode static --character grunt_base_east --kind portrait `
  --upscale never --seed 20261101 `
  --subject "<CHAR>, walking mid-stride in a WIDE split step, the RIGHT leg planted far forward, ... three-quarter top-down view, side profile facing right"

# 2) 立绘 → 视频（--no-look-refine：立绘已是最终画风，省 90 秒）
python $S\generate.py --mode frames-from-image --character grunt_walk_east `
  --src <...>\pathwarden__grunt_base_east.png --action walk --frames 4 --length 41 --seed 20261101 `
  --no-look-refine --cutout auto

# 3) 立刻快照 Wan 原始帧（覆盖问题见 FIELD-NOTES §3）
robocopy "$env:COMFY\output\Wan_frames" "<工程>\_work\raw\grunt_walk_east" *.png /NFL /NDL /NJH /NJS

# 4) 按步态周期挑帧 + 逐帧归一
python $S\pick_gait_frames.py --src <工程>\_work\raw\grunt_walk_east `
  --out <工程>\_work\grunt_walk_east --frames 4 --report pick.json
#   -> period=17 picked=[9,13,17,22] wrap_vs_avg=1.301

# 5) 落到引擎画布 + 写 manifest/sidecar
python $S\fit_and_validate.py --src <工程>\_work\grunt_walk_east `
  --out-dir <工程>\game\assets\art\enemies\grunt --asset enemy_grunt_walk_east `
  --canvas 48x56 --anchor bottom --fps 8 --loop --facing east --frames 4 `
  --allow-offcenter --manifest-root <工程>\game\assets\art
#   -> [PASS] enemy_grunt_walk_east 48x56 frames=4 scale=0.067
```

交付后的目录长这样（同目录四套动画共用一份 manifest）：

```
enemies/grunt/
  enemy_grunt_walk_east_00.png … _03.png
  enemy_grunt_walk_south_00.png … _03.png
  enemy_grunt_walk_north_00.png … _03.png
  enemy_grunt_die_00.png … _03.png
  enemy_grunt_walk_east.json          # sidecar（files 相对本目录）
  manifest.json                       # {"assets":[…]}（files 相对素材根）
```

这一轮 5 种体型 × 3 朝向 + 5 套死亡的实际耗时：约 **3 小时**（含重试、挑帧、校验），
单条「立绘→行走」约 **4.5 分钟**。批量前先清显存、先跑通一套再铺。

**踩坑清单**（都在 [FIELD-NOTES.md](FIELD-NOTES.md)）：
站姿立绘只出晃动、auto-loop 挑到平缓区间、Wan 输出目录互相覆盖、抠图容差写太小把包围盒撑爆、
Wan zoom 漂移、死亡末帧不透明、首尾帧 IoU 0.95 达不到。
