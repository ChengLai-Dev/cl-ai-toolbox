# 陷阱案例

## 1. 同名不同层：IMC 的 `mappings` vs `defaultKeyMappings.mappings`

**现象**：对任何 Input Mapping Context 调 `get_properties(["mappings"])` 都返回 `[]`。据此会误判"映射引用丢了"。

**真实结构**（`UInputMappingContext`）里两个字段同名但不同层：

```
InputMappingContext
├── mappings                    ← 5.7 起废弃，读回恒为 []
├── defaultKeyMappings          ← 真实数据在这
│   └── mappings
├── mappingProfileOverrides
├── inputModeFilterOptions
├── inputModeQueryOverride
├── registrationTrackingMode
└── contextDescription
```

**根因**（引擎源码 `Engine/Plugins/EnhancedInput/Source/EnhancedInput/`）：

顶层 `Mappings` 已标记废弃：

```cpp
UE_DEPRECATED(5.7, "Use the DefaultKeyMappings struct instead.")
UPROPERTY(config, BlueprintReadOnly, Category = "Mappings", ...)
TArray<FEnhancedActionKeyMapping> Mappings;
```

且 `PostLoad()` 会把旧数据**搬空**：

```cpp
if (GetLinkerCustomVersion(...) < FFortniteSeasonBranchObjectVersion::EnhancedInputMappingContextProfileMappingsUpdate)
{
    // We converted from a TArray<FEnhancedActionKeyMapping> to a struct so that it is consistent with the profile override types
    DefaultKeyMappings.Mappings = MoveTemp(Mappings);
}
```

`MoveTemp` 之后源数组为空 → 读出来**必然是 `[]`**，与"引用是否丢失"无关。

引擎自己的访问器也不看旧字段：

```cpp
const TArray<FEnhancedActionKeyMapping>& GetMappings() const { return DefaultKeyMappings.Mappings; }
```

**对策**：只读 `defaultKeyMappings.mappings`。写入同理，写顶层废弃字段没有任何意义。

## 2. Instanced 子对象不能跨资产复用 refPath

**现象**：把 A 资产里的 Instanced 子对象 refPath 写进 B 资产：

```
/Game/A.A:InputModifierNegate_0 is not a subobject of the property owner
for instanced property 'Modifiers'
SetObjectProperties on '/Game/B.B' (InputMappingContext): the following
properties could not be set: defaultKeyMappings
```

**并且写入不原子**：整个复合属性没赋上，但读回时该字段已被改成 `"None"`。

**对策**：传**类路径**，让引擎为目标资产实例化一个：

```json
{"modifiers": [{"refPath": "/Script/EnhancedInput.InputModifierNegate"}]}
```

写成功后读回会变成 `/Game/B.B:InputModifierNegate_1`。

## 3. 所有写入都是内存态

`set_properties` 只改内存对象。不调 `save_assets` 就不落盘，关编辑器即丢。

`save_assets` 传**空数组** = 保存所有脏资产；传路径数组 = 只存这些。

## 4. `read_file` / `write_file` 只碰纯文本

`AssetTools.read_file` / `write_file` 的可见范围是 `/Game/`、已启用插件的 `Content/`、工程 `Saved/`，且**仅纯文本格式**。

**不能**用来读写 `.uasset` 二进制。要改资产必须 `load_asset` 之后再走 `ObjectTools`。

## 5. UE 自带的 AgentSkill 是两层

引擎自带 skill 机制（`ToolsetRegistry.AgentSkillToolset`），工具名 PascalCase：

| 工具 | 作用 |
|---|---|
| `ListSkills` | 返回 `skill 路径 → 一句话描述` |
| `GetSkills` | 传路径数组，返回全文 `Instructions` |
| `CreateSkill` | 在指定文件夹建一个 `UAgentSkill` 蓝图资产 |
| `UpdateSkill` | 改蓝图形态 skill 的 Description / Instructions |

注意：

- 路径是 **UClass 路径**，蓝图形态带 `_C` 后缀，如 `/Game/Skills/MySkill.MySkill_C`
- 只有**蓝图资产形态**能被 `UpdateSkill` 改。C++ 原生类（`CLASS_Native`）和 Python 动态类（`RF_Transient`）会被拒绝——它们没有资产承载，改了 CDO 也会在模块重载/编辑器重启后丢失
- 项目设置里可用 `AgentSkillBlockedNames` / `AgentSkillAllowedNames`（支持正则，Block 优先）过滤
- 这些 skill 的描述**不会**预注入上下文，必须先主动调 `ListSkills` 才知道存在

