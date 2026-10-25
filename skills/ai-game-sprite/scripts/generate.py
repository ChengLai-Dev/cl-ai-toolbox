#!/usr/bin/env python
"""统一入口：静态美术资源 / 静态图生序列帧 / 文生序列帧。

三种模式共用同一个 Z-Image 引擎，路由规则见 SKILL.md 的「模式路由」一节：

    --mode static              只出一张静态美术资源
    --mode frames-from-image   给一张静态图，从它生成序列帧
    --mode frames              给文字描述，从零生成序列帧

用法：
    python generate.py --mode static --character crate --kind prop --seed 20261021
    python generate.py --mode frames-from-image --character hero --src D:\\art\\hero.png --action walk
    python generate.py --mode frames --character hero --action walk --seed 20261021
"""

import argparse
import json
import os
import shutil
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

# 静态资源没给 --subject 时的兜底主体
DEFAULT_SUBJECTS = {
    "prop": "a small wooden crate with iron bands",
    "icon": "a small blue potion flask with a cork stopper",
    "background": "a sunlit medieval village street with stone walls and market stalls",
    "portrait": "a female blacksmith in a leather apron holding a hammer",
    "tile": "cracked gray cobblestone pavement",
}

# 静态资源提示词模板：{c} 换成主体描述
STATIC_PROMPTS = {
    "prop": (
        "2D hand-drawn game item sprite, {c}, three-quarter top-down view facing right, "
        "clean flat colors, bold black outline, simple cel shading, plain flat light gray background, "
        "single object, centered, entire object visible, no text, no ground shadow, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
    "icon": (
        "2D game UI icon, {c}, flat vector style, bold dark outline, limited saturated palette, "
        "centered, plain flat white background, single icon, no text, no border, "
        "wide empty margins on every side of the frame"
    ),
    "background": (
        "2D hand-drawn game background, {c}, wide establishing shot, clean flat colors, "
        "simple cel shading, even lighting, no characters, no creatures, no text, "
        "empty open foreground space in the center"
    ),
    "portrait": (
        "full body 2D hand-drawn character portrait, {c}, three-quarter top-down view facing right, "
        "clean flat colors, bold black outline, simple cel shading, plain flat light gray background, "
        "full body, entire body visible from head to shoes, single character, no text, no ground shadow, "
        "wide empty gray margins on the left and right sides of the frame"
    ),
    "tile": (
        "seamless tileable 2D game ground texture, {c}, top-down view, clean flat colors, "
        "even lighting, uniform detail, no shadows, no objects, no borders, "
        "repeating pattern across the whole frame"
    ),
}

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
        "2D cartoon game character standing idle, three-quarter top-down view facing right, full body visible, "
        "subtle breathing motion, the chest and shoulders rise and fall gently, "
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
        "bold black outline, plain light gray background, smooth continuous looping reaction animation, "
        "game sprite animation"
    ),
}


