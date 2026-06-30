# VSCode Debug Bridge 扩展

VSCode 扩展，为 AI 助手提供调试信息访问能力。

## 功能

- ✅ **获取/设置/移除断点** - 完整的断点管理
- ✅ **获取变量值** - 支持局部和全局变量
- ✅ **获取调用栈** - 完整的调用层次
- ✅ **调试控制** - 继续、单步、暂停、重启、停止
- ✅ **表达式求值** - 在调试上下文中计算表达式
- ✅ **自动启动** - VSCode 启动时自动启动桥接服务

## 安装步骤

### 1. 安装依赖

```bash
cd mcp_tools/vsdbg_mcp/vscode-extension
npm install
```

### 2. 编译扩展

```bash
npm run compile
```

### 3. 打包扩展

```bash
npm run package
```

这会生成 `vsdbg-bridge-1.0.0.vsix` 文件。

### 4. 安装到 VSCode

方式 A: 命令行安装
```bash
code --install-extension vsdbg-bridge-1.0.0.vsix
```

方式 B: VSCode 中安装
1. 打开 VSCode
2. 按 `Ctrl+Shift+P` 打开命令面板
3. 输入 "Install from VSIX"
4. 选择生成的 `.vsix` 文件

### 5. 重启 VSCode

安装后重启 VSCode，扩展会自动启动桥接服务器。

## 使用方法

### 自动模式（推荐）

扩展默认在 VSCode 启动时自动启动桥接服务器，无需任何操作。

### 手动控制

按 `Ctrl+Shift+P` 打开命令面板，可以使用以下命令：

- `Debug Bridge: 启动调试桥接服务器`
- `Debug Bridge: 停止调试桥接服务器`
- `Debug Bridge: 查看桥接服务器状态`

### 状态栏

状态栏右侧会显示桥接服务器状态：
- `$(debug) Bridge: 19530` - 运行中
- `$(debug-disconnect) Bridge: 已停止` - 已停止

## 配置选项

在 VSCode 设置中搜索 "vsdbg-bridge"：

| 选项 | 默认值 | 说明 |
|-----|-------|------|
| `vsdbg-bridge.port` | 19530 | 桥接服务器监听端口 |
| `vsdbg-bridge.autoStart` | true | VSCode 启动时自动启动 |

## 开发调试

1. 在 VSCode 中打开扩展目录
2. 按 `F5` 启动扩展开发主机
3. 在新窗口中测试扩展功能

## 架构

```
┌─────────────────┐     stdio      ┌─────────────────┐     TCP:19530    ┌─────────────────┐
│   CodeMaker     │ ────────────▶ │  vsdbg_server   │ ───────────────▶ │  VSCode 扩展    │
│   (AI 助手)     │ ◀──────────── │   (MCP服务)     │ ◀─────────────── │  (本扩展)       │
└─────────────────┘               └─────────────────┘                  └─────────────────┘
                                                                              │
                                                                              │ vscode.debug API
                                                                              ▼
                                                                       ┌─────────────────┐
                                                                       │  VSCode 调试器  │
                                                                       └─────────────────┘
```

## 故障排除

### 端口被占用

修改设置中的端口号，同时修改 MCP 服务的端口配置。

### 扩展未启动

1. 检查 VSCode 开发者工具 (`Ctrl+Shift+I`) 中的控制台输出
2. 确认扩展已启用（扩展列表中查看）

### 无法获取变量

确保：
1. 调试会话已启动
2. 程序在断点处暂停
3. 不是在"运行中"状态
