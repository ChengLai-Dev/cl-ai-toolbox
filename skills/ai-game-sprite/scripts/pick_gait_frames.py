#!/usr/bin/env python
"""从 Wan 视频帧里按「步态周期」挑帧，并做逐帧尺寸归一。

为什么需要这一步（2026-10 实测）：
  1. `import_frames.py --auto-loop` 找的是「最相似的一对帧」，会落在动作最平缓的区间，
     拍出来的 4 帧几乎同姿态（实测：一个 48×56 的小怪，4 帧差异 <3%）。
  2. Wan 生成的视频里角色会缓慢 zoom / 平移，按「联合包围盒」缩放后仍然体型忽大忽小。

本脚本做三件事：
  1. 用掩膜自相关找步态周期 T（同一姿势隔多少帧重现）；
  2. 从 T 起等距取 N 帧（t0, t0+T/N, …），循环区间就是真正的步态周期；
  3. 逐帧按「身体高度」归一（bbox 高度缩到同一值、脚底贴画布底），压掉 zoom 漂移；
     缩放系数限幅 ±8%，避免武器/披风把 bbox 撑大引起抖动。

输出未定尺寸的中间帧（源分辨率），再交给 fit_and_validate.py 落到引擎画布。

用法：
    python pick_gait_frames.py --src <Wan输出目录> --out <中间帧目录> --frames 4
    python pick_gait_frames.py --src ... --out ... --frames 6 --report pick.json

退出码：0 = 挑到；2 = 没找到周期（通常是动作幅度太小，回去改立绘/视频 prompt）。
"""

import argparse
import json
import os
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

PIPELINE_ROOT = Path(os.environ.get("AI_GAME_PIPELINE_ROOT",
                                    r"D:\Code\opencode-workspace\ai-game-pipeline"))


def _pipeline_remove_background():
    """优先复用管线的抠图（色差 + 低饱和 + 边界洪水），口径一致才不会出现「这批干净那批脏」。"""
    try:
        sys.path.insert(0, str(PIPELINE_ROOT / "pipeline"))
        from gen_frames import remove_background  # noqa: F401
        return remove_background
    except Exception:
        return None