## 6. `describe_toolset` 的输出本身就是使用说明

官方没有独立文档。使用说明被拆散塞在：

1. **tool description** —— 来自 C++ doc comment 或 Python docstring
2. **toolset description** —— 常内嵌 workflow 段落。例：UMGToolSet 明确写了「每个 widget/slot 都必须先 `ObjectTools.list_properties` 拿到准确属性名，跳过这步会导致 `set_properties` 静默失败或写错属性」
3. **AgentSkill 的 Instructions**

遇到不熟悉的 toolset，`describe_toolset` 的返回值得完整读一遍，别只看工具名。

## 7. 排查手法：怎么区分"工具不支持"和"数据真的是空"

读到一个字段为空时，**不能直接下"数据丢了"的结论**。必须先排除三种可能：

| 可能 | 怎么排除 |
|---|---|
| ① 读错了层级 | 用 `list_properties` 看完整属性树，注意同名不同层的字段 |
| ② 读的是废弃/运行时字段 | 找同一语义的其他字段对照 |
| ③ 工具真的不支持该类型 | **换个能读的同类样本做对照** |

本案例里第 ③ 条的排除过程：用 `get_properties(["defaultKeyMappings"])` 在同一个 IMC 上成功读出了嵌套数组（含 struct、object 引用、enum 字符串），证明工具**支持**这类类型；那么顶层 `mappings` 读空就只能是 ①② 的原因，而不是工具的锅。

**没有对照就下结论，是这类排查最常见的错误。**

## 8. 协议面事实（避免误判工具能力）

实测 UE MCP 服务器的能力声明：

| 方法 | 状态 |
|---|---|
| `tools/list` / `tools/call` | ✅ 支持；`listChanged: true`；带分页（nextCursor） |
| `resources/list` | 方法存在但**恒返回 `{"resources": []}`**（引擎里只有测试 mock 实现了 provider） |
| `resources/templates/list` | ❌ `-32601 unknown method` |
| `prompts/*` | ❌ `-32601 unknown method` |

含义：**不要指望通过 MCP resources 拿到工程文档**。想让 AI 读到某份说明，只能靠它主动 `read_file`（且文件必须在可见范围内、且是纯文本），或者把内容写进 skill 的描述/正文。

另：`tools/call` 返回的是 **SSE 流**。用 `httpx` 之类的客户端时，UE 的 HTTP 实现对流式响应不带 `Content-Length` 或 chunked 编码，客户端可能一直等到活动超时（约 30s）才认为响应结束。做一次性探针脚本时给足超时，或缩短活动超时。

## 9. `call_tool` 的 `tool_name` 必须是短名，不能是全名

**现象**：照抄 `describe_toolset` 返回的 `name` 直接调：

```
call_tool(tool_name="editor_toolset.toolsets.programmatic.ProgrammaticToolset.get_execution_environment",
          toolset_name="editor_toolset.toolsets.programmatic.ProgrammaticToolset")
→ Unknown tool editor_toolset.toolsets.programmatic.ProgrammaticToolset.get_execution_environment
```

**根因**：两边约定不同。

| 位置 | 写法 |
|---|---|
| MCP 层 `call_tool(tool_name, toolset_name, ...)` | `tool_name` = **短名**（`get_execution_environment`） |
| 脚本内 `execute_tool(full_name, ...)` | **全名**（`editor_toolset....ProgrammaticToolset.get_execution_environment`） |

**对策**：`call_tool` 时把 `describe_toolset` 返回的 `name` 在**最后一个点**处切开，右边给 `tool_name`，左边给 `toolset_name`。报错信息里回显的就是你传的全名，可据此自查。

## 10. 逐次调用建资产会留"半成品"；用脚本事务兜住

**现象**：直接 `create` → `set_properties` → `save_assets` 一条条调，中途任一步失败（属性名猜错、类型不匹配、脚本被中断），资产已经建出来了但配置是半成品，且可能已被 `save_assets` 落盘。

**根因**：`call_tool` 是**无序、无事务**的独立请求；而 `create` 本身是立即生效的。

**对策**：把多步操作放进 `ProgrammaticToolset.execute_tool_script`。它内部用 `_TransactionalScriptRunner`
包了编辑器事务（源码 `editor_toolset/toolsets/programmatic.py`，类 `_TransactionalScriptRunner`）：
脚本正常返回才 `commit()`，抛异常/取消则回滚。这样"建 + 配 + 验证 + 落盘"要么全成，要么全退。

附带收益：往返次数从 `O(N)` 降到 `O(1)`。

