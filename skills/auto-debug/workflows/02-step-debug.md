# 逐步调试

## 适用场景
已在断点处停住，想逐行跟踪执行。

## 流程

1. **状态就绪** — 执行已停在目标位置

2. **单步走**

   | 操作 | 工具调用 |
   |------|---------|
   | 跳过当前行 | `debug_control(stepOver)` |
   | 进入函数内部 | `debug_control(stepInto)` |
   | 跳出当前函数 | `debug_control(stepOut)` |

3. **每步检查**
   - `get_debug_context()` 或 `evaluate_expression("变量名")`

4. **结束** — `debug_control(continue)` 恢复完整执行
