---
name: auto-debug
description: AI 断点调试技能。通过 vsdbg-mcp 设置断点、管理 Watchlist、等待命中、分析调试信息定位 Bug 根因。
---

# AI 自动查 Bug 技能

通过断点调试自动化帮助用户定位 Bug 原因。

## 流程概览

```
信息收集 → 连接检查 → 设置断点 → 注册 Watchlist → wait_next_hit 循环 → 输出报告
 Phase 1    Phase 2    Phase 3     Phase 4         Phase 5        Phase 6
```

| Phase | 做什么 | 核心工具 |
|-------|--------|---------|
| 1. 信息收集 | 理解 Bug 现象，定位相关代码，确定可疑位置 | 代码搜索 |
| 2. 连接检查 | 检查 vsdbg 调试连接状态 | `check_debug_connection` |
| 3. 设置断点 | 在关键位置设断点，优先使用条件断点 | `set_breakpoints` |
| 4. 注册 Watchlist | 告诉 MCP 本轮关心哪些断点（可以全量或子集） | `watchlist_manage` |
| 5. wait_next_hit 循环 | 循环调用 `wait_next_hit`，逐个命中、分析、继续 | `wait_next_hit` + `debug_control` |
| 6. 输出报告 | 输出根因、变量状态、调用路径、修复建议 | — |

> Phase 4-5 可反复调整：每次调整断点或 Watchlist 后，继续 `wait_next_hit`。

## 前置条件
1. VSCode 已安装 `vsdbg-bridge` 扩展 (v1.1.0+)
2. 调试会话已启动（已 attach 到游戏进程）
3. vsdbg-mcp MCP 服务已启用

## 核心概念：Watchlist

Watchlist 是 MCP 端独立维护的**关心断点集**，与 VSCode 中的断点设置解耦。

| 概念 | 说明 |
|------|------|
| **断点（Breakpoint）** | VSCode 中实际存在的断点。通过 `set_breakpoints` 设置 |
| **Watchlist** | MCP 端记录的 `(filePath, line)` 集合，告诉 `wait_next_hit` 哪些断点应该停下分析 |

**为什么需要 Watchlist？**
- 第一轮你可能想等所有断点都触发一遍，拿到全量信息
- 第二轮你只想关注某条路径上的断点，其余透明跳过
- 不用反复设置/删除断点，只需调整 Watchlist

## 详细流程

### Phase 1: 信息收集
1. **理解 Bug 描述**: 询问用户 Bug 的具体表现
2. **定位相关代码**: 根据 Bug 描述，使用代码搜索定位可能相关的文件和函数
3. **确定可疑位置**: 分析代码逻辑，列出需要检查的关键位置

### Phase 2: 连接检查

在未知连接是否建立之前，**必须**先检查 vsdbg 调试连接状态：

1. **调用 `check_debug_connection`** 检查连接状态
2. **根据结果决定后续流程**：

| 连接状态 | 处理方式 |
|----------|---------|
| 已连接 | 直接进入 Phase 3（设置断点） |
| 未连接 | 询问用户，进入阻塞等待循环 |

### Phase 3: 设置断点

在关键位置设置断点：

```
```
调用: set_breakpoints
参数:
{
  "breakpoints": [
    {"file_path": "文件绝对路径", "line": 行号, "condition": "可选条件表达式"}
  ]
}
```
```

**断点设置原则**:
- 在函数入口处设置，检查是否被调用
- 在数据处理关键点设置，检查数据状态
- 在条件分支处设置，检查逻辑走向
- **优先使用条件断点**减少不必要的中断

### Phase 4: 注册 Watchlist

告诉 MCP 本轮关心哪些断点。可以全量关心，也可以只关心子集：

```
调用: watchlist_manage
参数:
{
  "action": "set",        // set/add/remove/clear/list
  "breakpoints": [
    {"file_path": "...", "line": 10},
    {"file_path": "...", "line": 50}
  ]
}
```

| action | 行为 |
|--------|------|
| `set` | 替换整个 Watchlist |
| `add` | 追加条目（已有则忽略） |
| `remove` | 移除指定条目 |
| `clear` | 清空 Watchlist |
| `list` | 查看当前 Watchlist |

### Phase 5: wait_next_hit 循环

**核心工具**。调用后会：

1. 内部自动 `continue` 并等待下一个断点事件
2. 命中断点 → 检查是否在 Watchlist 中
   - **在 Watchlist 中** → 返回上下文给 AI 分析
   - **不在 Watchlist 中** → 自动 `continue`，透明跳过
3. 调试会话结束 → 返回 `session_ended` 通知

