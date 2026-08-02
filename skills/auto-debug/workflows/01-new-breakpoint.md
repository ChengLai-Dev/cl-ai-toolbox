# 跟踪新的执行路径

## 适用场景
想观察某段代码是否被执行，或在特定位置检查运行时的变量状态。

## 流程

1. **确认未在暂停状态** — 如果当前已暂停，先 `debug_control(continue)` 让程序跑起来
   - 例外：如果要在当前执行点之前设断点，可以在暂停状态下直接设

2. **设置断点** — `set_breakpoints(breakpoints=[...])`
   - 热路径优先用条件断点（`condition` 参数）
   - 每个条目包含：`file_path`（绝对路径）+ `line` + 可选 `condition`
   - **自动注册为等待命中对象**，无需额外步骤

3. **等待命中**
   ```
   wait_next_hit(timeout=60)
   ```
   - 内部自动处理：清旧事件、检测暂停则 continue、命中后返回上下文
   - 重复 `wait_next_hit()` 直至超时或会话结束
   - 需要中途调整关注点时，调 `set_breakpoints` 再设一次即可

4. **清理** — 完成后 `remove_all_breakpoints()` 清除断点