def run_pipeline(args_list, dry_run=False):
    cmd = [str(PYTHON)] + args_list
    print("$ " + " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=str(PIPELINE_DIR))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def staged_name(args):
    """落盘用的名字。

    流水线里所有路径都由角色名派生，加工程前缀后两个工程的同名角色
    就不会共用到同一份立绘、控制图和逐帧目录。
    """
    if args.project:
        return f"{args.project}__{args.character}"
    return args.character


def deliver_static(dest, kind, final, meta, character, project, dry_run=False):
    """把静态资源交付到目标工程：dest 是目标工程的 assets 目录。

    目标工程里用不带工程前缀的资源名，只有流水线内部用 `<project>__<name>`。
    """
    target = Path(dest) / "art" / kind
    print(f"\ndeliver: {target}")
    if dry_run:
        return target
    target.mkdir(parents=True, exist_ok=True)
    meta = dict(meta, name=character, project=project)
    (target / f"{character}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.copyfile(final, target / f"{character}.png")
    print(f"  copied {character}.png")
    print(f"  copied {character}.json")
    return target


def generation_size(target, size):
    """按目标比例缩到 max 边 <= size，并对齐 16 的倍数（VAE 下采样倍数）。"""
    scale = size / max(target)
    width = max(64, int(target[0] * scale) // 16 * 16)
    height = max(64, int(target[1] * scale) // 16 * 16)
    return width, height


def should_upscale(target, gen_size, mode):
    """要不要走 ESRGAN。

    目标比生成的大 -> 必须放大；目标比生成的小很多 -> 先放大再缩下来，
    等于超采样，比直接缩更干净（图标 768 -> 128 就是这种情况）。
    """
    if mode == "never":
        return False
    if mode == "always":
        return True
    target_area = target[0] * target[1]
    gen_area = gen_size[0] * gen_size[1]
    return target_area > gen_area or gen_area >= 2 * target_area


def run_static(args):
    sys.path.insert(0, str(PIPELINE_DIR))
    from config import ART_KINDS

    kind = args.kind
    width, height, cutout, seamless = ART_KINDS[kind]
    target = (width, height)
    gen_width, gen_height = generation_size(target, args.size)

    prompt = args.prompt or STATIC_PROMPTS[kind].format(c=args.subject or DEFAULT_SUBJECTS[kind])
    name = staged_name(args)
    art_dir = PIPELINE_ROOT / "assets" / "art" / kind
    out_dir = PIPELINE_ROOT / "game" / "assets" / "art" / kind
    source = art_dir / f"{name}.png"
    final = out_dir / f"{name}.png"
    if not args.dry_run:
        art_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Z-Image 与 ComfyUI 不能同时驻留，出图前先把 ComfyUI 停掉腾内存
    run_pipeline(["comfy_ctl.py", "stop"], args.dry_run)

    run_pipeline([
        "gen_look.py", "--character", name,
        "--width", str(gen_width), "--height", str(gen_height),
        "--steps", str(args.steps), "--seed", str(args.seed),
        "--prompt", prompt, "--out", str(source),
    ], args.dry_run)

    post = ["post_process.py", "--src", str(source), "--out", str(final),
            "--target", f"{width}x{height}"]
    if should_upscale(target, (gen_width, gen_height), args.upscale):
        post.append("--upscale")
    if cutout:
        post.append("--cutout")
    if seamless:
        post.append("--seamless")
    run_pipeline(post, args.dry_run)

    meta = {
        "kind": kind,
        "name": args.character,
        "project": args.project,
        "size": [width, height],
        "generation_size": [gen_width, gen_height],
        "seed": args.seed,
        "steps": args.steps,
        "prompt": prompt,
        "cutout": cutout,
        "seamless": seamless,
    }
    meta_file = out_dir / f"{name}.json"
    if not args.dry_run:
        meta_file.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nstatic art ready: {final}")
    print(f"meta:            {meta_file}")

    if args.dest:
        deliver_static(args.dest, kind, final, meta, args.character, args.project, args.dry_run)


def deliver_sprite(dest, out_dir, character, project, dry_run=False):
    """把图集交付到目标工程：dest 是目标工程的 assets 目录。

    manifest 里的 character 改回不带工程前缀的资源名，避免工程侧看到
    `projA__hero` 这种内部命名；同目录的 frames 是重打包用的源帧，不交付。
    """
    target = Path(dest) / "sprites" / character
    print(f"\ndeliver: {target}")
    if dry_run:
        return target
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["character"] = character
    manifest["project"] = project
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.copyfile(out_dir / "atlas.png", target / "atlas.png")
    print("  copied atlas.png")
    print("  copied manifest.json")
    return target


def run_frames(args):
    name = staged_name(args)
    cmd = [
        "run_pipeline.py",
        "--character", name,
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
        "--prompt", args.prompt or LOOK_PROMPTS[args.action].format(c=args.character_desc),
        "--video-prompt", args.video_prompt or VIDEO_PROMPTS[args.action],
    ]
    if args.mode == "frames-from-image":
        cmd += ["--from-image", args.src]
        if args.no_look_refine:
            cmd.append("--no-look-refine")
        cmd += ["--cutout", args.cutout]
    else:
        if args.no_controlnet:
            cmd.append("--no-controlnet")
        if args.look_src:
            cmd += ["--look-src", args.look_src]
        if args.skip_look:
            cmd.append("--skip-look")

    run_pipeline(cmd, args.dry_run)

    out = PIPELINE_ROOT / "game" / "assets" / "sprites" / name
    print(f"\nsprite ready: {out}")
    print(f"atlas:    {out / 'atlas.png'}")
    print(f"manifest: {out / 'manifest.json'}")
    print(f"\n预览:  python {Path(__file__).parent / 'preview.py'} \"{out}\" --action {args.action}")

    if args.dest:
        deliver_sprite(args.dest, out, args.character, args.project, args.dry_run)


def build_parser():
    sys.path.insert(0, str(PIPELINE_DIR))
    from config import ART_KINDS

    parser = argparse.ArgumentParser(
        description="2D 游戏美术资源生成：静态图 / 静态图生序列帧 / 文生序列帧")
    parser.add_argument("--mode", required=True,
                        choices=["static", "frames-from-image", "frames"],
                        help="static=出静态图；frames-from-image=按静态图出序列帧；frames=按文字出序列帧")
    parser.add_argument("--character", required=True, help="角色名 / 资源名，同时是产物目录名")
    parser.add_argument("--project", default=None,
                        help="工程命名空间；不同工程的同名资源互不覆盖（落盘名 <project>__<character>）")
    parser.add_argument("--dest", default=None,
                        help="目标工程的 assets 目录；验收通过后把成品复制过去")

    # 静态模式
    parser.add_argument("--kind", default="prop", choices=sorted(ART_KINDS),
                        help="静态资源类型")
    parser.add_argument("--subject", default=None,
                        help="静态资源的主体描述，不给则用该类型的默认主体")
    parser.add_argument("--upscale", choices=["auto", "always", "never"], default="auto",
                        help="是否走 ESRGAN 放大")

    # 序列帧模式
    parser.add_argument("--action", default="walk", choices=sorted(LOOK_PROMPTS))
    parser.add_argument("--src", default=None, help="frames-from-image：源静态图路径")
    parser.add_argument("--no-look-refine", action="store_true",
                        help="frames-from-image：源图已是最终画风时跳过 ControlNet 精修")
    parser.add_argument("--character-desc", default=DEFAULT_CHARACTER, help="角色设定段")
    parser.add_argument("--prompt", default=None, help="覆盖提示词")
    parser.add_argument("--video-prompt", default=None, help="覆盖视频提示词")

    parser.add_argument("--engine", choices=["a14b", "5b"], default="a14b")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--steps", type=int, default=8, help="去噪步数，Turbo 蒸馏模型 8 步足够")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--length", type=int, default=49)
    parser.add_argument("--size", type=int, default=768, help="生成边长上限，立绘上限 768")
    parser.add_argument("--video-width", type=int, default=480)
    parser.add_argument("--video-height", type=int, default=640)
    parser.add_argument("--control-scale", type=float, default=0.75)
    parser.add_argument("--tolerance", type=int, default=250)
    parser.add_argument("--cutout", choices=["auto", "flood", "birefnet", "none"], default="auto",
                        help="frames-from-image：源图去背方式")
    parser.add_argument("--no-controlnet", action="store_true",
                        help="frames：跳过 ControlNet 精修（不推荐用于动画序列帧）")
    parser.add_argument("--look-src", default=None, help="frames：把现成的图当基础立绘")
    parser.add_argument("--skip-look", action="store_true",
                        help="frames：复用已有立绘，只重跑动画与图集")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令")
    return parser


def main():
    args = build_parser().parse_args()

    if not PYTHON.exists():
        raise SystemExit(f"missing venv python: {PYTHON}")
    if not (PIPELINE_DIR / "run_pipeline.py").exists():
        raise SystemExit(f"missing pipeline: {PIPELINE_DIR}")

    if args.mode == "static":
        run_static(args)
    else:
        if args.mode == "frames-from-image" and not args.src:
            raise SystemExit("--mode frames-from-image 需要 --src 指定源静态图")
        run_frames(args)


if __name__ == "__main__":
    main()
