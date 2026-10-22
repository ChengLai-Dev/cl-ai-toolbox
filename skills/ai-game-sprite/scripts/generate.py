#!/usr/bin/env python
"""薄封装：调用已部署的 ai-game-pipeline，生成一个角色的序列帧图集。

默认走五步 ControlNet 流程：
    基础立绘(文生图) -> Canny 控制图 -> ControlNet 精修立绘 -> Wan 视频 -> 图集

用法：
    python generate.py --character soldier --action walk --seed 20261021
    python generate.py --character soldier --action attack --engine 5b
    python generate.py --character soldier --action walk --skip-look   # 只重跑动画与图集
    python generate.py --character soldier --action walk --prompt "..." --video-prompt "..."
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

PIPELINE_ROOT = Path(os.environ.get("AI_GAME_PIPELINE_ROOT", r"D:\Code\opencode-workspace\ai-game-pipeline"))
PIPELINE_DIR = PIPELINE_ROOT / "pipeline"
PYTHON = PIPELINE_ROOT / ".venv" / "Scripts" / "python.exe"

# 角色设定段，换角色只改这一处
DEFAULT_CHARACTER = (
    "a young courier with short blond hair wearing a mint green hoodie with the hood down, "
    "a brown leather crossbody satchel across the chest, dark gray shorts, white sneakers, "
    "holding a small white letter envelope in the right hand"
)

# 立绘 prompt 模板：{c} 角色设定段
LOOK_PROMPTS = {
    "walk": (
        "2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right, {c}, "
        "walking mid-stride, the front leg is the RIGHT leg stepping forward to the right, "
        "the back leg is the LEFT leg trailing behind, the front arm is the LEFT arm swinging forward, "
        "the back arm is the RIGHT arm swung behind, upright torso, "
        "clean flat colors, bold black outline, simple cel shading, plain flat light gray background, "
        "full body, entire body visible from head to shoes, single character, no text, no ground shadow, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
    "run": (
        "2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right, {c}, "
        "running mid-stride with legs apart and arms swinging, torso leaning forward, "
        "the front leg is the RIGHT leg stepping forward, the back leg is the LEFT leg trailing behind, "
        "the front arm is the LEFT arm swinging forward, the back arm is the RIGHT arm swung behind, "
        "clean flat colors, bold black outline, simple cel shading, plain flat light gray background, "
        "full body, entire body visible from head to shoes, single character, no text, no ground shadow, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
    "idle": (
        "2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right, {c}, "
        "standing still in a relaxed ready stance, both feet planted shoulder width apart, "
        "the RIGHT arm holds the prop lowered beside the right thigh, the LEFT arm relaxed at the side, "
        "upright posture, clean flat colors, bold black outline, simple cel shading, "
        "plain flat light gray background, full body, entire body visible from head to shoes, "
        "single character, no text, no ground shadow, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
    "attack": (
        "2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right, {c}, "
        "dynamic slash attack pose, the RIGHT arm extended forward to the right swinging the prop "
        "diagonally downward, the LEFT arm pulled back behind the body for balance, "
        "the front leg is the RIGHT leg bent forward, the back leg is the LEFT leg extended behind, "
        "torso twisted to the right, clean flat colors, bold black outline, simple cel shading, "
        "plain flat light gray background, full body, entire body visible from head to shoes, "
        "single character, no text, no ground shadow, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
    "hit": (
        "2D hand-drawn cartoon game character sprite, three-quarter top-down view facing right, {c}, "
        "staggering back from a hit, the torso leaning back a little, the head snapped back, "
        "the LEFT arm flung upward in shock, both feet still on the ground taking one small step back, "
        "shocked expression, clean flat colors, bold black outline, simple cel shading, "
        "plain flat light gray background, full body, entire body visible from head to shoes, "
        "single character, no text, no ground shadow, no hearts, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
}

# 视频 prompt 模板
VIDEO_PROMPTS = {
    "walk": (
        "2D cartoon game character walking in place, three-quarter top-down view facing right, "
        "full body visible, steady walking cycle with the legs alternating forward and backward, "
        "the front leg is the RIGHT leg while the back arm is the RIGHT arm, the LEFT arm swings forward, "
        "arms bent at the elbows, torso upright, clean flat colors, bold black outline, "
        "plain light gray background, smooth continuous walking motion, game sprite animation"
    ),
    "run": (
        "2D cartoon game character running fast in place, three-quarter top-down view facing right, "
        "full body visible, arms swinging forward and backward with bent elbows, "
        "legs in large alternating strides, dynamic running posture, torso leaning forward, "
        "clean flat colors, bold black outline, plain light gray background, "
        "smooth continuous running motion, game sprite animation"
    ),
    "idle": (
        "2D cartoon game character standing idle, three-quarter top-down view facing right, "
        "full body visible, subtle breathing motion, the chest and shoulders rise and fall gently, "
        "slight hair and cloth sway, arms relaxed, feet planted, clean flat colors, bold black outline, "
        "plain light gray background, smooth continuous subtle idle loop, game sprite animation"
    ),
    "attack": (
        "2D cartoon game character performing one slash attack, three-quarter top-down view facing right, "
        "full body visible, the right arm swings the prop in a fast diagonal slash from up high "
        "down to the front, the body lunges forward, the weight shifts onto the front leg, "
        "the left arm swings back, one decisive strike, clean flat colors, bold black outline, "
        "plain light gray background, smooth continuous attack animation, game sprite animation"
    ),
    "hit": (
        "2D cartoon game character knocked back by a hit, three-quarter top-down view facing right, "
        "full body visible, the body rocks backward in shock, the head snaps back, the free arm flies up, "
        "one foot steps back, the body sways forward again to the starting pose and the rocking motion "
        "repeats, a back and forth rocking motion, no floating hearts, no symbols, clean flat colors, "
        "bold black outline, plain light gray background, "
        "smooth continuous looping reaction animation, game sprite animation"
    ),
}


def build_parser():
    parser = argparse.ArgumentParser(
        description="生成 2D 游戏角色序列帧图集（默认走 ControlNet 流程）")
    parser.add_argument("--character", required=True, help="角色名，产物目录名")
    parser.add_argument("--action", default="walk",
                        choices=sorted(LOOK_PROMPTS), help="动作")
    parser.add_argument("--character-desc", default=DEFAULT_CHARACTER,
                        help="角色设定段，会填进提示词模板的 {c}")
    parser.add_argument("--prompt", default=None, help="覆盖立绘提示词")
    parser.add_argument("--video-prompt", default=None, help="覆盖视频提示词")
    parser.add_argument("--engine", choices=["a14b", "5b"], default="a14b")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--steps", type=int, default=8, help="去噪步数，Turbo 蒸馏模型 8 步足够")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--length", type=int, default=49)
    parser.add_argument("--size", type=int, default=768, help="立绘边长，上限 768")
    parser.add_argument("--video-width", type=int, default=480)
    parser.add_argument("--video-height", type=int, default=640)
    parser.add_argument("--control-scale", type=float, default=0.75)
    parser.add_argument("--tolerance", type=int, default=250)
    parser.add_argument("--no-controlnet", action="store_true",
                        help="跳过 ControlNet 精修（不推荐用于动画序列帧）")
    parser.add_argument("--look-src", default=None,
                        help="把现成的图当作 ControlNet 的基础立绘")
    parser.add_argument("--skip-look", action="store_true",
                        help="复用已有立绘，只重跑动画与图集")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将要执行的命令，不实际运行")
    return parser


def main():
    args = build_parser().parse_args()

    if not PYTHON.exists():
        raise SystemExit(f"missing venv python: {PYTHON}")
    if not (PIPELINE_DIR / "run_pipeline.py").exists():
        raise SystemExit(f"missing pipeline: {PIPELINE_DIR}")

    look_prompt = args.prompt or LOOK_PROMPTS[args.action].format(c=args.character_desc)
    video_prompt = args.video_prompt or VIDEO_PROMPTS[args.action]

    cmd = [
        str(PYTHON), "run_pipeline.py",
        "--character", args.character,
        "--action", args.action,
        "--engine", args.engine,
        "--seed", str(args.seed),
        "--steps", str(args.steps),
        "--frames", str(args.frames),
        "--length", str(args.length),
        "--size", str(args.size),
        "--video-width", str(args.video_width),
        "--video-height", str(args.video_height),
        "--control-scale", str(args.control_scale),
        "--tolerance", str(args.tolerance),
        "--prompt", look_prompt,
        "--video-prompt", video_prompt,
    ]
    if args.no_controlnet:
        cmd.append("--no-controlnet")
    if args.look_src:
        cmd += ["--look-src", args.look_src]
    if args.skip_look:
        cmd.append("--skip-look")

    print("$ " + " ".join(cmd))
    if args.dry_run:
        print("\n(dry-run，未执行)")
        return
    result = subprocess.run(cmd, cwd=str(PIPELINE_DIR))
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    out = PIPELINE_ROOT / "game" / "assets" / "sprites" / args.character
    print(f"\nsprite ready: {out}")
    print(f"atlas:    {out / 'atlas.png'}")
    print(f"manifest: {out / 'manifest.json'}")
    print(f"\n预览:  python {Path(__file__).parent / 'preview.py'} \"{out}\" --action {args.action}")


if __name__ == "__main__":
    main()
