#!/usr/bin/env python3
"""
UE 5.8 官方 MCP 服务器的 stdio 桥接。

存在的理由
----------
UE 5.8 自带官方 MCP 服务器（实验性引擎插件
Engine/Plugins/Experimental/ModelContextProtocol），它暴露的是
Streamable HTTP 端点 http://127.0.0.1:8000/mcp，而不是 stdio 进程。
只支持 stdio 的 MCP 客户端无法直连，本脚本完成转换：
从 stdin 读按行分隔的 JSON-RPC，转发给编辑器，再把应答写回 stdout。

协议事实（逐条对照插件源码 ModelContextProtocolServer.cpp 核验）
------------------------------------------------------------------
* 只有 POST /mcp 会干活。GET /mcp 固定返回 405，源码注释原文：
  "We do not currently support sse on a separate endpoint"，
  因此本脚本不建立 SSE 长连接。
* 服务器不校验 Accept 头；且没有 Origin 头时直接放行，源码注释原文：
  "No Origin header — non-browser client, allow"。
* initialize 会创建会话，并在响应头 Mcp-Session-Id 里返回会话 id；
  之后每个请求都必须原样带回，缺失返回 400，失效返回 404
  （404 按规范表示客户端应重新 initialize）。
* 通知类消息（无 "id" 字段）返回 202 且响应体为空，
  此时绝不可向 stdout 写任何东西。
* tools/call 若带 progressToken，响应可能是 text/event-stream 分帧，
  所以两种 content-type 都要处理。

配置（环境变量）
----------------
    UE_MCP_URL      默认 http://127.0.0.1:8000/mcp
    UE_MCP_TIMEOUT  单次请求超时秒数，默认 600
                     （建模/批量改资产这类调用可能很慢）

关于异常处理
------------
本脚本处在两个不可靠边界之间（客户端 stdin、编辑器 HTTP 服务）。
按项目规范 C++/Python 均不使用 try-catch 做控制流；这里仅在两处
外部边界收敛异常，且不吞掉错误——全部转成 JSON-RPC error 或明确的
stderr 提示，不改变控制流语义。
"""

import json
import os
import sys

import httpx


DEFAULT_SERVER_URL = "http://127.0.0.1:8000/mcp"

# 分区超时：连接超时要短（编辑器没开就快速失败），读取超时要长
# （建模、批量改资产等工具调用可能运行很久）。
REQUEST_TIMEOUT = httpx.Timeout(
    connect=2.0,
    read=float(os.environ.get("UE_MCP_TIMEOUT", "600")),
    write=30.0,
    pool=5.0,
)

JSONRPC_VERSION = "2.0"
JSONRPC_INTERNAL_ERROR = -32603

STARTUP_HINT = (
    "无法连接 UE 编辑器 MCP 服务器。请依次确认：\n"
    "  1. 编辑器已启动（项目：Warden）\n"
    "  2. Warden.uproject 中已启用 ModelContextProtocol 插件\n"
    "  3. Config/DefaultEditorPerProjectUserSettings.ini 里 bAutoStartServer=True\n"
    "  4. 编辑器 Output Log 里搜 'Starting MCP server on port' 确认已监听\n"
    "  5. 端口未被占用（一次只能开一个编辑器实例）"
)


def write_stderr(message):
    """诊断信息一律走 stderr —— stdout 只允许出现 JSON-RPC 消息。"""
    print(f"[ue-mcp-bridge] {message}", file=sys.stderr, flush=True)


def to_single_line(payload):
    """把一条消息压成单行。

    stdio 传输的帧约定是「一行一条 JSON-RPC 消息」。而实测上游 UE 插件的应答
    是 application/json + 缩进美化过的响应体（content-type 不是 text/event-stream），
    一个响应里含大量换行；若原样写回，客户端会把换行当成消息分隔，收到一堆
    解析不了的碎片，导致整个 server 注册不上。这里统一兜底。

    JSON 规范要求字符串内部的换行必须转义为 \\n，因此合法 JSON 里的裸换行
    只可能来自格式缩进，删除它既安全又不改变语义。
    """
    if "\n" not in payload and "\r" not in payload:
        return payload

    return payload.replace("\r", "").replace("\n", "")


def write_message(payload):
    """向客户端输出一条 JSON-RPC 消息，压成单行并要求立即送达。"""
    sys.stdout.write(to_single_line(payload) + "\n")
    sys.stdout.flush()


