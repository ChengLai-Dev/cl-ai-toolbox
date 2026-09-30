---
name: ue-umg
description: 在虚幻工程里创建和修改 UMG 界面。主路线是编辑工程 UIWidgets 目录下的 JSON 文件、由 WidgetJsonBridge 插件自动重建 Widget Blueprint；事件绑定、UI Component、命名槽、编译验证等 JSON 路线做不到的部分走官方 MCP 的 UMGToolSet。当需要新建界面、调整布局、修改控件属性，或用户提到 UMG / Widget Blueprint / UIWidgets / WBP 时触发。
---

# UE 界面（UMG）

## 两条路线

| | JSON 路线（主） | MCP 路线（补充） |
|---|---|---|
| 怎么用 | 编辑 `<项目>/UIWidgets/**/*.json` | 调 `UMGToolSet` 的 MCP 工具 |
| 真源 | JSON 文件 | 资产本身 |
| 一次改整棵树 | ✅ 一个文件搞定 | ❌ 每个控件一次工具调用 |
| 版本管理 | ✅ git 友好 | ❌ 改的是 `.uasset` |
| 事件绑定 / UI Component / 命名槽 | ❌ 不支持 | ✅ 支持 |
| 编译控制 | 隐式 | ✅ 显式 `CompileWidgetBlueprint` |

**默认走 JSON 路线**，按需求切：

| 需求 | 走哪条 |
|---|---|
| 新建界面、改布局、改文字/颜色/字号 | JSON |
| 大改结构、重构、需要 code review | JSON |
| 绑定 `OnClicked` 等事件 | MCP |
| 增删 UI Component | MCP |
| 命名槽内容 | MCP |
| 编译并拿错误详情 | MCP |

## JSON 路线

### 前提

- 插件 `WidgetJsonBridge` 已在 `.uproject` 启用（经 `AdditionalPluginDirectories` 引入）
- **编辑器必须开着**——靠 1 秒 ticker 轮询检测文件变化
- 插件需先编译出 `Binaries`；**编辑器运行中（Live Coding 活跃）编译会失败，要先关编辑器**

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
            "LayoutData": "(Offsets=(Left=-300.000000,Top=60.000000,Right=300.000000,Bottom=130.000000),Anchors=(Minimum=(X=0.500000,Y=0.000000),Maximum=(X=0.500000,Y=0.000000)),Alignment=(X=0.500000,Y=0.000000))"
          }
        }
      }
    ]
  }
}
```

### 规则

1. `contentHash` 由插件维护，**不要手写、不要改**（导入时忽略）
2. `schemaVersion` 固定为 `1`
3. 删 JSON 节点 = 删控件；**删 JSON 文件不会删资产**，要在 Content Browser 手动删
4. 只能给容器控件加 `children`：`CanvasPanel` / `VerticalBox` / `HorizontalBox` / `Overlay` / `ScrollBox` 等；单子容器（`SizeBox` / `Border` / `Button` / `ScaleBox` / `NamedSlot`）最多一个；叶子控件（`TextBlock` / `Image` / `Spacer` / `ProgressBar`）不能有 `children`
5. **只写想改的属性即可**，未列出的用默认值；未知属性名会告警并跳过，不会中断

### ⚠️ 槽位属性以实测为准，不要照抄文档

插件自带的 `Docs/SchemaReference.md` 在 **CanvasPanelSlot 那一段是错的**：它写 `Position` / `Size` / `Anchors` / `Alignment` 四个独立属性，但引擎里这四个只是 `UFUNCTION` 存取器，**不是 UPROPERTY**，反射序列化根本碰不到。

实测真实属性是（见 `Engine/Source/Runtime/UMG/Public/Components/CanvasPanelSlot.h`）：

| 真实属性 | 类型 | 说明 |
|---|---|---|
| `LayoutData` | `FAnchorData` 文本 | `(Offsets=(Left=..,Top=..,Right=..,Bottom=..),Anchors=(Minimum=(X=..,Y=..),Maximum=(X=..,Y=..)),Alignment=(X=..,Y=..))` |
| `bAutoSize` | bool | 按内容自适应尺寸 |
| `ZOrder` | int | 渲染顺序，越大越靠上 |

VerticalBox / HorizontalBox 的槽同理，`Size` 是 `FSlateChildSize` 结构体文本（`(Value=1.000000,SizeRule=Fill)`），不是文档写的 `Size.Rule`。

**可信做法**：需要某个控件的准确属性格式时，**先在编辑器里手工摆好一个，Ctrl+S 回写 JSON，然后照抄格式**。这比读文档可靠。

## MCP 路线

工具的发现协议和通用陷阱见 `ue-mcp` 技能，**动手前先读这两份**：

- `../ue-mcp/SKILL.md`
- `../ue-mcp/references/pitfalls.md`

`UMGToolSet` 的工具清单与用法见 [references/umg-toolset.md](references/umg-toolset.md)。

主流程：`CreateWidgetBlueprint` 建资产 → `AddWidget` 加控件 → `ObjectTools.list_properties` 拿准确属性名 → `set_properties` → `CompileWidgetBlueprint` 验证。

## 参考

- [references/json-bridge.md](references/json-bridge.md) — JSON 格式全量、实测属性、插件限制与 5.8 适配要点
- [references/umg-toolset.md](references/umg-toolset.md) — 官方 UMGToolSet 工具清单与用法
