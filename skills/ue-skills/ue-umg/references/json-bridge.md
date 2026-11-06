# JSON 路线：WidgetJsonBridge

## 插件身份

```
位置   : D:\Code\UE Plugins\WidgetJsonBridge\
FriendlyName : Widget Json Bridge
版本   : 0.1.0
模块   : WidgetJsonBridgeEditor（纯 Editor，无 Runtime 代码）
```

自述："Bidirectional JSON synchronization for UMG User Widgets. Watches the project UIWidgets folder and rebuilds Widget Blueprints from JSON files; exports editor changes back to JSON on asset save."

源码分布（改插件时看这里）：

| 文件 | 职责 |
|---|---|
| `Private/WidgetJsonSerializer.cpp` | 核心：`UWidgetTree` ↔ JSON 反射序列化 |
| `Private/WidgetJsonSync.cpp` | 同步调度：目录监听 / hash 跟踪 / 冲突处理 |
| `Private/WidgetJsonBridgeEditorModule.cpp` | 模块入口：菜单 / 保存事件 / Ticker |
| `Private/WidgetJsonBridgeTests.cpp` | 3 个自动化测试 |

## 工程接入

`.uproject` 需要：

```json
"AdditionalPluginDirectories": ["D:/Code/UE Plugins"],
"Plugins": [ { "Name": "WidgetJsonBridge", "Enabled": true } ]
```

## 路径映射

```
<项目>/UIWidgets/HUD/MainMenu.json   ↔   /Game/HUD/MainMenu.uasset
```

- JSON 放入 `UIWidgets/` 后编辑器即创建对应资产（目录不存在可手动建）
- 资产已存在时导入会**重建 WidgetTree**（旧树被替换）
- 实际映射**以文件路径为准**，`assetPath` 只是信息性字段

## 完整 JSON 结构