def _fallback_remove_background(image, tolerance=250, saturation=24):
    """管线不可用时的等价实现（判据与 gen_frames.remove_background 相同）。"""
    img = image.convert("RGBA")
    rgb = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w = rgb.shape[:2]
    corners = [img.getpixel(p)[:3] for p in [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]]
    bg = np.array([sum(c[i] for c in corners) // len(corners) for i in range(3)], np.int16)
    dist = np.abs(rgb - bg).sum(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    candidate = (dist <= tolerance) & (sat <= saturation)
    seen = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if candidate[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if candidate[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    out = np.asarray(img).copy()
    out[:, :, 3] = np.where(seen, 0, out[:, :, 3])
    return Image.fromarray(out, "RGBA")


REMOVE_BG = _pipeline_remove_background() or _fallback_remove_background


def cut_frame(path, tol=250):
    img = Image.open(path).convert("RGBA")
    return np.asarray(REMOVE_BG(img, tolerance=tol)).astype(np.float32)


def mask_bbox(a, thresh=128):
    m = a[..., 3] > thresh
    if not m.any():
        return None
    ys, xs = np.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def iou(m1, m2):
    inter = np.logical_and(m1, m2).sum()
    union = np.logical_or(m1, m2).sum()
    return float(inter) / float(union) if union else 0.0


def resize_rgba(arr, size):
    alpha = arr[..., 3] / 255.0
    rgb = arr[..., :3] * alpha[..., None]
    rgb_img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").resize(size, Image.LANCZOS)
    a_img = Image.fromarray((alpha * 255).astype(np.uint8), "L").resize(size, Image.LANCZOS)
    a = np.asarray(a_img).astype(np.float32) / 255.0
    out_rgb = np.asarray(rgb_img).astype(np.float32) / np.maximum(a[..., None], 1e-6)
    return np.concatenate([np.clip(out_rgb, 0, 255), a[..., None] * 255.0], -1)


def find_period(masks, t_min, t_max):
    n = len(masks)
    best, scores = (None, -1.0), {}
    for T in range(t_min, min(t_max, n - 2) + 1):
        vals = [iou(masks[i], masks[i + T]) for i in range(0, n - T, 2)]
        s = float(np.mean(vals)) if vals else 0.0
        scores[T] = s
        if s > best[1]:
            best = (T, s)
    return best[0], best[1], scores


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True, help="Wan 输出帧目录（读 _last_run.txt，没有就读全部 png）")
    p.add_argument("--out", required=True, help="中间帧输出目录")
    p.add_argument("--frames", type=int, default=4, help="要挑几帧（4 走路 / 6 boss）")
    p.add_argument("--min-t", type=int, default=10, help="周期搜索下限（16fps 下 10 帧≈0.6s）")
    p.add_argument("--max-t", type=int, default=28)
    p.add_argument("--tol", type=int, default=250, help="背景容差 sum|Δ|，与 import_frames 同口径")
    p.add_argument("--clamp", type=float, default=0.08, help="逐帧缩放限幅（默认 0.08 = ±8 个百分点）")
    p.add_argument("--report", default=None, help="选帧报告 json")
    args = p.parse_args()

    src = Path(args.src)
    manifest = src / "_last_run.txt"
    names = ([l.strip() for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
             if manifest.exists() else [f.name for f in sorted(src.glob("*.png"))])
    if not names:
        raise SystemExit(f"no frames in {src}")

    frames = [cut_frame(src / n, args.tol) for n in names]
    masks = [f[..., 3] > 128 for f in frames]
    boxes = [mask_bbox(f) for f in frames]
    if any(b is None for b in boxes):
        raise SystemExit("some frames are empty after background removal")

    T, tscore, scores = find_period(masks, args.min_t, args.max_t)
    if T is None:
        print("no period found: motion too small. 立绘/视频 prompt 改成宽步幅再来", file=sys.stderr)
        return 2

    n = args.frames
    step = T / n
    best_t0, best_wrap = 0, -1.0
    for t0 in range(0, len(frames) - T + 1):
        idx = [t0 + int(round(k * step)) for k in range(n)]
        wrap = iou(masks[idx[-1]], masks[idx[0]])
        if wrap > best_wrap:
            best_wrap, best_t0 = wrap, t0
    idx = [min(best_t0 + int(round(k * step)), len(frames) - 1) for k in range(n)]

    heights = [boxes[i][3] - boxes[i][1] for i in idx]
    h_ref = float(np.median(heights))
    # 用中位缩放做基准，单帧偏差再限幅（武器/披风偶尔把 bbox 撑大，不限幅会一抽一抽）
    med = float(np.median([h_ref / h for h in heights]))
    scales = [min(max(h_ref / h, med * (1 - args.clamp)), med * (1 + args.clamp)) for h in heights]

    H, W = frames[0].shape[:2]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()

    for k, (i, s) in enumerate(zip(idx, scales)):
        f = resize_rgba(frames[i], (max(1, int(W * s)), max(1, int(H * s))))
        box = mask_bbox(f)
        cx = (box[0] + box[2]) / 2.0
        canvas = np.zeros_like(frames[0])
        x = int(round(W / 2 - cx))
        y = int(round((H - 1) - box[3]))
        sx0, sy0 = max(0, x), max(0, y)
        dx0, dy0 = max(0, -x), max(0, -y)
        w = min(f.shape[1] - dx0, W - sx0)
        h = min(f.shape[0] - dy0, H - sy0)
        canvas[sy0:sy0 + h, sx0:sx0 + w] = f[dy0:dy0 + h, dx0:dx0 + w]
        Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGBA").save(
            out_dir / f"{k:02d}.png")

    trans = [iou(masks[idx[k]], masks[idx[(k + 1) % n]]) for k in range(n)]
    avg = sum(trans) / len(trans) if trans else 0.0
    report = {
        "src": str(src),
        "frames_available": len(frames),
        "period_T": T,
        "period_score": round(tscore, 4),
        "picked_index": idx,
        "picked_names": [names[i] for i in idx],
        "body_height_ref": h_ref,
        "scales": [round(s, 4) for s in scales],
        "iou_transitions": [round(x, 4) for x in trans],
        "iou_wrap": round(trans[-1], 4),
        "wrap_vs_avg": round(trans[-1] / avg, 3) if avg else None,
        "period_scores": {str(k): round(v, 4) for k, v in sorted(scores.items())},
    }
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"period={T} picked={idx} wrap_vs_avg={report['wrap_vs_avg']} -> {out_dir}")
    if report["wrap_vs_avg"] is not None and report["wrap_vs_avg"] < 0.9:
        print("WARN 接缝比普通帧间过渡更差（wrap_vs_avg < 0.9），循环会顿一下："
              "换 --min-t/--max-t 或换 4→6 帧重挑", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