```
调用: wait_next_hit
参数:
{
  "timeout": 60,          // 总超时（含内部循环）
  "auto_context": true    // 命中后自动获取上下文
}
```

返回示例（命中）：
```json
{
  "success": true,
  "hit": true,
  "location": {"filePath": "...", "line": 50},
  "context": {
    "location": {"filePath": "...", "line": 50},
    "variables": {"Local": [...]},
    "call_stack": [...]
  },
  "session_ended": false
}
```

返回示例（会话结束）：
```json
{
  "success": true,
  "hit": false,
  "session_ended": true,
  "session_name": "CLEngine2D"
}
```

返回示例（超时）：
```json
{
  "success": true,
  "hit": false,
  "session_ended": false,
  "timeout": true,
  "message": "等待 60 秒后超时，未命中 Watchlist 中的断点"
}
```

**典型循环**：

```
# 第一轮：全量等待
set_breakpoints(breakpoints=[A, B, C])
watchlist_manage(action="set", breakpoints=[A, B, C])

while True:
    result = wait_next_hit()       # 自动 continue → 等待下一命中
    if not result["hit"]:
        break                      # 超时或会话结束，退出循环
    analyze_context(result["context"])

# 第二轮：只看关键路径
watchlist_manage(action="remove", breakpoints=[A])  # 不再关心 A
result = wait_next_hit()  # 只会在 B 或 C 停下
```

**注意事项**：
- `wait_next_hit` **每次被调用时自动先 `continue`**（若程序暂停），然后进入等待
- 非 Watchlist 断点命中时内部自动再 `continue`，透明跳过
- AI **不需要手动调 `continue`**，只需反复调 `wait_next_hit` 即可遍历所有关心断点
- 如果 Watchlist 为空，`wait_next_hit` 会直接返回错误

### Phase 6: 输出报告

```markdown
## Bug 分析报告

### 问题描述
[用户描述的 Bug 现象]

### 根因定位
- **文件**: xxx.cpp
- **行号**: 123

### 问题分析
[详细说明为什么这段代码会导致 Bug]

### 关键变量状态
| 变量 | 实际值 | 预期值 |
|------|--------|--------|

### 调用路径
[关键调用链]

### 修复建议
[具体的修复方案]
```

## 可用 MCP 工具

| 分类 | 工具 | 说明 |
|------|------|------|
| **连接管理** | `check_debug_connection` | 检查调试连接状态 |
| **断点管理** | `set_breakpoints` | 批量设置断点（可选条件） |
| | `remove_breakpoint` | 移除单个断点 |
| | `remove_all_breakpoints` | 移除所有 AI 断点，不影响手动断点 |
| **Watchlist** | `watchlist_manage` | 管理关心断点集 |
| **核心等待** | `wait_next_hit` | ⭐ 等待下一命中，自动 continue 跳过非关心断点 |
| **调试控制** | `debug_control` | continue/stepOver/stepInto/stepOut/pause/restart/stop |
| **信息查询** | `evaluate_expression` | 评估表达式 |
| | `get_debug_context` | 获取完整上下文（位置+变量+调用栈） |

## 使用示例

**用户**: 帮我查一下点击活动按钮后数据不刷新的 Bug

**AI 执行流程**:
1. 搜索活动相关代码，定位 `ActivityPanel.cpp` 中的可疑位置
2. 设置断点:
   - `set_breakpoints(breakpoints=[{file_path: "ActivityPanel.cpp", line: 96}, {file_path: "ActivityPanel.cpp", line: 200}])`
3. 注册 Watchlist（关心全部）:
   - `watchlist_manage(action="set", breakpoints=[{A:96}, {B:200}])`
4. 提示用户: "请打开活动面板并点击按钮"
5. 循环调用 `wait_next_hit()` 逐个命中、分析
6. 若想只看某个后续路径，调整 Watchlist 后继续

## 注意事项

1. **Watchlist 不能为空**: 调用 `wait_next_hit` 前必须先通过 `watchlist_manage` 设置关心断点
2. **先设断点，再注册 Watchlist**: `set_breakpoints` 只负责在 VSCode 中创建断点，`watchlist_manage` 才告诉 MCP 等哪些
3. **条件断点优先**: 循环/高频函数中务必使用条件断点
4. **超时处理**: `wait_next_hit` 有内部超时，合理设置 timeout（建议 30-60 秒）
5. **调试结束通知**: 如果程序跑完或被用户停止，`wait_next_hit` 会返回 `session_ended`，AI 应据此判断"代码执行完毕但未命中目标断点"
