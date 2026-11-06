---
name: ue-umg
description: 在虚幻工程里创建和修改 UMG 界面。主路线是编辑工程 UIWidgets 目录下的 JSON 文件、由 WidgetJsonBridge 插件自动重建 Widget Blueprint（支持布局、属性、事件绑定）；UI Component、命名槽、显式编译等 JSON 路线做不到的部分走官方 MCP 的 UMGToolSet。每次新建或实质修改界面，默认同时产出交互文档（每个 WBP 一份，按节点写"程序要接哪些节点、哪个节点接什么事件"），除非用户明确说不要文档。当需要新建界面、调整布局、修改控件属性、绑定控件事件，或用户提到 UMG / Widget Blueprint / UIWidgets / WBP 时触发。
---

# UE 界面（UMG）

## 两条路线

| | JSON 路线（主） | MCP 路线（补充） |
|---|---|---|
| 怎么用 | 编辑 `<项目>/UIWidgets/**/*.json` | 调 `UMGToolSet` 的 MCP 工具 |
| 真源 | JSON 文件 | 资产本身 |
| 一次改整棵树 | ✅ 一个文件搞定 | ❌ 每个控件一次工具调用 |
| 版本管理 | ✅ git 友好 | ❌ 改的是 `.uasset` |
| 事件绑定 | ✅ `events` 字段 | ✅ 支持 |
| UI Component / 命名槽 | ❌ 不支持 | ✅ 支持 |
| 编译控制 | 隐式 | ✅ 显式 `CompileWidgetBlueprint` |

**默认走 JSON 路线**，按需求切：

| 需求 | 走哪条 |
|---|---|
| 新建界面、改布局、改文字/颜色/字号 | JSON |
| 大改结构、重构、需要 code review | JSON |
| 绑定 `OnClicked` 等事件 | JSON（`"events": ["OnClicked"]`） |
| 增删 UI Component | MCP |
| 命名槽内容 | MCP |
| 编译并拿错误详情 | MCP |

## 交付物：交互文档（默认必出）

**每个 WBP 一份交互文档**，除非用户明确说不要。文档只回答一件事：**拼这个界面的人希望程序接哪些节点**。

位置：`<项目>/Docs/UI/<WBP名>.md`。

必须覆盖：

| 章节 | 内容 |
|---|---|
| 需要程序接的节点 | 节点 / 类型 / 程序拿它做什么（图标、文本、选中框、按钮…） |
| 不需要接的节点 | 纯布局/装饰节点，单列一块，告诉程序可以忽略 |
| 交互 | 哪个节点接什么事件、触发后发生什么；跨控件的流程写在持有方那份 |
| 状态 | 每个状态下哪个节点变、变成什么（颜色 / 显隐 / 索引） |
| 含有的子控件 | 只写实例名 + 「见 xxx.md」，不重复内部节点 |

**不写**：业务数据从哪来、何时刷新、已实现/未实现、代码与函数签名、完整调色板。

模板见 [references/ui-handoff-doc.md](references/ui-handoff-doc.md)，直接抄结构。

只交付了 JSON/资产、没来得及写文档时，明确告诉用户"文档待补"，不要默默省略。

## JSON 路线

### 前提

- 插件 `WidgetJsonBridge` 已在 `.uproject` 启用（经 `AdditionalPluginDirectories` 引入）
- **编辑器必须开着**——靠 1 秒 ticker 轮询检测文件变化
- 插件需先编译出 `Binaries`。编辑器开着时用 `-NoHotReloadFromIDE` 可以照常编译，不必关编辑器（见 README 构建一节）

### 路径映射

```
<项目>/UIWidgets/HUD/MainMenu.json   ↔   /Game/HUD/MainMenu.uasset
```

JSON 放入 `UIWidgets/` 即触发创建；资产已存在时**重建** WidgetTree（旧树被替换）。

### 双向同步

- AI 改 JSON → 1 秒内资产重建
- Designer 里手工改 + **Ctrl+S** → 自动回写 JSON
- 两边同时改 → 编辑器版本落 `xxx_editor_conflict.json`，主文件保留 AI 版本，**需人工合并**

### 最小骨架

```json
{
  "schemaVersion": 1,
  "designSizeMode": "Desired",
  "root": {
    "class": "/Script/UMG.CanvasPanel",
    "className": "CanvasPanel",
    "name": "Root_Canvas",
    "isVariable": false,
    "properties": {},
    "children": [
      {
        "class": "/Script/UMG.TextBlock",
        "className": "TextBlock",
        "name": "Text_Title",
        "isVariable": false,
        "properties": { "Text": "格雷王冠", "Justification": "Center" },
        "slot": {
          "class": "/Script/UMG.CanvasPanelSlot",
          "className": "CanvasPanelSlot",
          "properties": {
            "LayoutData": {
              "offsets":   {"left": -300, "top": 60, "right": 600, "bottom": 70},
              "anchors":   {"min": {"x": 0.5, "y": 0}, "max": {"x": 0.5, "y": 0}},
              "alignment": {"x": 0.5, "y": 0}
            }
          }
        }
      }
    ]
  }
}
```