```json
{
  "schemaVersion": 1,
  "assetPath": "/Game/HUD/MainMenu",
  "contentHash": "88b038c66d9a8d6e39c43a4d79c547c6",
  "root": {
    "class": "/Script/UMG.CanvasPanel",
    "className": "CanvasPanel",
    "name": "Root_Canvas",
    "isVariable": false,
    "properties": { },
    "slot": null,
    "children": [ ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `schemaVersion` | 固定 `1` |
| `assetPath` | 信息性，导入忽略 |
| `designSizeMode` | 可选。设计器预览模式：`FillScreen` / `Custom` / `CustomOnScreen` / `Desired` / `DesiredOnScreen` |
| `structMode` | 可选。`"object"`：所有可导出结构体递归写成原生 JSON 对象；缺省/`"string"`：非白名单结构体仍是引擎文本字符串。写对象结构体时必须写 `"object"` |
| `contentHash` | 树内容的规范化 MD5（key 排序），**由插件维护，AI 不要动** |
| `class` | 类的完整对象路径。C++ 类如 `/Script/UMG.TextBlock`；蓝图类如 `/Game/UI/WBP_Avatar.WBP_Avatar_C` |
| `className` | 短名，信息性，导入忽略 |
| `name` | 控件名，即对象名（`GetFName()`），**按原名创建**；只有同 WidgetTree 下真重名才加数字后缀并告警。名字稳定是动画/事件绑定存活的前提。**不要用「类名_」开头**：`Border_IconFrame`、`Overlay_Icon`、`TextBlock_Title` 会被 Hierarchy 显示成 `Border`/`Overlay`/`TextBlock`，代码按对象名找就找不到（见 SKILL.md「命名」一节） |
| `isVariable` | 是否暴露为蓝图变量。声明了 `events` 时被强制置 `true` |
| `events` | 委托名数组，如 `["OnClicked"]`。导入时生成蓝图事件节点；导出时从 `Blueprint->Bindings` 回写 |
| `properties` | 可编辑属性表 |
| `slot` | 父容器分配的槽位（根节点为 `null` 或省略） |
| `children` | 子控件数组 |

### `designSizeMode`（默认写 `Desired`）

设计器工具栏那个 `Fill Screen / Custom / Custom on Screen / Desired / Desired on Screen` 下拉，存的是 `UUserWidget::DesignSizeMode`（生成类 CDO，`WITH_EDITORONLY_DATA`），**不在 WidgetTree 里**。所以：

- 导入时先校验枚举名，编译重建 CDO 之后再写入；值写错整次导入失败（不动旧树）
- 导出时从 CDO 回写，往返不丢
- **默认写 `"Desired"`**：引擎 CDO 默认是 `FillScreen`（`UserWidget.cpp:113`），不写会按设计视口铺满；面板/栏位/细条都会被拉伸，比例失真
- **只影响编辑器预览框大小，运行时布局无关**（`WITH_EDITORONLY_DATA`，`UserWidget.h:1533-1535`）
- `Desired` 下小控件（如 `WBP_WeightBar`）可能预览得很小，用 Designer 的 Zoom 放大即可；不要为了看清改成 `FillScreen`
- 只有 `Desired` 真的是 0×0（完全空白的容器）时，才用 `CustomOnScreen` 给一个预览尺寸；`FillScreen` 只用于确实要按整屏占比预览的 HUD

### `structMode`：结构体对象模式

- 顶层 `"structMode": "object"`：所有可导出 `FStructProperty` 递归写成原生 JSON 对象。
- 缺省或 `"string"`：旧行为，非白名单结构体仍是引擎文本字符串。
- 导入不依赖该字段：JSON 值是 Object 就按对象解析，是 String 就按旧格式解析；旧 JSON 不用迁移。
- **写对象结构体时必须同时写 `"structMode": "object"`**；否则编辑器保存时会按 string 模式把对象改回字符串（插件会 Warning，但不会阻止）。
- 对象模式的字段名是 C++ 属性名（`BackgroundImage` / `FillImage` / `TintColor` / `DrawAs` / `ResourceName` 等）；具体字段看 `PropertySchema/widgets/<Class>.json` 里对应属性的 `fields`。
- 不参与对象化的字段：`UVRegion`、`bIsDynamicallyLoaded`（没有 `CPF_Edit`）；容器字段（`TArray` / `TMap` / `TSet`）仍是引擎文本字符串，写成数组会导入失败。
- 白名单结构体（`FVector2D` / `FLinearColor` / `FMargin` / `FAnchors` / `FAnchorData` / `FSlateChildSize`）仍用专用格式，不受 `structMode` 影响。

`ProgressBar.WidgetStyle` 的对象写法示例：

```json
"WidgetStyle": {
  "BackgroundImage": {
    "TintColor": {
      "SpecifiedColor": { "r": 0.02, "g": 0.03, "b": 0.04, "a": 1 },
      "ColorUseRule": "UseColor_Specified"
    },
    "DrawAs": "Box",
    "Margin": { "left": 0.4167, "top": 0.4167, "right": 0.4167, "bottom": 0.4167 },
    "ResourceObject": "None",
    "ResourceName": "../../../Engine/Content/Slate/Common/ProgressBar_Background.png"
  },
  "FillImage": {
    "TintColor": {
      "SpecifiedColor": { "r": 0.584, "g": 0.397, "b": 0.138, "a": 1 },
      "ColorUseRule": "UseColor_Specified"
    }
  },
  "EnableFillAnimation": false
}
```

> 这是属性片段，不是完整 WBP JSON。`FillImage` / `MarqueeImage` 只写要改的字段即可；不要写 `"..."` 之类的占位键，未知字段会让整次导入失败。

> 只写要改的字段时，不要删掉同级其它字段；未写的字段会取类默认值，不是“保持当前值”。

## 属性值格式

导出规则：**`CPF_Edit` 且非 Transient / Deprecated / BlueprintReadOnly / delegate** 的属性。也就是说——

> **导出哪个属性，AI 才能改哪个属性。**

并且导出时做了 **CDO 差异过滤**：与类默认值相同的属性不写进 JSON。所以一份干净界面的 JSON 很小（一个 TextBlock 通常只有 `Text` 一两个字段），**未写 = 用默认值**。

值按类型输出：

| 属性类型 | JSON 值 |
|---|---|
| `bool` | JSON bool |
| 整数/浮点 | JSON number（导入用 `%.17g`，double 不丢精度） |
| 枚举 | 枚举名字符串，如 `"Left"`、`"SelfHitTestInvisible"` |
| `FText` / `FString` / `FName` | 纯文本字符串（**要显示什么就直接写什么**） |
| 结构体（白名单） | 原生 JSON 对象，见下 |
| 结构体（其他） | 默认引擎 `ExportTextItem` 文本格式；顶层 `structMode: object` 时改为原生 JSON 对象（字段名见 Schema 的 `fields`） |
| 对象引用 | 路径字符串，如 `"/Game/UI/Textures/T_Icon.T_Icon"` 或 `"None"` |

### 原生 JSON 对象（白名单 / `structMode: object`）

| 结构体 | 写法 |
|---|---|
| `FVector2D` | `{"x": 1.0, "y": 2.0}` |
| `FLinearColor` | `{"r": 1, "g": 0.5, "b": 0, "a": 1}` |
| `FMargin` | `{"left": 10, "top": 5, "right": 10, "bottom": 5}` |
| `FAnchors` | `{"min": {"x": 0.5, "y": 0.5}, "max": {"x": 0.5, "y": 0.5}}` |
| `FAnchorData` | `{"offsets": {...}, "anchors": {...}, "alignment": {...}}` |
| `FSlateChildSize` | `{"value": 1.0, "rule": "Fill"}` |

导入端同时兼容旧的引擎文本格式，历史 JSON 不用改。

### 引擎文本格式（白名单外）

```
Slate 颜色 (SpecifiedColor=(R=1.000000,G=1.000000,B=1.000000,A=1.000000))
Slate 字体 (FontObject=None,Size=24.000000,TypefaceFontName="Bold")
```

这类格式复杂，**别猜**：先导出 Property Schema 看 `format`，或在编辑器里手工设一次再 Ctrl+S 回写照抄。

未知属性名、值格式错误、容器拒绝子控件、抽象/废弃类，都会让**整次导入失败**并写进错误报告（不再静默跳过）。所以改不熟悉的属性前先查 `PropertySchema/`。

## 属性 Schema（权威查表）

菜单 **Tools > Widget Json Bridge > Export Property Schema**，或控制台 `WidgetJsonBridge.ExportSchema`。

输出到 `<项目>/Saved/WidgetJsonBridge/PropertySchema/`：

```
index.json                      # 类清单
widgets/TextBlock.json          # 单类几 KB
slots/CanvasPanelSlot.json
```

每条属性带 `name` / `type` / `category` / `format`，枚举属性额外带 `values`。`format` 为 `object` 时可写原生 JSON 对象，为 `string` 时必须写引擎文本格式。非白名单结构体在 `structMode: object` 下会额外带 `fields`，递归列出字段名/类型/format；照它写就不会猜错字段名。

**改不熟悉的属性前先读这个，而不是读文档。**

## 槽位属性（实测更正）

插件自带的 `Docs/SchemaReference.md` 里 CanvasPanelSlot 那张表是**错的**。它列的 `Position` / `Size` / `Anchors` / `Alignment` 在引擎里只是 `UFUNCTION` 存取器，不是 UPROPERTY，反射序列化碰不到。

**实测真实导出**（与 `Engine/Source/Runtime/UMG/Public/Components/CanvasPanelSlot.h` 一致）：

```json
"slot": {
  "class": "/Script/UMG.CanvasPanelSlot",
  "className": "CanvasPanelSlot",
  "properties": {
    "LayoutData": {
      "offsets":   {"left": -300, "top": 60, "right": 600, "bottom": 70},
      "anchors":   {"min": {"x": 0.5, "y": 0}, "max": {"x": 0.5, "y": 0}},
      "alignment": {"x": 0.5, "y": 0}
    },
    "ZOrder": 0
  }
}
```

`UCanvasPanelSlot` 的 UPROPERTY 只有三个：`LayoutData`（`FAnchorData`）、`bAutoSize`、`ZOrder`。
`FAnchorData` = `{ FMargin Offsets; FAnchors Anchors; FVector2D Alignment; }`。

**`Offsets` 的语义（2026-11 实测订正，旧文档这里写错过）**：

- 锚点重合（Minimum == Maximum）的轴：`Left/Top` 是相对锚点的位置偏移，**`Right/Bottom` 是宽/高**（Designer 的 Details 面板在此轴上就显示为 `Size X` / `Size Y`）。
- 拉伸锚点（Minimum ≠ Maximum）的轴：`Right/Bottom` 才是右下边距。

引擎依据：`SConstraintCanvas::FSlot::ArrangeChildren` 点锚点轴取 `Size = (Right, Bottom)`；`UCanvasPanelSlot::SetSize()` 把 `Size.X` 写进 `Offsets.Right`。

所以 200×80、中心落在锚点上的写法是：

```json
"offsets": {"left": -100, "top": -40, "right": 200, "bottom": 80}
```

写成 `right: 100, bottom: 40`（当成右下边界）不会报错，控件会变成 100×40 —— **尺寸减半且无任何提示**。
插件现已在导入时校验：点锚点轴上 `Right/Bottom < 0` 直接判失败，并在错误里给出应填的值。

**导出时会省略值为 0 的分量**，例如这个导出结果只有 `Right`/`Bottom`：

```
"LayoutData": "(Offsets=(Right=100.000000,Bottom=30.000000),Anchors=(...),Alignment=(...))"
```

VerticalBox / HorizontalBox 的槽：`Padding`、`Size`、`HorizontalAlignment`、`VerticalAlignment`。

- `Size` 是 `FSlateChildSize`，可写 `{"value": 1.0, "rule": "Fill"}`；`rule` 为 **`Automatic`** 或 `Fill`
- `HorizontalAlignment`：`HAlign_Fill` / `HAlign_Left` / `HAlign_Center` / `HAlign_Right`
- `VerticalAlignment`：`VAlign_Fill` / `VAlign_Top` / `VAlign_Center` / `VAlign_Bottom`

`UButtonSlot`：`Padding`、`HorizontalAlignment`、`VerticalAlignment`。

**可靠做法**：需要某个控件的准确属性名与格式时，**导出 Property Schema 查表**（`Saved/WidgetJsonBridge/PropertySchema/slots/<类名>.json`），或手工摆一个 → Ctrl+S 回写照抄。不要靠文档。

## 事件绑定

节点上加 `events` 数组：

```json
{
  "class": "/Script/UMG.Button",
  "name": "Btn_Start",
  "isVariable": true,
  "events": ["OnClicked"],
  "properties": {},
  "children": [ ]
}
```

- 值是**委托属性名**（Button 有 `OnClicked` / `OnPressed` / `OnReleased` / `OnHovered` / `OnUnhovered`），不是处理函数名
- 声明了 `events` 的控件会被自动置 `isVariable = true`（`BindToEventProperty` 要按变量名找控件）
- 导入在 `CompileBlueprint` 之后调 `FWidgetBlueprintOperationUtils::BindToEventProperty`，由引擎生成事件节点，函数名形如 `BndEvt__Btn_Start_OnClicked`
- 导出时读 `Blueprint->Bindings` 回写，所以往返不丢
- 编辑器里手工加的绑定若 JSON 里没有对应 `events`，结构大改后可能失效 —— 要长期存活就写进 JSON
- 重复绑定不会报错，官方 API 会返回 "already bound"，插件只记 Verbose

## 构建与验证

```powershell
# 构建（见下文的 Live Coding 坑）
& "<engine>/Build/BatchFiles/Build.bat" <Project>Editor Win64 Development -Project="<path>/<Project>.uproject" -NoHotReloadFromIDE -WaitMutex

