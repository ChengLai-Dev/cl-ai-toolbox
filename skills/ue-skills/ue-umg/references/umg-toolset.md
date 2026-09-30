# MCP 路线：官方 UMGToolSet

## 身份

```
Engine\Plugins\Experimental\Toolsets\UMGToolSet\
FriendlyName : UMG ToolSet
Description  : AI assistant tools for creating and manipulating UMG widgets via reflection.
toolset 名   : UMGToolSet.UMGToolSet
```

## 官方的工作流警告（toolset 描述原文）

> IMPORTANT WORKFLOW - for every widget and slot returned by this toolset:
>   1. Call `ObjectTools.list_properties(widget)` to discover exact property names.
>   2. Call `ObjectTools.get_properties(widget, [...])` with those exact names.
>   3. Call `ObjectTools.set_properties(widget, {...})` with those exact names.
>
> Property names vary per widget class and **CANNOT be guessed** - `list_properties` is required.
> Skipping step 1 causes `set_properties` to **silently fail** or set wrong properties.
>
> Returns UObject pointers - ToolsetRegistry serializes them as `{"refPath": "..."}` automatically.
> Pass returned Widget, Slot, and Parent pointers directly to ObjectTools or back to this toolset.

**这是最重要的一条**：属性名必须先 `list_properties` 探测。跳过会静默失败。

## 工具清单（24 个）

所有工具的第一个参数都是 `widgetBlueprint`（WBP 的 `{refPath}`）。

### 资产与树结构

| 工具 | 参数 | 作用 |
|---|---|---|
| `CreateWidgetBlueprint` | `folderPath`, `assetName`, `parentClass` | 建 WBP 资产，返回 blueprint 指针 |
| `AddWidget` | `widgetClass`, `widgetDisplayName`, `parentWidget`, `childIndex` | 加控件，返回含 Slot 指针的完整信息 |
| `RemoveWidget` | `widget` | 删控件连同子树 |
| `MoveWidget` | `widget`, `newParent`, `childIndex` | 移到新父面板的指定位置，返回新 Slot |
| `RenameWidget` | `widget`, `newDisplayName` | 改名 |
| `WrapWidgets` | `widgets`, `wrapperClass` | 把一个或多个控件包进新建的面板 |
| `ReplaceWidgetWithTemplate` | `widgetToReplace`, `templateClass` | 用模板类的新实例替换 |
| `ReplaceWidgetWithNamedSlot` | `widgetToReplace`, `namedSlot` | 用某个命名槽的内容替换宿主控件 |
| `ReplaceWidgetWithChild` | `widgetToReplace` | 用第一个子控件替换面板，把面板从树上摘掉 |

### 查询

| 工具 | 参数 | 作用 |
|---|---|---|
| `GetWidgets` | — | 返回 WBP 信息 + 深度优先顺序的全部控件 |
| `GetWidgetDescription` | `startWidget`, `maxDepth` | 整棵树的完整属性 dump |
| `GetWidgetTreeDepth` | `startWidget` | 最大深度（无子节点的 root = 0） |
| `GetWidgetClassInfo` | `widgetClass` | 单个控件类的 Category / Description / 是否 Panel |
| `ListWidgetClasses` | `filter` | 列出可用控件类，可按名字子串过滤 |
| `ListWidgetBlueprints` | `folderPath` | 列出某目录下的 WBP |
| `GetNamedSlots` | — | 命名槽绑定（独立于树层级） |

### 进阶能力（JSON 路线没有的）

| 工具 | 参数 | 作用 |
|---|---|---|
| `BindToEventProperty` | `eventName`, `propertyName`, `propertyClass` | **加蓝图事件处理节点**，绑定到控件的 multicast delegate |
| `AddUIComponent` | `widgetName`, `componentClass` | 给指定控件加 UI Component |
| `RemoveUIComponent` | `widgetName`, `componentClass` | 移除 UI Component |
| `MoveUIComponent` | `widgetName`, `componentClassToMove`, `relativeToComponentClass`, `bMoveAfter` | 调整 UI Component 顺序 |
| `SetNamedSlotContent` | `hostWidget`, `slotName`, `widgetClass`, `widgetName` | 设置命名槽内容，返回含 Slot 指针的完整信息 |
| `ToggleWidgetAsVariable` | `widget`, `bIsVariable` | 设置 `bIsVariable` 标志 |
| `CompileWidgetBlueprint` | — | 编译 WBP，失败时返回错误详情 |

## 典型流程

```
1. CreateWidgetBlueprint(folderPath="/Game/UI", assetName="WBP_MainMenu", parentClass=<UserWidget>)
   → 拿到 widgetBlueprint 指针
2. GetWidgets(widgetBlueprint)                    # 看初始树，通常已有一个根 CanvasPanel
3. AddWidget(widgetClass=<TextBlock>, widgetDisplayName="Text_Title", parentWidget=<root>, childIndex=0)
   → 返回 widget 指针和 slot 指针
4. ObjectTools.list_properties(widget)            # ★ 必做，拿准确属性名
5. ObjectTools.set_properties(widget, {"Text": "标题", ...})
6. ObjectTools.set_properties(slot, {"LayoutData": "(...)"})   # 槽位属性写到 slot 上
7. CompileWidgetBlueprint(widgetBlueprint)        # 验证
```

## 和 JSON 路线的边界

**UMGToolSet 能做到而 JSON 路线做不到**（JSON 路线的硬缺口）：

- 事件绑定（`BindToEventProperty`）
- UI Component 增删移
- 命名槽内容（`SetNamedSlotContent`）
- 显式编译与错误详情

**JSON 路线更划算的场景**：

- 新建界面 / 大改布局 —— 官方这套要 N 次工具往返，每次 `set_properties` 前还得先 `list_properties`，token 开销随控件数线性增长；JSON 是写一个文件一次到位
- 需要 git diff / code review —— 官方改的是 `.uasset` 二进制，不可 diff
- 需要"先出完整设计再落地"

**注意**：这个 toolset 的 UObject 指针通过 `{"refPath": "..."}` 序列化，可以直接在工具之间传递，也可以传给 `ObjectTools`。但没有"保存资产"能力——改完要用 `AssetTools.save_assets` 落盘。
