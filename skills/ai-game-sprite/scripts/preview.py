#!/usr/bin/env python
"""验收脚本：把序列帧拼成 gif 预览，并计算循环闭合指标。

用法：
    python preview.py "D:\\Code\\opencode-workspace\\ai-game-pipeline\\game\\assets\\sprites\\hero"
    python preview.py <sprite_dir> --action walk --fps 10
    python preview.py <sprite_dir> --src "D:\\Code\\ComfyUI\\ComfyUI-0.36.0\\output\\Wan_frames"

指标：
    wrap/avg  末帧->首帧 的像素差 / 相邻帧平均像素差
              < 1.0 表示接缝比普通帧间过渡还平滑
    iou       循环区间检测得分（需要 --src 指向原始视频帧）
              > 0.70 可用
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PIPELINE_ROOT = Path(os.environ.get("AI_GAME_PIPELINE_ROOT", r"D:\Code\opencode-workspace\ai-game-pipeline"))
PIPELINE_DIR = PIPELINE_ROOT / "pipeline"


def checkerboard(size, cell=8):
    """灰白棋盘底，用来显示透明区域。"""
    w, h = size
    board = Image.new("RGB", size, (230, 230, 230))
    draw = ImageDraw.Draw(board)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2 == 0:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(205, 205, 205))
    return board


def frame_diff(a, b):
    """两帧之间的平均像素差（RGB + alpha 通道）。"""
    arr_a = np.asarray(a, dtype=np.float32)
    arr_b = np.asarray(b, dtype=np.float32)
    return float(np.abs(arr_a - arr_b).mean())


def loop_score(src, min_loop=16, tolerance=250, max_frames=64):
    """在原始视频帧上找最合适的循环区间，返回 (start, end, iou, total)。

    优先读 `_last_run.txt`（只含最后一轮生成的帧），与 import_frames.py --use-last 一致。
    没有该文件时只取目录里最后的 max_frames 帧 —— ComfyUI 的输出目录会累积历史帧，
    全量跑 find_loop 是 O(n^2) 的，帧数上千会算到天荒地老。
    """
    sys.path.insert(0, str(PIPELINE_DIR))
    from import_frames import find_loop

    src = Path(src)
    manifest = src / "_last_run.txt"
    if manifest.exists():
        names = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        files = [src / name for name in names]
    else:
        files = sorted(src.glob("*.png"))[-max_frames:]

    if not files:
        raise SystemExit(f"no frames in {src}")
    frames = [Image.open(f).convert("RGBA") for f in files]
    start, end, score = find_loop(frames, tolerance, min_loop)
    return start, end, score, len(frames)


def main():
    parser = argparse.ArgumentParser(description="序列帧验收：gif 预览 + 循环闭合指标")
    parser.add_argument("sprite_dir", help="game/assets/sprites/<角色> 目录")
    parser.add_argument("--action", default="walk")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--out", default=None, help="gif 输出路径")
    parser.add_argument("--src", default=None,
                        help="原始视频帧目录，额外计算循环区间 iou")
    parser.add_argument("--min-loop", type=int, default=16)
    parser.add_argument("--tolerance", type=int, default=250)
    args = parser.parse_args()

    sprite_dir = Path(args.sprite_dir)
    frames_dir = sprite_dir / "frames" / args.action
    files = sorted(frames_dir.glob("*.png"))
    if not files:
        raise SystemExit(f"no frames in {frames_dir}")

    frames = [Image.open(f).convert("RGBA") for f in files]
    size = frames[0].size

    diffs = [frame_diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    wrap = frame_diff(frames[-1], frames[0])
    avg = sum(diffs) / len(diffs)
    ratio = wrap / avg if avg else 0.0

    board = checkerboard(size)
    rendered = []
    for frame in frames:
        canvas = board.copy()
        canvas.paste(frame, (0, 0), frame)
        rendered.append(canvas)

    out = Path(args.out) if args.out else sprite_dir / f"preview_{args.action}.gif"
    out.parent.mkdir(parents=True, exist_ok=True)
    rendered[0].save(
        out,
        save_all=True,
        append_images=rendered[1:],
        duration=int(1000 / args.fps),
        loop=0,
    )

    print(f"frames  : {len(frames)} @ {size[0]}x{size[1]}  fps={args.fps}")
    print(f"wrap    : {wrap:.2f}")
    print(f"avg     : {avg:.2f}")
    verdict = "seamless" if ratio < 1.0 else "visible seam"
    print(f"wrap/avg: {ratio:.3f}  ({verdict})")

    if args.src:
        start, end, iou, total = loop_score(args.src, args.min_loop, args.tolerance)
        mark = "OK" if iou > 0.70 else "LOW"
        print(f"loop    : [{start}, {end}) of {total}  iou={iou:.3f}  [{mark}]")

    print(f"gif     : {out}")


if __name__ == "__main__":
    main()
