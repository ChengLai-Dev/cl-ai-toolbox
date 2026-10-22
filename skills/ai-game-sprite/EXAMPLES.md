# 提示词模板与实战记录

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