### designSizeMode（默认写 Desired）

`designSizeMode` 对应 `UUserWidget::DesignSizeMode`，声明在 `WITH_EDITORONLY_DATA` 下（`UserWidget.h:1533-1535`），**只影响 Designer 预览，不影响运行时布局**。引擎 CDO 默认是 `FillScreen`（`UserWidget.cpp:113`），不写时预览会按设计视口铺满。

1. **新写 JSON 一律先写 `"designSizeMode": "Desired"`**。面板、栏位、行、格子、细条都适用。
2. `Desired` 下小控件（如 `WBP_WeightBar`）可能预览得很小，用 Designer 的 Zoom 放大即可；**不要为了看清就改成 `FillScreen`**——`FillScreen` 会按设计视口铺满，比例失真。
3. 只有 `Desired` 真的是 0×0（完全空白的容器）时，才用 `CustomOnScreen` 给一个预览尺寸；`FillScreen` 只用于确实要按整屏占比预览的 HUD。

### 规则

1. `contentHash` 由插件维护，**不要手写、不要改**（导入时忽略）
2. `schemaVersion` 固定为 `1`
3. 删 JSON 节点 = 删控件；**删 JSON 文件不会删资产**，要在 Content Browser 手动删
4. 只能给容器控件加 `children`：`CanvasPanel` / `VerticalBox` / `HorizontalBox` / `Overlay` / `ScrollBox` 等；单子容器（`SizeBox` / `Border` / `Button` / `ScaleBox` / `NamedSlot`）最多一个；叶子控件（`TextBlock` / `Image` / `Spacer` / `ProgressBar`）不能有 `children`
5. **只写想改的属性即可**，未列出的用默认值；但**未知属性名会让整次导入失败**（不再静默跳过），所以改不熟悉的属性前先查 `PropertySchema/`
6. `name` 会被**原样使用**，只有同树真重名才加后缀。名字稳定是动画与事件绑定存活的前提，不要靠改名来表达结构调整
7. 导出已做 CDO 差异过滤，JSON 里只出现非默认值，文件很小
8. 控件对象名**不要以「类名_」开头**，否则 Hierarchy 显示名会和对象名不一致（见下节）
9. `designSizeMode` 默认写 `"Desired"`；它只影响 Designer 预览，详见上节
10. 需要把 `FSlateBrush` / `WidgetStyle` 等结构体写成对象时，顶层加 `"structMode": "object"`；具体字段查 Schema 的 `fields`，详见 [references/json-bridge.md](references/json-bridge.md)

### ⚠️ 命名：Hierarchy 显示名必须等于对象名

Hierarchy 里那行文字不一定是对象名。引擎逻辑（`Widget.cpp:1234` `IsGeneratedName` / `1279` `GetDisplayNameBase`）：

- 名字**等于类名**、或以**「类名_」开头**，且该控件不是变量 → 显示**类名**（`Border_IconFrame` 在面板上显示成 `Border`）
- 否则 → 显示对象名（若设过编辑器专用的 `DisplayLabel` 则显示它；`DisplayLabel` 只在编辑器存在，JSON 也不导出）

后果：Designer 里看到 `Border` / `Overlay`，代码里 `GetName()` / `FindWidget` / `BindWidget` / `SeekWidget` 拿到的却是 `Border_IconFrame` / `Overlay_Icon`。照面板上的名字写路径 → 找不到控件 → 运行期空指针，而且**编译期不报错**。

规则：

| 要求 | 做法 |
|---|---|
| 显示名 = 对象名 | 对象名不用「类名_」前缀：写 `IconFrame_Border` / `Icon_Overlay` / `Frame_Fill`，不要 `Border_IconFrame` / `Overlay_Icon` |
| 语义前缀安全 | `Img_` / `Text_` / `Btn_` / `Grid_` / `Size_` / `VB_` / `HB_` 都不与类名撞（类名是 `Image` `TextBlock` `Button` `UniformGridPanel` `SizeBox` `VerticalBox` `HorizontalBox`） |
| 交付前核对 | Hierarchy 里某控件被显示成类名（而不是你写的名字）→ 对象名带了「类名_」前缀，改掉 |

**插件会自动对齐**：`WidgetJsonBridge` 导入 JSON 时，对每个控件执行 `SetDisplayLabel(对象名)`（在控件迁进真实 WidgetTree、Rename 之后），所以面板名字不会再被替换成类名，也不需要你手写 `DisplayLabel`。手动在 Designer 里设的 `DisplayLabel` 会在下次重建时被覆盖——这是有意的，别依赖它。

