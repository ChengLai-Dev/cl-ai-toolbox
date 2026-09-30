---
name: ue-mcp
description: 通过编辑器内运行的 UE 官方 MCP（Unreal MCP）读写虚幻工程资产。用 list_toolsets / describe_toolset / call_tool 三跳发现并调用编辑器工具；多步操作（建资产/批量改属性）优先用 execute_tool_script 一次批处理。当需要用 MCP 操作 UE 资产（Input Mapping Context、材质、蓝图、GameplayEffect/GameplayAbility、网格、数据表等）、查询资产字段内容，或用户提到 UE MCP / Unreal MCP 时触发。
---

# Unreal MCP

## 前提

UE 5.8+ 把官方 MCP 服务器做成引擎实验性插件 `ModelContextProtocol`，跑在**编辑器进程内**，通过 HTTP 暴露：

| 项 | 值 |
|---|---|
| 地址 | `http://127.0.0.1:8000/mcp` |
| 协议 | MCP `2025-06-18`；`tools/call` 返回 **SSE 流** |
| 必需插件 | `ModelContextProtocol` + `AllToolsets`（只开前者就只有元工具，没有真实工具集） |

工程侧配置在 `Config/DefaultEditorPerProjectUserSettings.ini` 的 `[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]`：

- `bAutoStartServer=True`，否则编辑器启动后服务器不监听
- `bEnableToolSearch=True` 时 `tools/list` 只暴露 3 个元工具
- 一个端口只能被一个编辑器实例占用，多开编辑器会互相抢

**编辑器没开 = 服务器不在 = 所有工具调用失败。** 先确认端口在监听。

## 三跳发现协议

`bEnableToolSearch` 打开时（默认），协议面只有三个元工具，真实工具**必须用 `call_tool` 包装调用**，不能当顶层工具直接调：

```
list_toolsets()                                → toolset 名字清单
describe_toolset(toolset_name)                 → 该 toolset 全部工具的 inputSchema / outputSchema
call_tool(toolset_name, tool_name, arguments)  → 执行
```

**不要跳过 describe_toolset。** 参数名必须从 `inputSchema` 读，猜必错。

## 批量执行（execute_tool_script）

逐次 `call_tool` 一次网络往返。多步操作（建资产 → 写属性 → 读回 → 落盘）**必须批处理**，
否则开销随资产数量线性增长（实测：建 2 个资产 21 次调用，批处理后 2 次）。

`editor_toolset.toolsets.programmatic.ProgrammaticToolset.execute_tool_script`：

- 沙盒 Python；注入 `execute_tool("<工具全名>", json字符串)`
- 必须定义 `run()` 并返回 `dict`
- 允许 import：`json` `math` `datetime` `copy` `re` `time`
- **带编辑器事务**：脚本抛错自动回滚，不会留下半成品资产
- 使用前调一次 `get_execution_environment`（每会话一次）

模板：

```python
import json

def tool(name, payload):
    return execute_tool(name, json.dumps(payload))

def run():
    bp = tool("editor_toolset.toolsets.blueprint.BlueprintTools.create", {
        "folder_path": "/Game/MyFolder",
        "asset_name": "GE_MyEffect",
        "asset_type": {"refPath": "/Script/GameplayAbilities.GameplayEffect"},
    })["returnValue"]
    cdo = tool("editor_toolset.toolsets.blueprint.BlueprintTools.get_default_object",
               {"blueprint": bp})["returnValue"]
    tool("editor_toolset.toolsets.object.ObjectTools.set_properties", {
        "instance": cdo, "values": json.dumps({"durationPolicy": "Instant"}),
    })
    readback = json.loads(tool(
        "editor_toolset.toolsets.object.ObjectTools.get_properties",
        {"instance": cdo, "properties": ["durationPolicy"]})["returnValue"])
    tool("editor_toolset.toolsets.asset.AssetTools.save_assets",
         {"asset_paths": [bp["refPath"].split(".")[0]]})
    return {"durationPolicy": readback["durationPolicy"]}
```

> 建资产 / 写属性 / 三件套结构体 的完整配方见
> [references/authoring-recipes.md](references/authoring-recipes.md)。

## 黄金法则

1. **写之前先读**。改**不熟悉的**资产前必须先 `list_properties` 拿到准确属性名 —— 属性名不能猜，猜错会**静默失败**（工具返回成功但值没变）。已知类型的字段（如 GameplayEffect、IMC）优先查本 skill / 项目文档，避免 `list_properties` 的大输出。
2. **在副本上做写入试验**。动真实资产前先 `duplicate` 出一份临时副本，在副本上验证写法，最后 `delete`。写入出错会留下半成品状态。
3. **写操作是内存态**。`set_properties` 等只改内存对象，必须再调 `save_assets` 才落盘。
4. **工具名大小写敏感**。`ListSkills` 能过，`list_skills` 报 `Unknown tool`。
5. **同名不同层**。属性路径写错层级，会得出完全相反的结论。
6. **两层调用名的写法不同**。MCP 层：`tool_name` 用**短名**（`create`）、`toolset_name` 用全名；脚本内：`execute_tool` 用**全名**（`editor_toolset.toolsets.blueprint.BlueprintTools.create`）。把全名传给 `call_tool` 会报 `Unknown tool`。

## 已知陷阱

| 现象 | 原因 | 对策 |
|---|---|---|
| `get_properties` 报参数缺失 | `properties` 是**必填**数组 | 显式传属性名列表 |
| 读某字段恒为空数组 | 读的是**废弃字段**，数据已迁到新字段 | 读新字段，见 `references/pitfalls.md` |
| `set_properties` 返回 true 但值没变 | 属性名猜错，或写了非 EditAnywhere 字段 | 先 `list_properties` 校准；返回 true 后**必须读回验证** |
| 写 Instanced 子对象报 "is not a subobject of the property owner" | 抄了别的资产的子对象 `refPath` | 传**类路径**让引擎自己实例化 |
| 写入报错后发现字段被改坏 | 复合属性的写入**不原子** | 在副本上试；出错后重新读回确认状态 |
| `call_tool` 报 Unknown tool | 名字大小写不符，或把**全名**（`...BlueprintTools.create`）当成了 `tool_name` | `tool_name` 只填**短名**（`create`）；大小写从 `describe_toolset` 复制 |

案例与引擎源码依据见 [references/pitfalls.md](references/pitfalls.md)。

## 安全写入流程

```
1. duplicate(源资产 → 临时副本)
2. load_asset(副本) 取到 {refPath} 实例引用
3. get_properties(副本, [属性名])      # 记录基线
4. set_properties(副本, 新值)          # 试验
5. get_properties(副本, [属性名])      # 读回验证 ← 必做
6. is_dirty(源资产)                    # 确认源资产未被牵连
7. delete(临时副本)
8. 验证通过后，才对真实资产重复 4-5
9. save_assets(...)                    # 落盘
```

## 参考

- `references/pitfalls.md` — 已踩实的陷阱案例、根因与排查手法
- `references/authoring-recipes.md` — 建资产 / 写属性 / 落盘的通用配方（含占位符，项目私有值见项目文档）
