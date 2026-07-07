# -*- coding: utf-8 -*-

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


async def extract_frames(video_path: str, output_dir: str, fps: float = 0,
                         format: str = "png", quality: int = 95,
                         start_time: float = 0, duration: float = 0) -> dict:
    video = Path(video_path)
    if not video.exists():
        return {"success": False, "error": f"视频文件不存在: {video_path}"}

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = video.stem
    cmd = ["ffmpeg", "-y"]

    if start_time > 0:
        cmd.extend(["-ss", str(start_time)])

    cmd.extend(["-i", str(video.absolute())])

    if duration > 0:
        cmd.extend(["-t", str(duration)])

    if fps > 0:
        cmd.extend(["-vf", f"fps={fps}"])

    ext = format.lower().replace("jpeg", "jpg")
    if ext not in ("png", "jpg"):
        ext = "png"

    output_pattern = str(out_dir / f"{stem}_%06d.{ext}")
    cmd.append(output_pattern)

    if ext == "jpg":
        qscale = max(2, min(31, int(32 - quality / 100 * 30)))
        cmd.extend(["-q:v", str(qscale)])
    elif ext == "png":
        cmd.extend(["-compression_level", str(max(0, min(9, 9 - quality // 11)))])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"FFmpeg 失败: {stderr.decode('utf-8', errors='replace')[:500]}"
            }

        files = sorted(out_dir.glob(f"{stem}_*.{ext}"))
        return {
            "success": True,
            "output_dir": str(out_dir.absolute()),
            "frame_count": len(files),
            "format": ext,
            "files": [f.name for f in files[:20]],
            "total_files": len(files)
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "未找到 FFmpeg，请确保已安装并添加到系统 PATH"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_video_info(video_path: str) -> dict:
    video = Path(video_path)
    if not video.exists():
        return {"success": False, "error": f"视频文件不存在: {video_path}"}

    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video.absolute())
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return {"success": False, "error": f"FFprobe 失败: {stderr.decode()[:300]}"}

        info = json.loads(stdout.decode())

        result = {"success": True}
        if "format" in info:
            fmt = info["format"]
            result["duration"] = float(fmt.get("duration", 0))
            result["size"] = int(fmt.get("size", 0))
            result["bit_rate"] = int(fmt.get("bit_rate", 0))
            result["format_name"] = fmt.get("format_name", "")

        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                result["width"] = int(stream.get("width", 0))
                result["height"] = int(stream.get("height", 0))
                fps_str = stream.get("r_frame_rate", "0/1")
                result["fps"] = eval(fps_str) if "/" in fps_str else 0
                result["codec"] = stream.get("codec_name", "")
                result["frame_count"] = int(stream.get("nb_frames", 0))
                break

        return result

    except FileNotFoundError:
        return {"success": False, "error": "未找到 FFprobe，请确保已安装 FFmpeg"}
    except Exception as e:
        return {"success": False, "error": str(e)}


server = Server("video-to-frames")


@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="extract_frames",
            description="从视频中提取序列帧（PNG/JPG），保存到本地目录",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"},
                    "output_dir": {"type": "string", "description": "输出目录路径"},
                    "fps": {"type": "number", "description": "提取帧率，0=所有原始帧", "default": 0},
                    "format": {"type": "string", "description": "输出格式: png 或 jpg", "default": "png", "enum": ["png", "jpg"]},
                    "quality": {"type": "number", "description": "图片质量 1-100", "default": 95},
                    "start_time": {"type": "number", "description": "开始时间（秒）", "default": 0},
                    "duration": {"type": "number", "description": "提取时长（秒），0=到结束", "default": 0}
                },
                "required": ["video_path", "output_dir"]
            }
        ),
        Tool(
            name="get_video_info",
            description="获取视频文件的元信息（时长、分辨率、帧率、编码等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"}
                },
                "required": ["video_path"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    result = {}

    if name == "extract_frames":
        result = await extract_frames(
            video_path=arguments["video_path"],
            output_dir=arguments["output_dir"],
            fps=arguments.get("fps", 0),
            format=arguments.get("format", "png"),
            quality=arguments.get("quality", 95),
            start_time=arguments.get("start_time", 0),
            duration=arguments.get("duration", 0)
        )
    elif name == "get_video_info":
        result = await get_video_info(video_path=arguments["video_path"])
    else:
        result = {"success": False, "error": f"未知工具: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