非变量控件在面板上会显示成 `[名字]`（TextBlock 还会带文本摘要），方括号和摘要都来自 `GetLabelTextWithMetadata()`（`Widget.cpp:1264`），是引擎固定格式；检查比的是去掉装饰的 `GetLabelText()`（`Widget.h:1062`，仅 `WITH_EDITOR`）。两者都不能当运行期查找键。

命名检查（诊断用，**不阻断导入**）：导入后、Designer 保存后各跑一次，不一致写进 Output Log（`WidgetJsonBridge[Import]` / `[Save]`）；变量控件记 Error、装饰节点记 Warning，`WidgetJsonBridge.StrictNameCheck 1` 可全部升级为 Error，`WidgetJsonBridge.ValidateNames` 只扫 `/Game` 做全量体检。

### 写之前先查属性表

改不熟悉的控件属性前，先让编辑器导出真实属性清单：

**Tools > Widget Json Bridge > Export Property Schema**，或控制台 `WidgetJsonBridge.ExportSchema`。

输出在 `<项目>/Saved/WidgetJsonBridge/PropertySchema/`，按类分文件（`widgets/TextBlock.json`、`slots/CanvasPanelSlot.json`），几 KB，直接读。每个属性带 `format` 字段：

- `object` → 可写原生 JSON 对象
- `string` → 必须是引擎文本格式字符串
- `原生 JSON 值` → bool / number / 字符串

这比读文档或猜属性名可靠，也省掉「手工摆一个再 Ctrl+S 照抄」那一步。

### 事件绑定

节点上加 `events` 数组，值是委托属性名：

```json
{ "class": "/Script/UMG.Button", "name": "Btn_Start", "isVariable": true, "events": ["OnClicked"] }
```

- 声明了 `events` 的控件会被自动标成变量（引擎要求）
- 导入时通过 `FWidgetBlueprintOperationUtils::BindToEventProperty` 生成蓝图事件节点，函数名由引擎决定
- 导出时从 `Blueprint->Bindings` 回写，往返不丢
- 编辑器里手工加的绑定如果在 JSON 里没有对应 `events`，结构大改后可能失效 —— 想让某个绑定长期存活，就把它写进 JSON

### 槽位属性

`UCanvasPanelSlot` 的 UPROPERTY 只有三个：`LayoutData`（`FAnchorData`）、`bAutoSize`、`ZOrder`。
`Position` / `Size` / `Anchors` / `Alignment` 在引擎里只是 `UFUNCTION` 存取器，**不是 UPROPERTY**，写了无效。

`LayoutData` 现在可以写原生对象：

```json
"LayoutData": {
  "offsets":   {"left": -100, "top": -40, "right": 200, "bottom": 80},
  "anchors":   {"min": {"x": 0.5, "y": 0.5}, "max": {"x": 0.5, "y": 0.5}},
  "alignment": {"x": 0.5, "y": 0.5}
}
```

旧的引擎文本格式仍然兼容。VerticalBox / HorizontalBox 的 `Size` 可写 `{"value": 1.0, "rule": "Fill"}`。

### ⚠️ offsets 的语义（踩过一次坑，别再错）

**锚点重合（Min == Max）时：`left/top` 是相对锚点的位置偏移，`right/bottom` 是宽和高，不是右下边界坐标。**

这正是 Designer 里 Details 面板的标签：点锚点轴上 `Right/Bottom` 显示为 **Size X / Size Y**；只有该轴是拉伸锚点（Min ≠ Max）时才叫 Offset Right/Bottom。

```json
// 200×80 的控件，中心落在锚点上
"offsets": {"left": -100, "top": -40, "right": 200, "bottom": 80}
```

写错成「右下边界」（`right: 100, bottom: 40`）的后果：控件变成 100×40（正好一半），而且**不会报错**——负值时才会被插件拦下。别人（或旧文档）写的 `right = left + width` 一律要改成 `right = width`。

**权威来源是 `PropertySchema/`，不是文档。** 需要某个控件的准确属性名时先导出 Schema 查表。

## MCP 路线

工具的发现协议和通用陷阱见 `ue-mcp` 技能，**动手前先读这两份**：

- `../ue-mcp/SKILL.md`
- `../ue-mcp/references/pitfalls.md`

`UMGToolSet` 的工具清单与用法见 [references/umg-toolset.md](references/umg-toolset.md)。

主流程：`CreateWidgetBlueprint` 建资产 → `AddWidget` 加控件 → `ObjectTools.list_properties` 拿准确属性名 → `set_properties` → `CompileWidgetBlueprint` 验证。

## 参考

- [references/ui-handoff-doc.md](references/ui-handoff-doc.md) — 程序对接文档模板（默认必出的交付物）
- [references/json-bridge.md](references/json-bridge.md) — JSON 格式全量、实测属性、插件限制与 5.8 适配要点
- [references/umg-toolset.md](references/umg-toolset.md) — 官方 UMGToolSet 工具清单与用法
