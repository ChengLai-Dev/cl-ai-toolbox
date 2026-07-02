# -*- coding: utf-8 -*-
# [AI-GENERATED]
"""
VSCode Debug MCP Server
用于获取VSCode调试信息的MCP服务

功能:
1. 获取当前断点位置和变量值
2. 获取调用栈信息
3. 获取所有断点列表
4. 控制调试流程（继续、单步等）

使用方法:
1. 在VSCode中安装配套的调试助手扩展 (vsdbg-bridge-1.0.0.vsix)
2. 启动调试会话
3. MCP服务自动连接并提供调试信息
"""

import json
import socket
import sys
import os
import threading
import queue
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 默认调试桥接服务器配置
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19530
NOTIFICATION_PORT = 19531

# 断点事件队列（用于存储 SSE 推送的断点事件）
breakpoint_event_queue: queue.Queue = queue.Queue()
sse_connected = False
sse_thread: Optional[threading.Thread] = None

# 关心断点集（Watchlist）：本轮 AI 关心的 (filePath -> line 集合)
# 仅用于 wait_next_hit 判断是否应透明跳过
watchlist: Dict[str, set] = {}
_watchlist_lock = threading.Lock()


class VSCodeDebugClient:
    """VSCode调试桥接客户端"""
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
    
    def connect(self) -> bool:
        """连接到调试桥接服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception as e:
            self.connected = False
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.connected = False
    
    def send_command(self, command: str, params: Dict = None) -> Dict:
        """发送命令并获取响应"""
        if not self.connected:
            if not self.connect():
                return {"success": False, "error": "无法连接到调试桥接服务器，请确保VSCode调试助手已启动"}
        
        try:
            request = {
                "command": command,
                "params": params or {}
            }
            
            # 发送请求
            data = json.dumps(request).encode('utf-8')
            length = len(data)
            header = f"{length:08d}".encode('utf-8')
            self.socket.sendall(header + data)
            
            # 接收响应
            header = self.socket.recv(8)
            if not header:
                raise ConnectionError("连接已关闭")
            
            length = int(header.decode('utf-8'))
            response_data = b""
            while len(response_data) < length:
                chunk = self.socket.recv(min(4096, length - len(response_data)))
                if not chunk:
                    raise ConnectionError("连接已关闭")
                response_data += chunk
            
            return json.loads(response_data.decode('utf-8'))
        
        except Exception as e:
            self.connected = False
            return {"success": False, "error": str(e)}
    
    def get_breakpoints(self) -> Dict:
        """获取所有断点列表"""
        return self.send_command("getBreakpoints")
    
    def get_current_location(self) -> Dict:
        """获取当前断点位置"""
        return self.send_command("getCurrentLocation")
    
    def get_variables(self, scope: str = "all") -> Dict:
        """获取当前作用域的变量值
        
        Args:
            scope: 作用域类型 - "local", "global", "all"
        """
        return self.send_command("getVariables", {"scope": scope})
    
    def get_call_stack(self) -> Dict:
        """获取调用栈信息"""
        return self.send_command("getCallStack")
    
    def debug_continue(self) -> Dict:
        """继续执行"""
        return self.send_command("continue")
    
    def debug_step_over(self) -> Dict:
        """单步跳过"""
        return self.send_command("stepOver")
    
    def debug_step_into(self) -> Dict:
        """单步进入"""
        return self.send_command("stepInto")
    
    def debug_step_out(self) -> Dict:
        """单步跳出"""
        return self.send_command("stepOut")
    
    def debug_pause(self) -> Dict:
        """暂停执行"""
        return self.send_command("pause")
    
    def debug_restart(self) -> Dict:
        """重启调试"""
        return self.send_command("restart")
    
    def debug_stop(self) -> Dict:
        """停止调试"""
        return self.send_command("stop")
    
    def evaluate_expression(self, expression: str) -> Dict:
        """评估表达式
        
        Args:
            expression: 要评估的表达式
        """
        return self.send_command("evaluate", {"expression": expression})
    
    def set_breakpoint(self, file_path: str, line: int, condition: str = None) -> Dict:
        """设置断点
        
        Args:
            file_path: 文件路径
            line: 行号
            condition: 条件表达式（可选）
        """
        params = {"filePath": file_path, "line": line}
        if condition:
            params["condition"] = condition
        return self.send_command("setBreakpoint", params)
    
    def remove_breakpoint(self, file_path: str, line: int, include_manual: bool = False) -> Dict:
        """移除断点
        
        Args:
            file_path: 文件路径
            line: 行号
            include_manual: 是否允许移除手动断点
        """
        return self.send_command("removeBreakpoint", {"filePath": file_path, "line": line, "includeManual": include_manual})
    
    def remove_all_breakpoints(self, include_manual: bool = False) -> Dict:
        """移除 AI 设置的断点
        
        Args:
            include_manual: 是否同时移除手动断点
        """
        return self.send_command("removeAllBreakpoints", {"includeManual": include_manual})
    

# ========== SSE 客户端 - 用于接收断点事件推送 ==========

class SSEClient:
    """SSE 客户端，用于接收 VSCode Extension 推送的断点事件"""
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = NOTIFICATION_PORT):
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}/events"
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.session_id: Optional[str] = None
    
    def start(self) -> Dict:
        """启动 SSE 订阅"""
        global sse_connected, sse_thread
        
        if self.running:
            return {"success": True, "message": "SSE 订阅已在运行", "session_id": self.session_id}
        
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        sse_thread = self.thread
        
        # 等待连接建立
        timeout = 5.0
        start_time = time.time()
        while time.time() - start_time < timeout:
            if sse_connected:
                return {"success": True, "message": "SSE 订阅已启动", "session_id": self.session_id}
            time.sleep(0.1)
        
        return {"success": False, "error": "SSE 连接超时，请确保 VSCode Extension 已启动"}
    
    def stop(self) -> Dict:
        """停止 SSE 订阅"""
        global sse_connected
        self.running = False
        sse_connected = False
        return {"success": True, "message": "SSE 订阅已停止"}
    
    def _listen_loop(self):
        """SSE 监听循环"""
        global sse_connected, breakpoint_event_queue
        
        while self.running:
            try:
                req = urllib.request.Request(self.url)
                req.add_header('Accept', 'text/event-stream')
                req.add_header('Cache-Control', 'no-cache')
                
                with urllib.request.urlopen(req, timeout=120) as response:
                    sse_connected = True
                    buffer = ""
                    
                    # 使用逐行读取，更适合 SSE
                    while self.running:
                        try:
                            # 逐字节读取直到遇到换行，避免阻塞
                            line_bytes = b""
                            while True:
                                byte = response.read(1)
                                if not byte:
                                    # 连接关闭
                                    raise ConnectionError("SSE 连接关闭")
                                line_bytes += byte
                                if byte == b'\n':
                                    break
                            
                            line = line_bytes.decode('utf-8').rstrip('\r\n')
                            
                            if line == '':
                                # 空行表示消息结束，处理 buffer
                                if buffer:
                                    self._process_sse_message(buffer)
                                    buffer = ""
                            elif line.startswith(':'):
                                # 注释行（心跳），忽略
                                pass
                            else:
                                # 累积到 buffer
                                buffer += line + '\n'
                                
                        except socket.timeout:
                            # 超时但连接未断，继续
                            continue
                                        
            except urllib.error.URLError as e:
                sse_connected = False
                if self.running:
                    time.sleep(2)  # 重连间隔
            except ConnectionError as e:
                sse_connected = False
                if self.running:
                    time.sleep(1)  # 短暂等待后重连
            except Exception as e:
                sse_connected = False
                if self.running:
                    time.sleep(2)
        
        sse_connected = False
    
    def _process_sse_message(self, message: str):
        """处理 SSE 消息"""
        for line in message.split('\n'):
            if line.startswith('data: '):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    self._handle_event(data)
                except json.JSONDecodeError:
                    pass
    
    def _handle_event(self, data: Dict):
        """处理 SSE 事件"""
        global breakpoint_event_queue
        
        event_type = data.get('type')
        
        if event_type == 'connected':
            self.session_id = data.get('sessionId')
        
        elif event_type == 'breakpointHit':
            # 断点触发事件 - 全部入队，由 wait_next_hit 根据 watchlist 决定是否跳过
            location = data.get('location', {})
            if 'location' in location and isinstance(location.get('location'), dict):
                inner_location = location['location']
            else:
                inner_location = location
            
            breakpoint_event_queue.put({
                'type': 'breakpointHit',
                'timestamp': data.get('timestamp'),
                'hitCount': data.get('hitCount'),
                'location': inner_location
            })
        
        elif event_type == 'resumed':
            # 程序恢复运行
            breakpoint_event_queue.put({
                'type': 'resumed',
                'timestamp': data.get('timestamp')
            })
        
        elif event_type == 'sessionEnded':
            # 调试会话结束
            breakpoint_event_queue.put({
                'type': 'sessionEnded',
                'timestamp': data.get('timestamp'),
                'sessionName': data.get('sessionName')
            })


# 创建MCP服务器
server = Server("vsdbg-mcp")
debug_client = VSCodeDebugClient()
sse_client = SSEClient()


@server.list_tools()
async def list_tools() -> List[Tool]:
    """列出所有可用工具"""
    return [
        Tool(
            name="check_debug_connection",
            description="检查与VSCode调试桥接服务器的连接状态",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="set_breakpoints",
            description="批量设置断点。每项可指定文件路径、行号、可选条件。只负责在 VSCode 中创建断点，不影响 Watchlist",
            inputSchema={
                "type": "object",
                "properties": {
                    "breakpoints": {
                        "type": "array",
                        "description": "断点列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string", "description": "文件绝对路径"},
                                "line": {"type": "integer", "description": "行号（从1开始）"},
                                "condition": {"type": "string", "description": "条件表达式（可选）"}
                            },
                            "required": ["file_path", "line"]
                        }
                    }
                },
                "required": ["breakpoints"]
            }
        ),
        Tool(
            name="remove_breakpoint",
            description="移除指定位置的断点。默认只移除 AI 设置的断点；include_manual=true 时可移除任意断点",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件的绝对路径"
                    },
                    "line": {
                        "type": "integer",
                        "description": "行号（从1开始）"
                    },
                    "include_manual": {
                        "type": "boolean",
                        "description": "为 true 时允许移除手动断点",
                        "default": False
                    }
                },
                "required": ["file_path", "line"]
            }
        ),
        Tool(
            name="remove_all_breakpoints",
            description="移除 AI 设置的断点。include_manual=true 时移除所有断点（含手动）",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_manual": {
                        "type": "boolean",
                        "description": "为 true 时同时移除手动断点",
                        "default": False
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="watchlist_manage",
            description="管理关心断点集（Watchlist）。控制 wait_next_hit 应等待哪些断点、透明跳过哪些。与断点设置解耦",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "set=替换整个列表, add=追加, remove=移除指定, clear=清空, list=查看当前",
                        "enum": ["set", "add", "remove", "clear", "list"]
                    },
                    "breakpoints": {
                        "type": "array",
                        "description": "set/add/remove 时使用，每项含 file_path 和 line",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string", "description": "文件绝对路径"},
                                "line": {"type": "integer", "description": "行号"}
                            },
                            "required": ["file_path", "line"]
                        }
                    }
                },
                "required": ["action"]
            }
        ),
        Tool(
            name="wait_next_hit",
            description="等待下一个关心的断点命中。非 Watchlist 中的断点透明跳过。调试会话结束时也会通知",
            inputSchema={
                "type": "object",
                "properties": {
                    "auto_continue": {
                        "type": "boolean",
                        "description": "进入等待前是否自动 continue（若程序暂停）。设为 false 表示当前已处于暂停状态，直接等待命中即可。默认 true",
                        "default": True
                    },
                    "timeout": {
                        "type": "number",
                        "description": "总超时秒数（含内部循环），默认 60",
                        "default": 60
                    },
                    "auto_context": {
                        "type": "boolean",
                        "description": "命中后是否自动获取完整上下文（位置+变量+调用栈），默认 true",
                        "default": True
                    }
                },
                "required": []
            }
        ),

        Tool(
            name="debug_control",
            description="控制调试流程：continue(继续), stepOver(单步跳过), stepInto(单步进入), stepOut(单步跳出), pause(暂停), restart(重启), stop(停止)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "调试控制动作",
                        "enum": ["continue", "stepOver", "stepInto", "stepOut", "pause", "restart", "stop"]
                    }
                },
                "required": ["action"]
            }
        ),
        Tool(
            name="evaluate_expression",
            description="在当前调试上下文中评估表达式，获取其值。可用于查看变量、调用函数等",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要评估的表达式，如变量名、函数调用、属性访问等"
                    }
                },
                "required": ["expression"]
            }
        ),
        Tool(
            name="get_debug_context",
            description="一次性获取完整的调试上下文，包括当前位置、局部变量、调用栈",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_global_vars": {
                        "type": "boolean",
                        "description": "是否包含全局变量（可能很大），默认 false",
                        "default": False
                    },
                    "max_stack_depth": {
                        "type": "integer",
                        "description": "调用栈最大深度，默认 10",
                        "default": 10
                    }
                },
                "required": []
            }
        )
    ]


def _in_watchlist(file_path: str, line: int) -> bool:
    """检查给定的断点位置是否在 Watchlist 中"""
    with _watchlist_lock:
        if not watchlist:
            return False
        norm_path = file_path.replace('\\', '/').lower()
        for wl_path, lines in watchlist.items():
            wl_norm_path = wl_path.replace('\\', '/').lower()
            if (norm_path == wl_norm_path or norm_path.endswith(wl_norm_path) or wl_norm_path in norm_path):
                if line in lines:
                    return True
        return False


def _get_context(include_global: bool = False, max_stack: int = 10) -> Dict:
    """获取调试上下文（内部使用）"""
    location = debug_client.get_current_location()
    if not location.get("success", False) or not location.get("paused", False):
        return {"error": "程序未暂停"}
    scope = "all" if include_global else "local"
    variables = debug_client.get_variables(scope)
    call_stack = debug_client.get_call_stack()
    if call_stack.get("success") and call_stack.get("callStack"):
        call_stack["callStack"] = call_stack["callStack"][:max_stack]
    return {
        "location": location.get("location"),
        "variables": variables.get("variables", {}),
        "call_stack": call_stack.get("callStack", []),
        "session_name": location.get("sessionName"),
        "session_type": location.get("sessionType")
    }


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """调用工具"""
    
    result = {}
    
    # ========== 连接管理 ==========
    if name == "check_debug_connection":
        connected = debug_client.connect()
        if connected:
            result = {"success": True, "message": "已连接到VSCode调试桥接服务器"}
            debug_client.disconnect()
        else:
            result = {"success": False, "message": "无法连接到调试桥接服务器"}
    
    # ========== 断点管理 ==========
    elif name == "set_breakpoints":
        bps = arguments.get("breakpoints", [])
        if not bps:
            result = {"success": False, "error": "断点列表不能为空"}
        else:
            set_results = {"success": True, "breakpoints_set": [], "breakpoints_failed": []}
            for bp in bps:
                fp = bp.get("file_path", "")
                ln = bp.get("line", 0)
                cond = bp.get("condition")
                if fp and ln:
                    r = debug_client.set_breakpoint(fp, ln, cond)
                    info = {"file_path": fp, "line": ln}
                    if r.get("success"):
                        set_results["breakpoints_set"].append(info)
                    else:
                        info["error"] = r.get("error", "未知错误")
                        set_results["breakpoints_failed"].append(info)
                else:
                    set_results["breakpoints_failed"].append({
                        "file_path": fp or "(空)", "line": ln, "error": "文件路径或行号无效"
                    })
            set_results["summary"] = {
                "total": len(bps),
                "success": len(set_results["breakpoints_set"]),
                "failed": len(set_results["breakpoints_failed"])
            }
            result = set_results
    
    elif name == "remove_breakpoint":
        file_path = arguments.get("file_path", "")
        line = arguments.get("line", 0)
        include_manual = arguments.get("include_manual", False)
        if not file_path or not line:
            result = {"success": False, "error": "文件路径和行号为必填项"}
        else:
            result = debug_client.remove_breakpoint(file_path, line, include_manual)
    
    elif name == "remove_all_breakpoints":
        include_manual = arguments.get("include_manual", False)
        result = debug_client.remove_all_breakpoints(include_manual)
    
    # ========== Watchlist 管理 ==========
    elif name == "watchlist_manage":
        action = arguments.get("action", "list")
        bps = arguments.get("breakpoints", [])
        
        with _watchlist_lock:
            if action == "set":
                watchlist.clear()
                for bp in bps:
                    fp, ln = bp.get("file_path", ""), bp.get("line", 0)
                    if fp and ln:
                        watchlist.setdefault(fp, set()).add(ln)
                result = {"success": True, "action": "set", "count": len(bps)}
            
            elif action == "add":
                added = 0
                for bp in bps:
                    fp, ln = bp.get("file_path", ""), bp.get("line", 0)
                    if fp and ln:
                        if ln not in watchlist.setdefault(fp, set()):
                            watchlist[fp].add(ln)
                            added += 1
                result = {"success": True, "action": "add", "added": added}
            
            elif action == "remove":
                removed = 0
                for bp in bps:
                    fp, ln = bp.get("file_path", ""), bp.get("line", 0)
                    if fp and ln and fp in watchlist and ln in watchlist[fp]:
                        watchlist[fp].discard(ln)
                        if not watchlist[fp]:
                            del watchlist[fp]
                        removed += 1
                result = {"success": True, "action": "remove", "removed": removed}
            
            elif action == "clear":
                watchlist.clear()
                result = {"success": True, "action": "clear"}
            
            elif action == "list":
                result = {
                    "success": True,
                    "action": "list",
                    "watchlist": {
                        fp: sorted(list(lines)) for fp, lines in watchlist.items()
                    }
                }
            else:
                result = {"success": False, "error": f"未知操作: {action}"}
    
    # ========== 等待下一命中（核心） ==========
    elif name == "wait_next_hit":
        timeout = arguments.get("timeout", 60)
        auto_context = arguments.get("auto_context", True)
        auto_continue = arguments.get("auto_continue", True)
        
        if auto_continue:
            debug_client.debug_continue()
        
        with _watchlist_lock:
            if not watchlist:
                result = {"success": False, "error": "Watchlist 为空，请先调用 watchlist_manage 设置关心断点"}
            else:
                result = {}
        
        if result:
            pass  # 已设置错误结果
        elif not sse_connected:
            # 尝试启动 SSE 订阅
            sub_result = sse_client.start()
            if not sub_result.get("success"):
                result = {"success": False, "error": "无法连接到断点事件推送，请确保调试会话已启动"}
        
        if not result:
            deadline = time.time() + timeout
            hit_found = False
            session_ended = False
            
            try:
                while time.time() < deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    
                    try:
                        event = breakpoint_event_queue.get(timeout=min(remaining, 5.0))
                    except queue.Empty:
                        continue
                    
                    etype = event.get('type')
                    
                    if etype == 'sessionEnded':
                        result = {
                            "success": True,
                            "hit": False,
                            "session_ended": True,
                            "session_name": event.get('sessionName', '')
                        }
                        session_ended = True
                        break
                    
                    elif etype == 'breakpointHit':
                        loc = event.get('location', {})
                        fp = loc.get('filePath', '')
                        ln = loc.get('line', 0)
                        
                        if _in_watchlist(fp, ln):
                            # 命中关心的断点
                            ctx = _get_context() if auto_context else {}
                            result = {
                                "success": True,
                                "hit": True,
                                "location": loc,
                                "context": ctx,
                                "session_ended": False
                            }
                            hit_found = True
                            break
                        else:
                            # 不关心的断点，透明跳过
                            debug_client.debug_continue()
                            continue
                    
                    elif etype == 'resumed':
                        # 忽略 resumed 事件，继续等待
                        continue
                
                if not hit_found and not session_ended:
                    result = {
                        "success": True,
                        "hit": False,
                        "session_ended": False,
                        "timeout": True,
                        "message": f"等待 {timeout} 秒后超时，未命中 Watchlist 中的断点"
                    }
            
            except Exception as e:
                result = {"success": False, "error": str(e)}
    
    # ========== 调试控制 ==========
    elif name == "debug_control":
        action = arguments.get("action")
        action_map = {
            "continue": debug_client.debug_continue,
            "stepOver": debug_client.debug_step_over,
            "stepInto": debug_client.debug_step_into,
            "stepOut": debug_client.debug_step_out,
            "pause": debug_client.debug_pause,
            "restart": debug_client.debug_restart,
            "stop": debug_client.debug_stop
        }
        if action in action_map:
            result = action_map[action]()
        else:
            result = {"success": False, "error": f"未知的动作: {action}"}
    
    # ========== 表达式求值 ==========
    elif name == "evaluate_expression":
        expression = arguments.get("expression", "")
        if not expression:
            result = {"success": False, "error": "表达式不能为空"}
        else:
            result = debug_client.evaluate_expression(expression)
    
    # ========== 调试上下文 ==========
    elif name == "get_debug_context":
        include_global = arguments.get("include_global_vars", False)
        max_stack = arguments.get("max_stack_depth", 10)
        ctx = _get_context(include_global, max_stack)
        if "error" in ctx:
            result = {"success": False, "error": ctx["error"]}
        else:
            result = {"success": True, **ctx}
    
    else:
        result = {"success": False, "error": f"未知的工具: {name}"}
    
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    """主入口"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