# 跑插件的 8 个自动化测试（往返、端到端、路径映射、导入原子性、属性 Schema、事件绑定、UTF-8、hash 回环）
& "<engine>/Binaries/Win64/UnrealEditor-Cmd.exe" "<path>/<Project>.uproject" -unattended -nosplash -NullRHI -log -ExecCmds="Automation RunTests WidgetJsonBridge" -TestExit="Automation Test Queue Empty"
```

测试结果看 `<Project>/Saved/Logs/<Project>.log` 里的 `Test Completed` 行；导入/导出日志形如 `WidgetJsonBridge: 已导入 ... -> /Game/...`。

### 两个必须先知道的坑

1. **`-NoHotReloadFromIDE` 是必需的。** UBT 有个按可执行文件路径命名的**全局**互斥体检查（`HotReload.cs` 的 `CheckForLiveCodingSessionActive`）。所有 UE 编辑器都是同一个 `Engine/Binaries/Win64/UnrealEditor.exe`，所以**任何一个**开着 Live Coding 的编辑器都会锁死**所有**工程的编译，哪怕工程完全无关。报错原文 `Unable to build while Live Coding is active...`。传 `-NoHotReloadFromIDE` 跳过该检查，不用关编辑器，也不用杀 `LiveCodingConsole`（互斥体由编辑器进程持有，杀 console 无效）。

2. **外部插件的编译产物不在插件目录里。** 经 `AdditionalPluginDirectories` 引入的插件，DLL 落在**目标工程的** `Binaries/` 下。判断插件是否已编译要看工程侧，不看插件的 `Binaries/`。

## 常用控件属性

| 控件 | 常用属性 |
|---|---|
| `TextBlock` | `Text`、`FontSize`（快捷覆盖，-1 时用 `Font.Size`）、`ColorAndOpacity`、`Justification`（`Left`/`Center`/`Right`）、`AutoWrapText`、`MinDesiredWidth`、`WrapTextAt` |
| `Image` | `Brush`（含 `ResourceObject` 与 `ImageSize`）、`ColorAndOpacity` |
| `Button` | `ClickMethod`（`DownAndUp`/`PreciseClick`/`MouseDown`/`MouseUp`）、`BackgroundColor`、`WidgetStyle` |
| `SizeBox` | `WidthOverride`、`HeightOverride`、`MinDesiredWidth`、`MinDesiredHeight` |
| 所有 `UWidget` 基类 | `Visibility`、`RenderOpacity`、`RenderTransform`、`RenderTransformPivot`、`ToolTipText`、`bIsEnabled`、`Clipping`、`PixelSnapping`、`Cursor`、`AccessibleBehavior` |

导出已做 **CDO 差异过滤**：与类默认值相同的属性不写进 JSON。所以一个干净页面的 `TextBlock` 通常只剩 `Text` 一两个字段，不再有"导出 36 个默认值"的问题。手写时同样只需写想改的。

## 双向同步与冲突

```
AI 改 UIWidgets/**/*.json  ──ticker(1s)──> 重建 WidgetBlueprint ──> 保存
编辑器改 UMG ──Ctrl+S──> PackageSavedWithContextEvent ──hash 对比──> 回写 JSON / 写 .conflict
```

- **防回环**：导入器保存资产时通过 `ImportingPackageNames` 跳过反向导出
- **冲突**：两边同时改时，编辑器版本存为 `xxx_editor_conflict.json`，主文件保留 AI 版本，**绝不静默覆盖**，需人工合并

## 导入失败与撤销

- **原子导入**：新树先在临时 `UWidgetTree` 上完整构建，成功后一次性替换。**JSON 写错不会毁掉现存资产**，旧树原样保留
- **属性级错误也算失败**：未知属性名、值格式错误、单子容器塞多个子控件、抽象类，都会让整次导入失败并写报告（以前只打 warning 继续，AI 无从得知自己写错了）
- **失败报告**：原因写到 `<项目>/Saved/WidgetJsonBridge/Errors/<相对路径>.error.json`，字段为 `jsonPath` / `assetPath` / `error` / `timestamp`。**AI 改完 JSON 应读这个目录确认无新增错误文件**，比翻 Output Log 可靠
- **不刷日志**：同一份内容失败过不会每秒重试；文件内容一变（hash 变）自动重试
- **编译失败不落盘**：编译不过时不保存资产，也不标记为已同步
- **可撤销**：整个导入包在 `FScopedTransaction` 里，`WidgetTree->Modify()` 与控件 Rename 都在事务内（Ctrl+Z 路径未做 GUI 自动化实测）
- **冲突文件不参与同步**：`*_editor_conflict.json` 会被 ticker 跳过，不会变成垃圾资产

## 菜单（Tools > Widget Json Bridge）

| 菜单项 | 作用 |
|---|---|
| Export Edited Widget to JSON | 把当前打开的 WBP 导出为 JSON（手动触发，**无视冲突检测直接覆盖**） |
| Import All JSON Files | 清空同步记录并全量重导入 `UIWidgets/` 下所有 JSON |
| Open Sync Folder | 打开 `UIWidgets` 目录 |
| Open Docs Folder | 打开插件文档目录 |

## 已知限制

- 动画（`WidgetAnimation`）、属性绑定、`BindWidget`、跨 WBP 命名槽引用 —— **未支持**
- 删除 JSON 文件**不会**删除资产，需手动删
- 全量重建 WidgetTree：JSON 里声明的事件会被重建，但只在编辑器里手工加、JSON 里没有对应 `events` 的绑定，结构大改后可能失效
- 插件 `Binaries` 不随 git，引擎升级后需按新版本重编

## 菜单

| 菜单项 | 作用 |
|---|---|
| Export Edited Widget to JSON | 打开中的 WBP 导出为 JSON（无视冲突检测） |
| Import All JSON Files | 清空同步记录并全量重导入 |
| Export Property Schema | 导出每个控件类/槽类的真实属性清单到 `Saved/WidgetJsonBridge/PropertySchema/` |
| Open Sync Folder | 打开 `UIWidgets` |
| Open Docs Folder | 打开插件文档目录 |

控制台命令：`WidgetJsonBridge.ExportSchema`

## 插件自身的构建与测试

用任意接入了本插件的工程即可（插件是纯 Editor 模块，不依赖具体工程的游戏代码）：

```powershell
# 构建（编辑器开着也能编，关键是 -NoHotReloadFromIDE）
& "<engine>/Build/BatchFiles/Build.bat" <Project>Editor Win64 Development -Project="<path>/<Project>.uproject" -NoHotReloadFromIDE -WaitMutex

