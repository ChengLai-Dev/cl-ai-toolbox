#!/usr/bin/env python
"""把管线产物归一到一个确定的画布/锚点，并做可判定的校验 + 写 manifest。

管线的产物不是引擎能直接用的尺寸：
  - 模式① 出的是 768 的静态图；
  - 模式②③ 出的是 192×256 的图集帧（底部锚定、四周 8px padding）。
两者都要按目标工程的「单帧尺寸 / 锚点 / 命名」重新归一一次，否则会出现
「图集里看着没问题，进引擎后角色大小不一、脚底悬空 / 埋进地面」。

同时把每一条验收句算成数字（画布、边距、锚点、循环 IoU、末帧是否为空、
左右镜像差、明度差），写进 sidecar 与目录级 manifest.json —— 验收的人不用靠眼睛。

用法：
    # 单帧静态件（塔底座、图标）
    python fit_and_validate.py --src base.png --out-dir out/towers --asset tower_base \
        --canvas 88x88 --anchor bottom --margin auto

    # 序列帧（行走/死亡/特效）
    python fit_and_validate.py --src frames_dir --out-dir out/enemies/grunt \
        --asset enemy_grunt_walk_east --canvas 48x56 --anchor bottom \
        --fps 8 --loop --facing east --frames 4

    # 引擎要求末帧全透明的死亡套
    python fit_and_validate.py ... --once --facing none --require-empty-last

    # 程序化生成的素材（已经是最终画布）
    python fit_and_validate.py ... --passthrough

    # 同目录多套动画（walk_east / walk_south / die）时，manifest.json 自动合并成
    # {"assets": [...]}，files 写成相对 --manifest-root 的路径（契约要求）
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ---------------------------------------------------------------- 基础工具

def load_rgba(path):
    img = Image.open(path)
    return np.asarray(img.convert("RGBA")).astype(np.float32)


def resize_rgba(arr, size):
    """预乘 alpha 的 LANCZOS：直接缩会从透明像素吸进灰色，边缘出脏边。"""
    alpha = arr[..., 3] / 255.0
    rgb = arr[..., :3] * alpha[..., None]
    rgb_img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").resize(size, Image.LANCZOS)
    a_img = Image.fromarray((alpha * 255).astype(np.uint8), "L").resize(size, Image.LANCZOS)
    a = np.asarray(a_img).astype(np.float32) / 255.0
    out_rgb = np.asarray(rgb_img).astype(np.float32) / np.maximum(a[..., None], 1e-6)
    return np.concatenate([np.clip(out_rgb, 0, 255), a[..., None] * 255.0], -1)


def clean_alpha(arr):
    arr = arr.copy()
    a = arr[..., 3]
    a[a < 15] = 0.0
    a[a > 240] = 255.0
    return arr


def bbox_of(arr, thresh=40.0):
    m = arr[..., 3] > thresh
    if not m.any():
        return None
    ys, xs = np.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def mask_of(arr, thresh=128.0):
    return arr[..., 3] > thresh


def iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def centroid(mask):
    ys, xs = np.where(mask)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else (0.0, 0.0)


def margin_px(canvas, manual=None):
    """透明边距：按短边 5% 分档，1–4 px。底边不留（那是接地锚点）。"""
    if manual is not None:
        return int(manual)
    return int(min(4, max(1, round(min(canvas) * 0.05))))


def symmetrize(arr):
    """左右镜像平均：用于「必须左右对称」的装饰件（AI 直出通常差 3–12%）。"""
    m = arr[..., 3] > 40
    cols = np.where(m.any(axis=0))[0]
    if not len(cols):
        return arr
    x0, x1 = int(cols.min()), int(cols.max()) + 1
    a = arr.copy()
    a[:, x0:x1, :3] = (arr[:, x0:x1, :3] + arr[:, x0:x1, :3][:, ::-1]) / 2.0
    a[:, x0:x1, 3] = np.maximum(arr[:, x0:x1, 3], arr[:, x0:x1, 3][:, ::-1])
    return a


def grade_rgba(arr, gamma=1.0, sat=1.0, val=1.0, hue_shift_deg=0.0):
    """统一调色：只动 RGB，alpha 掩膜保持不变（循环闭合依赖掩膜）。"""
    if gamma == 1.0 and sat == 1.0 and val == 1.0 and not hue_shift_deg:
        return arr

    def rgb_to_hsv(rgb):
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        mx, mn = rgb.max(-1), rgb.min(-1)
        d = mx - mn
        h = np.zeros_like(mx)
        m = d > 1e-6
        idx = m & (mx == r); h[idx] = ((g[idx] - b[idx]) / d[idx]) % 6
        idx = m & (mx == g); h[idx] = ((b[idx] - r[idx]) / d[idx]) + 2
        idx = m & (mx == b); h[idx] = ((r[idx] - g[idx]) / d[idx]) + 4
        return np.stack([h / 6.0, np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0), mx], -1)

    def hsv_to_rgb(hsv):
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        i = np.floor(h * 6.0); f = h * 6.0 - i
        p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
        i = i.astype(np.int32) % 6
        out = np.zeros(hsv.shape, np.float32)
        for k, (rr, gg, bb) in enumerate([(v, t, p), (q, v, p), (p, v, t),
                                          (p, q, v), (t, p, v), (v, p, q)]):
            m = i == k
            out[..., 0][m] = rr[m]; out[..., 1][m] = gg[m]; out[..., 2][m] = bb[m]
        return out

    out = arr.copy()
    rgb = np.power(np.clip(arr[..., :3] / 255.0, 0, 1), gamma)
    hsv = rgb_to_hsv(rgb)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg / 360.0) % 1.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 1)
    hsv[..., 2] = np.clip(hsv[..., 2] * val, 0, 1)
    out[..., :3] = np.clip(hsv_to_rgb(hsv) * 255.0, 0, 255)
    return out


def fit_frames(frames, canvas, anchor, fill=(1.0, 1.0), margin=None):
    """联合包围盒 -> 单缩放 -> 逐帧贴到画布锚点。所有帧共用同一缩放（动画不能逐帧缩放）。

    允许整帧全透明（死亡套末帧就该是空的）：空帧不参与联合包围盒，直接输出透明画布。
    """
    W, H = canvas
    boxes = [bbox_of(f) for f in frames]
    if all(b is None for b in boxes):
        raise SystemExit("all frames are fully transparent")
    solid = [b for b in boxes if b is not None]
    bx0 = min(b[0] for b in solid); by0 = min(b[1] for b in solid)
    bx1 = max(b[2] for b in solid); by1 = max(b[3] for b in solid)
    uw, uh = bx1 - bx0, by1 - by0
    mx = margin_px(canvas, margin)
    usable_w = int(round((W - 2 * mx) * fill[0]))
    usable_h = int(round(((H - mx) if anchor == "bottom" else (H - 2 * mx)) * fill[1]))
    scale = min(usable_w / uw, usable_h / uh)
    big = scale * 2.0 if scale * max(uw, uh) < 64 else scale

    pre = []
    for f, b in zip(frames, boxes):
        if b is None:
            pre.append(None)
            continue
        crop = f[by0:by1, bx0:bx1]
        pre.append(resize_rgba(crop, (max(1, int(round(crop.shape[1] * big))),
                                      max(1, int(round(crop.shape[0] * big))))))
    solid_pre = [p for p in pre if p is not None]
    s2 = min(usable_w / max(p.shape[1] for p in solid_pre),
             usable_h / max(p.shape[0] for p in solid_pre))

    outs = []
    for p in pre:
        canvas_arr = np.zeros((H, W, 4), np.float32)
        if p is None:
            outs.append(canvas_arr)
            continue
        w = max(1, int(round(p.shape[1] * s2)))
        h = max(1, int(round(p.shape[0] * s2)))
        img = resize_rgba(p, (w, h))
        x = (W - w) // 2
        y = H - h if anchor == "bottom" else (H - h) // 2
        canvas_arr[max(0, y):max(0, y) + h, max(0, x):max(0, x) + w] = img
        outs.append(clean_alpha(canvas_arr))
    return outs, s2 * scale, (bx0, by0, bx1, by1), mx


# ---------------------------------------------------------------- 校验

def check_frame(arr, canvas, anchor, check_center=True, check_edges=True, margin=None):
    W, H = canvas
    issues = []
    if arr.shape[1] != W or arr.shape[0] != H:
        issues.append(f"canvas {arr.shape[1]}x{arr.shape[0]} != {W}x{H}")
    a = arr[..., 3]
    corners = [a[0, 0], a[0, -1], a[-1, 0], a[-1, -1]]
    if any(c > 0 for c in corners):
        issues.append(f"corner alpha != 0: {[round(float(c)) for c in corners]}")
    mx = margin_px(canvas, margin)
    L, R, T = a[:, :mx].max() if mx else 0, a[:, -mx:].max() if mx else 0, a[:mx, :].max() if mx else 0
    if check_edges and (L > 8 or R > 8 or T > 8):
        issues.append(f"edge band alpha too high (L={L:.0f} R={R:.0f} T={T:.0f})")
    box = bbox_of(arr)
    if box is None:
        return issues, None          # 空帧合法（死亡末帧），由 --require-empty-last 单独判
    if anchor == "bottom":
        if box[3] != H:
            issues.append(f"bottom edge at y={box[3]} but canvas H={H} (anchor lost)")
        cx = (box[0] + box[2]) / 2.0
        if check_center and abs(cx - W / 2) > 1.0:
            issues.append(f"bottom-center off by {cx - W / 2:.1f}px")
    else:
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        if abs(cx - W / 2) > 1.0 or abs(cy - H / 2) > 1.0:
            issues.append(f"center off by ({cx - W / 2:.1f},{cy - H / 2:.1f})px")
    return issues, box


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def upsert_manifest(out_dir, entry, manifest_root):
    """同目录多套动画时写成 {"assets":[...]}；manifest 里的 files 相对 manifest_root。"""
    path = out_dir / "manifest.json"
    sets = []
    if path.exists():
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
            sets = list(cur["assets"]) if isinstance(cur, dict) and "assets" in cur \
                else ([cur] if isinstance(cur, dict) and cur.get("asset") else [])
        except Exception:
            sets = []
    sets = [s for s in sets if s.get("asset") != entry["asset"]] + [entry]
    sets.sort(key=lambda s: s.get("asset", ""))
    payload = sets[0] if len(sets) == 1 else {"assets": sets}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True, help="源：单张 png 或帧目录")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--asset", required=True, help="素材名（文件名前缀）")
    p.add_argument("--canvas", required=True, help="WxH")
    p.add_argument("--anchor", choices=["bottom", "center"], default="bottom")
    p.add_argument("--fps", type=float, default=None)
    p.add_argument("--loop", action="store_true")
    p.add_argument("--once", action="store_true", help="播一次（loop=false）")
    p.add_argument("--facing", default="none", help="east/south/north/none")
    p.add_argument("--frames", type=int, default=None, help="期望帧数，不符直接失败")
    p.add_argument("--fill", default="1.0,1.0", help="内容占可用区域比例 fx,fy")
    p.add_argument("--margin", type=int, default=None, help="透明边距像素，默认按短边 5 个百分点分档")
    p.add_argument("--grade", default=None, help="调色：gamma=0.6,sat=0.8,val=1.05,hue=3")
    p.add_argument("--symmetrize", action="store_true", help="左右镜像平均（装饰件必用）")
    p.add_argument("--passthrough", action="store_true", help="源已是最终画布，只清 alpha")
    p.add_argument("--require-empty-last", action="store_true")
    p.add_argument("--allow-offcenter", action="store_true", help="剪影可不居中（挥武器/迈步）")
    p.add_argument("--allow-touch-edges", action="store_true", help="允许左右贴边（全屏/满画布爆心）")
    p.add_argument("--manifest-root", default=None, help="manifest.files 的相对根（默认 = out-dir 的 3 级父目录）")
    p.add_argument("--source", default="ai-game-sprite")
    p.add_argument("--license", default="project-owned")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--iou-threshold", type=float, default=0.95, help="循环首尾帧 IoU 阈值（真实步态建议别用它判，见 FIELD-NOTES 6）")
    p.add_argument("--warn-only", action="store_true", help="有问题也只打印、退出码仍为 0（CI 里不想被已知争议项卡住时用）")
    p.add_argument("--report", default=None, help="校验报告 json")
    args = p.parse_args()

    W, H = (int(x) for x in args.canvas.lower().split("x"))
    canvas = (W, H)
    src = Path(args.src)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        files = sorted(src.glob("*.png"))
        if not files:
            raise SystemExit(f"no png in {src}")
        if args.frames and len(files) != args.frames:
            raise SystemExit(f"frame count {len(files)} != expected {args.frames}")
        frames = [load_rgba(f) for f in files]
    else:
        frames = [load_rgba(src)]

    grade = {}
    if args.grade:
        for part in args.grade.split(","):
            k, v = part.split("=")
            grade[{"hue": "hue_shift_deg"}.get(k.strip(), k.strip())] = float(v)
    if grade:
        frames = [grade_rgba(f, **grade) for f in frames]
    if args.symmetrize:
        frames = [symmetrize(f) for f in frames]

    fill = tuple(float(x) for x in args.fill.split(","))
    if args.passthrough:
        outs = []
        for f in frames:
            if f.shape[1] != W or f.shape[0] != H:
                raise SystemExit(f"passthrough size {f.shape[1]}x{f.shape[0]} != {W}x{H}")
            outs.append(clean_alpha(f))
        scale, union, mx = 1.0, None, margin_px(canvas, args.margin)
    else:
        outs, scale, union, mx = fit_frames(frames, canvas, args.anchor, fill, args.margin)

    out_files = ([out_dir / f"{args.asset}.png"] if len(outs) == 1
                 else [out_dir / f"{args.asset}_{i:02d}.png" for i in range(len(outs))])
    for arr, path in zip(outs, out_files):
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA").save(path, optimize=True)

    issues = []
    for i, arr in enumerate(outs):
        fi, _ = check_frame(arr, canvas, args.anchor,
                            check_center=not args.allow_offcenter,
                            check_edges=not args.allow_touch_edges,
                            margin=args.margin)
        issues += [f"f{i}: {x}" for x in fi]

    loop_metrics = None
    loop_iou = shift = None
    if len(outs) > 1:
        m0, m1 = mask_of(outs[0]), mask_of(outs[-1])
        loop_iou = iou(m0, m1)
        c0, c1 = centroid(m0), centroid(m1)
        shift = max(abs(c0[0] - c1[0]), abs(c0[1] - c1[1]))
        if args.loop and loop_iou < 0.95:
            issues.append(f"loop IoU {loop_iou:.3f} < {args.iou_threshold}（真实步态通常达不到，见 FIELD-NOTES 第 6 条的 wrap_vs_avg 口径）")
        trans = [iou(mask_of(outs[k]), mask_of(outs[k + 1])) for k in range(len(outs) - 1)]
        avg = sum(trans) / len(trans) if trans else 0.0
        loop_metrics = {
            "iou_first_last": round(loop_iou, 4),
            "centroid_shift_px": round(shift, 3),
            "iou_transitions": [round(t, 4) for t in trans],
            "wrap_vs_avg": round(loop_iou / avg, 3) if avg else None,
        }
    if args.require_empty_last and mask_of(outs[-1]).any():
        issues.append("last frame is not empty (require-empty-last)")

    mirror = None
    if args.symmetrize:
        a = outs[0][..., :3] * (outs[0][..., 3:4] / 255.0)
        m = outs[0][..., 3] > 128
        cols = np.where(m.any(axis=0))[0]
        if len(cols):
            x0, x1 = cols.min(), cols.max() + 1
            base = a[:, x0:x1]
            denom = np.abs(base).sum() or 1.0
            mirror = float(np.abs(base - base[:, ::-1]).sum() / denom)

    manifest_root = Path(args.manifest_root) if args.manifest_root else out_dir.parent.parent
    entry = {
        "asset": args.asset,
        "canvas": [W, H],
        "origin": "top_left",
        "anchor_px": [W // 2, H] if args.anchor == "bottom" else [W // 2, H // 2],
        "frames": len(outs),
        "fps": args.fps,
        "loop": bool(args.loop and not args.once),
        "facing": args.facing,
        "pixel_density": 1.0,
        "files": [p.relative_to(manifest_root).as_posix() for p in out_files],
        "source": args.source,
        "license": args.license,
        "seed": args.seed,
        "sha256_frames": [sha256(p) for p in out_files],
        "alpha_margin_px": mx,
        "fill": list(fill),
        "grade": grade,
        "loop_metrics": loop_metrics,
    }
    sidecar = dict(entry)
    sidecar["files"] = [p.name for p in out_files]
    if len(out_files) == 1:
        sidecar["file"] = out_files[0].name
    (out_dir / f"{args.asset}.json").write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
    upsert_manifest(out_dir, entry, manifest_root)

    status = "PASS" if not issues else "FAIL"
    report = {
        "asset": args.asset, "status": status, "canvas": list(canvas), "anchor": args.anchor,
        "scale": round(scale, 4), "union_bbox_src": union, "margin_px": mx,
        "loop_iou": None if loop_iou is None else round(loop_iou, 4),
        "loop_centroid_shift_px": None if shift is None else round(shift, 3),
        "loop_metrics": loop_metrics, "mirror_diff": None if mirror is None else round(mirror, 4),
        "opaque_px": [int(mask_of(f).sum()) for f in outs],
        "issues": issues, "files": [p.name for p in out_files],
    }
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[{status}] {args.asset} {W}x{H} frames={len(outs)} scale={scale:.3f}")
    for it in issues:
        print("   -", it)
    if args.warn_only:
        return 0
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
