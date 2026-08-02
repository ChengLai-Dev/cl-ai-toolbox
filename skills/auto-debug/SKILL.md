---
name: auto-debug
description: 调试技能。通过 vsdbg-mcp 设置断点、查看调用栈和变量、单步跟踪，定位崩溃、卡死、逻辑错误等问题的根因。
---

# auto-debug

## 工具参考

| 工具 | 只读？ | 副作用 | 用途 |
|------|--------|--------|------|
| `get_debug_context` | ✅ | 无 | 获取当前位置+调用栈+局部变量（首选） |
| `evaluate_expression` | ✅ | 无 | 检查特定表达式/变量值 |
| `set_breakpoints` | ❌ | 修改 VSCode 断点 | 设断点，自动标记为等待命中对象 |
| `remove_breakpoint` | ❌ | 修改 VSCode 断点 | 移除单个断点 |
| `remove_all_breakpoints` | ❌ | 修改 VSCode 断点 | 清除断点 |
| `wait_next_hit` | ❌ | 自动 continue（若已暂停） | 等 set_breakpoints 设的断点命中 |
| `debug_control` | ❌ | 改变执行流 | continue/stepOver/stepInto/stepOut/pause |
| `check_debug_connection` | ✅ | 无 | 检查调试桥接是否已连接 |

## 黄金法则

1. **用户说"停住了"/"崩了"/"看调用栈"** → 立即 `get_debug_context()`。绝不要先设断点或 continue。
2. **跟踪新路径** → `set_breakpoints(...)` → `wait_next_hit()`，两步就够了。
3. **`wait_next_hit` 内部自动处理**：清旧事件、检测暂停则 continue、命中后自动取上下文。

## 场景索引

| 场景 | 参考文件 |
|------|---------|
| 已停在断点/异常上 | `workflows/00-already-paused.md` |
| 跟踪新的执行路径 | `workflows/01-new-breakpoint.md` |
| 逐步调试 | `workflows/02-step-debug.md` |

详细流程在 `workflows/` 目录下，按需用 `read` 工具加载。