def parse_message(raw_message):
    """尽力把一行文本解析成 JSON-RPC 消息对象；解析不了返回 None。

    客户端 stdin 是不可靠边界，可能送来非 JSON 内容；取不到就按"无从处理"
    对待，由调用方决定不回复。异常收敛点与原来保持一致（仍是外部边界两处）。
    """
    try:
        parsed = json.loads(raw_message)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed


def extract_request_id(raw_message):
    """尽力取出 JSON-RPC 的 id，仅用于在出错时构造应答。

    取不到（不是合法 JSON，或通知类消息本就没有 id）时返回 None，
    调用方据此决定"不回复"。
    """
    parsed = parse_message(raw_message)

    if parsed is None:
        return None

    return parsed.get("id")


def extract_sse_payloads(body_text):
    """从 text/event-stream 响应里抽出所有 data: 分帧的内容。

    该插件用 "event: message\\r\\ndata: <json>\\r\\n\\r\\n" 组帧，
    见源码 FormatSSEMessage()。这里只关心 data 行，且可能有多帧。
    """
    payloads = []

    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue

        payload = line[len("data:"):].strip()
        if payload:
            payloads.append(payload)

    return payloads


def build_error_response(request_id, code, message):
    """构造 JSON-RPC error 应答。"""
    return json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        },
        ensure_ascii=False,
    )


# 上游暴露的元工具清单，取其 tools/list 应答的原文（已实测核对）。
# 引擎这一层的工具面是固定的这三个，所以可以本地应答，不必依赖编辑器。
META_TOOLS = [
    {
        "name": "list_toolsets",
        "description": "List all available toolsets with names and descriptions.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_toolset",
        "description": "Get detailed information about a toolset including all tool names, descriptions, and input schemas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "toolset_name": {
                    "type": "string",
                    "description": "Name of the toolset to describe. Use list_toolsets to see available names.",
                }
            },
            "required": ["toolset_name"],
        },
    },
    {
        "name": "call_tool",
        "description": "Call a tool by name. Provide toolset_name to call a toolset tool, or omit it to call a top-level MCP tool. Use list_toolsets and describe_toolset to discover available tools and their input schemas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "toolset_name": {
                    "type": "string",
                    "description": "Optional. Name of the toolset containing the tool. Omit to call a top-level MCP tool. Use list_toolsets to discover toolset names.",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to call, without toolset prefix. Use describe_toolset to discover tool names and their input schemas.",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the tool. Must match the tool's input schema. Defaults to an empty object.",
                },
            },
            "required": ["tool_name"],
        },
    },
]


