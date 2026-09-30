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
    "name": "CanvasPanel_0",
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
| `contentHash` | 树内容的规范化 MD5（key 排序），**由插件维护，AI 不要动** |
| `class` | 类的完整对象路径。C++ 类如 `/Script/UMG.TextBlock`；蓝图类如 `/Game/UI/WBP_Avatar.WBP_Avatar_C` |
| `className` | 短名，信息性，导入忽略 |
| `name` | 控件名，唯一。新建时若重名会自动加后缀 |
| `isVariable` | 是否暴露为蓝图变量 |
| `properties` | 可编辑属性表 |
| `slot` | 父容器分配的槽位（根节点为 `null` 或省略） |
| `children` | 子控件数组 |

## 属性值格式

导出规则：**`CPF_Edit` 且非 Transient / Deprecated / BlueprintReadOnly / delegate** 的属性。也就是说——

> **导出哪个属性，AI 才能改哪个属性。**

值按类型输出：

| 属性类型 | JSON 值 |
|---|---|
| `bool` | JSON bool |
| 整数/浮点 | JSON number |
| 枚举 | 枚举名字符串，如 `"Left"`、`"SelfHitTestInvisible"` |
| `FText` / `FString` / `FName` | 纯文本字符串（**要显示什么就直接写什么**） |
| 结构体 | 引擎 `ExportTextItem` 文本格式，如 `"(SpecifiedColor=(R=1.000000,G=1.000000,B=1.000000,A=1.000000))"` |
| 对象引用 | 路径字符串，如 `"/Game/UI/Textures/T_Icon.T_Icon"` 或 `"None"` |

结构体文本样例：

```
线性颜色   (R=1.000000,G=0.500000,B=0.000000,A=1.000000)
Slate 颜色 (SpecifiedColor=(R=1.000000,G=1.000000,B=1.000000,A=1.000000))
边距       (Left=10.000000,Top=5.000000,Right=10.000000,Bottom=5.000000)
FAnchorData (Offsets=(Left=-300.000000,Top=60.000000,Right=300.000000,Bottom=130.000000),Anchors=(Minimum=(X=0.500000,Y=0.000000),Maximum=(X=0.500000,Y=0.000000)),Alignment=(X=0.500000,Y=0.000000))
```

未知属性名会在导入时**告警并跳过**，不会报错中断。

## 槽位属性（实测更正）

插件自带的 `Docs/SchemaReference.md` 里 CanvasPanelSlot 那张表是**错的**。它列的 `Position` / `Size` / `Anchors` / `Alignment` 在引擎里只是 `UFUNCTION` 存取器，不是 UPROPERTY，反射序列化碰不到。

**实测真实导出**（与 `Engine/Source/Runtime/UMG/Public/Components/CanvasPanelSlot.h` 一致）：

```json
"slot": {
  "class": "/Script/UMG.CanvasPanelSlot",
  "className": "CanvasPanelSlot",
  "properties": {
    "LayoutData": "(Offsets=(Left=-300.000000,Top=60.000000,Right=300.000000,Bottom=130.000000),Anchors=(Minimum=(X=0.500000,Y=0.000000),Maximum=(X=0.500000,Y=0.000000)),Alignment=(X=0.500000,Y=0.000000))",
    "bAutoSize": false,
    "ZOrder": 0
  }
}
```

`UCanvasPanelSlot` 的 UPROPERTY 只有三个：`LayoutData`（`FAnchorData`）、`bAutoSize`、`ZOrder`。
`FAnchorData` = `{ FMargin Offsets; FAnchors Anchors; FVector2D Alignment; }`。

`Offsets` 在锚点重合（Minimum == Maximum）时表达的是**相对锚点的矩形**：`Left/Top` 是左上偏移，`Right/Bottom` 是右下偏移。要让控件中心落在锚点上取 `Left=-Width/2, Top=-Height/2, Right=Width/2, Bottom=Height/2`。