# 测试（结果看 <Project>/Saved/Logs/<Project>.log 里的 "Test Completed" 行）
& "<engine>/Binaries/Win64/UnrealEditor-Cmd.exe" "<path>/<Project>.uproject" -unattended -nosplash -NullRHI -log -ExecCmds="Automation RunTests WidgetJsonBridge" -TestExit="Automation Test Queue Empty" -NoHotReloadFromIDE
```

测试会用到真实资产：`UIWidgets/Test/SyncTest.json` ↔ `/Game/Test/SyncTest`。

## UE 5.8 API 适配要点（改插件代码时必读）

- 属性标志：5.8 移除了 `CPF_EditAnywhere/EditDefaultsOnly`，**统一用 `CPF_Edit`**
- 文本序列化：老 `ExportTextItem/ImportText` 已移除，改用 `ExportTextItem_InContainer/ImportText_InContainer`（指针需包 `TNotNull`，头 `Misc/NotNull.h`）
- 属性值读写：`TProperty<...>::GetPropertyValue_InContainer/SetPropertyValue_InContainer`；`FByteProperty::Enum` 已私有，改用 `GetIntPropertyEnum()`
- 保存事件：`UPackage::PackageSavedWithContextEvent`（3 参数，含 `FObjectPostSaveContext`，头 `UObject/ObjectSaveContext.h`）
- 保存资产：`UEditorLoadingAndSavingUtils::SavePackages`（头在 `FileHelpers.h`）
- `FJsonObject::Values` 键类型是 `FSharedString`（用 `ToView()` 转 `FString`）
- MD5：`FMD5::HashAnsiString` / `FMD5::HashBytes`
- `CreateAsset(ObjectName, PackagePath, ...)` 的 PackagePath 是**目录**，不是资产全路径
- `-ExecutePythonScript` 模式下脚本执行完编辑器自动退出，验证脚本不能依赖跨 tick 等待
- 控件树构建：`NewObject<UWidget>(WidgetTree, Class, MakeUniqueObjectName, RF_Transactional)`；容器用 `UPanelWidget::AddChild`，单子容器用 `UContentWidget::SetContent`；槽位属性写到返回的 `UPanelSlot` 上