def build_local_response(message):
    """就地应答不依赖编辑器的握手类消息；不该本地应答时返回 None。

    为什么必须本地应答：编辑器启动远慢于 IDE。实测两者同时启动时，IDE 拉起
    MCP 服务的那一刻编辑器才起了 1 秒、端口尚未监听；握手一旦转发就会失败，
    而 MCP 客户端会把整个 server 判为不可用并且不再重试 —— 表现为「工具明明
    存在却永远 not found」。这三个元工具的清单由引擎固定提供（META_TOOLS），
    本地应答既准确又不依赖编辑器；真正需要编辑器的只有 tools/call。
    """
    method = message.get("method")

    if method == "initialize":
        params = message.get("params")
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None

        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": message.get("id"),
            "result": {
                "protocolVersion": requested_version or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {
                    "name": "ue-mcp-bridge",
                    "title": "Unreal MCP Bridge",
                    "version": "1.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": message.get("id"),
            "result": {"tools": META_TOOLS},
        }

    if method == "ping":
        return {"jsonrpc": JSONRPC_VERSION, "id": message.get("id"), "result": {}}

    return None


# 自己建会话时使用的协议版本与请求 id。响应由桥接内部消费，不转发给客户端，
# 因此 id 取负值以免与客户端可能使用的正数 id 混淆。
PROTOCOL_VERSION = "2025-06-18"
SESSION_INIT_REQUEST_ID = -1


def establish_session(client, server_url):
    """主动向上游建立一个会话并返回其会话 id。

    为什么必须能自己建会话：编辑器重启后旧会话 id 会失效（上游按 404 作废），
    而 MCP 客户端在整个 IDE 生命周期里只 initialize 一次，之后不会重来。
    桥接若只会"从响应头里捡"会话 id，就会永久卡在无会话状态，后续每个调用
    都收到 400（缺 Mcp-Session-Id）。实测上游允许多个会话并存，所以这里主动
    建一个不会挤掉客户端那条。

    建不上（编辑器没开等）返回 None；带着 None 继续转发会由上游返回 400，
    错误对客户端依然可见，与原来的行为一致。
    """
    body = json.dumps(
        {
            "jsonrpc": JSONRPC_VERSION,
            "id": SESSION_INIT_REQUEST_ID,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ue-mcp-bridge", "version": "1.0"},
            },
        },
        ensure_ascii=False,
    )

    try:
        response = client.post(
            server_url,
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    except httpx.HTTPError as error:
        write_stderr(f"主动建立会话失败：{type(error).__name__}: {error}")
        return None

    returned_session_id = response.headers.get("mcp-session-id")
    if returned_session_id:
        write_stderr(f"已主动建立会话：{returned_session_id}")
    else:
        write_stderr(f"主动建立会话失败：上游未返回 Mcp-Session-Id（HTTP {response.status_code}）")

    return returned_session_id


def handle_http_result(response):
    """把 HTTP 应答转换成要写回 stdout 的行（可能多行，也可能零行）。"""
    # 202 = 已接受的通知，按协议不得回复任何内容。
    if response.status_code == httpx.codes.ACCEPTED:
        return []

    content_type = response.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        payloads = extract_sse_payloads(response.text)
        if payloads:
            return payloads
        # SSE 头但无 data 帧：退回按整体处理，避免静默丢弃应答。

    text = response.text.strip()
    if not text:
        return []

    return [text]


def main():
    server_url = os.environ.get("UE_MCP_URL", DEFAULT_SERVER_URL)
    session_id = None
    announced_failure = False

    # MCP 规范要求 stdio 通信用 UTF-8，而 Windows 下 Python 默认按 locale
    # （简体中文环境为 GBK）解码，必须显式指定，否则中文工具描述会乱码。
    # stderr 一并设为 UTF-8：它只承载诊断日志，而读取它的 MCP 客户端按
    # UTF-8 解析；errors="replace" 保证极端情况下日志编码也不会中断进程。
    sys.stdin.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    client = httpx.Client(timeout=REQUEST_TIMEOUT)

    write_stderr(f"已启动，上游 {server_url}")

    # 用 readline 迭代而不是 for-in-stdin：stdin 作为管道时后者会块缓冲，
    # 导致消息不能及时送达。
    for raw_line in iter(sys.stdin.readline, ""):
        raw_message = raw_line.strip()
        if not raw_message:
            continue

        # 握手类消息就地应答，不依赖编辑器（理由见 build_local_response）。
        message = parse_message(raw_message)
        if message is not None:
            local_response = build_local_response(message)
            if local_response is not None:
                write_message(json.dumps(local_response, ensure_ascii=False))
                continue

        # 会话可能尚未建立（桥接启动时编辑器还没开），也可能刚被上游按 404 作废
        # （编辑器重启即作废旧会话）。MCP 客户端整个生命周期只 initialize 一次，
        # 不会因为 404 重新来一遍，所以这里自己补建，否则后续调用全是 400。
        if session_id is None:
            session_id = establish_session(client, server_url)

        headers = {"Content-Type": "application/json"}
        if session_id is not None:
            headers["Mcp-Session-Id"] = session_id

        request_id = extract_request_id(raw_message)

        try:
            response = client.post(
                server_url,
                content=raw_message.encode("utf-8"),
                headers=headers,
            )
        except httpx.HTTPError as error:
            # 边界收敛：连不上/超时都要转成客户端能理解的错误，
            # 否则客户端只会看到 MCP 服务器无声挂掉。
            detail = f"{type(error).__name__}: {error}"

            if not announced_failure:
                write_stderr(STARTUP_HINT)
                announced_failure = True

            write_stderr(f"请求失败（{detail}）")
            session_id = None

            if request_id is None:
                # 通知类消息没有 id，无从回复，只能记日志。
                continue

            write_message(
                build_error_response(
                    request_id,
                    JSONRPC_INTERNAL_ERROR,
                    f"UE 编辑器 MCP 服务器不可达（{detail}）",
                )
            )
            continue

        announced_failure = False

        # initialize 与后续请求都会带回会话 id；缓存下来供下次请求使用。
        returned_session_id = response.headers.get("mcp-session-id")
        if returned_session_id:
            if session_id != returned_session_id:
                write_stderr(f"会话 id：{returned_session_id}")
            session_id = returned_session_id

        # 404 表示会话已失效，按规范清空以便下次 initialize 重建。
        if response.status_code == httpx.codes.NOT_FOUND:
            write_stderr("会话已失效（404），已清空会话 id，等待客户端重新 initialize")
            session_id = None

        for payload in handle_http_result(response):
            write_message(payload)

    write_stderr("stdin 已关闭，退出")
    client.close()


if __name__ == "__main__":
    main()