**导出时会省略值为 0 的分量**，例如这个导出结果只有 `Right`/`Bottom`：

```
"LayoutData": "(Offsets=(Right=100.000000,Bottom=30.000000),Anchors=(...),Alignment=(...))"
```

VerticalBox / HorizontalBox 的槽：`Padding`、`Size`、`HorizontalAlignment`、`VerticalAlignment`。

- `Size` 是 `FSlateChildSize`，文本形如 `(Value=1.000000,SizeRule=Fill)`；枚举是 **`Automatic`** 或 `Fill`
- `HorizontalAlignment`：`HAlign_Fill` / `HAlign_Left` / `HAlign_Center` / `HAlign_Right`
- `VerticalAlignment`：`VAlign_Fill` / `VAlign_Top` / `VAlign_Center` / `VAlign_Bottom`

`UButtonSlot`：`Padding`、`HorizontalAlignment`、`VerticalAlignment`。

> 插件文档里写的 `Size.Rule = Auto | Fill` **属性名和枚举值都不对**（2026-09 已订正仓库内文档）。

**可靠做法**：需要某个控件的准确属性名与格式时，**先在编辑器里手工摆好一个 → Ctrl+S 回写 JSON → 照抄**。不要靠文档。

## 构建与验证

```powershell
# 构建（见下文的 Live Coding 坑）
& "<engine>/Build/BatchFiles/Build.bat" <Project>Editor Win64 Development -Project="<path>/<Project>.uproject" -NoHotReloadFromIDE -WaitMutex

# 跑插件的 3 个自动化测试（含端到端：JSON → 资产 → 回写 JSON）
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

注意**完整导出会包含大量默认值属性**（一个 `TextBlock` 能导出 36 个字段，多数是默认值）。手写时只写想改的即可；这是当前已知的"JSON 偏大"问题。

## 双向同步与冲突

```
AI 改 UIWidgets/**/*.json  ──ticker(1s)──> 重建 WidgetBlueprint ──> 保存
编辑器改 UMG ──Ctrl+S──> PackageSavedWithContextEvent ──hash 对比──> 回写 JSON / 写 .conflict
```

- **防回环**：导入器保存资产时通过 `ImportingPackageNames` 跳过反向导出
- **冲突**：两边同时改时，编辑器版本存为 `xxx_editor_conflict.json`，主文件保留 AI 版本，**绝不静默覆盖**，需人工合并

## 菜单（Tools > Widget Json Bridge）

| 菜单项 | 作用 |
|---|---|
| Export Edited Widget to JSON | 把当前打开的 WBP 导出为 JSON（手动触发，**无视冲突检测直接覆盖**） |
| Import All JSON Files | 清空同步记录并全量重导入 `UIWidgets/` 下所有 JSON |
| Open Sync Folder | 打开 `UIWidgets` 目录 |
| Open Docs Folder | 打开插件文档目录 |

## 已知限制

- 事件绑定（`OnClicked` 等）、属性绑定、`BindWidget`、动画、跨 WBP 命名槽引用 —— **均未支持**
- 删除 JSON 文件**不会**删除资产，需手动删
- 导出含默认值属性，JSON 偏大（可做 CDO 差异过滤缩小）
- 插件 `Binaries` 不随 git，引擎升级后需按新版本重编

## 插件自身的构建与测试

```powershell
# 构建（编辑器开着会失败，先关）
& "D:\Code\UE_5.8\Engine\Build\BatchFiles\Build.bat" GreyCrownEditor Win64 Development -Project="D:\Code\UE Projects\GreyCrown\GreyCrown.uproject" -WaitMutex

# 测试（结果看 GreyCrown/Saved/Logs/GreyCrown.log 里的 "Test Completed" 行）
& "D:\Code\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "D:/Code/UE Projects/GreyCrown/GreyCrown.uproject" -unattended -nosplash -NullRHI -log -ExecCmds="Automation RunTests WidgetJsonBridge" -TestExit="Automation Test Queue Empty"
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
