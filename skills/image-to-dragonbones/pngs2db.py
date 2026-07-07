"""Convert LayerDiff part PNGs → DragonBones 5.5 skeleton + atlas."""

import json
import os
import os.path as osp
import argparse
from glob import glob
from PIL import Image
import numpy as np


def _flip_y(y, canvas_h):
    return canvas_h - y


def find_bbox(img, threshold=30, min_row_px=3):
    """Find tight bounding box of non-transparent content.
    Filters isolated noise by requiring at least min_row_px pixels per row/col.
    """
    arr = np.array(img)
    if arr.shape[2] < 4:
        return None
    alpha = arr[..., -1]
    mask = alpha > threshold
    if not np.any(mask):
        return None

    h, w = mask.shape

    # erode once to remove single-pixel noise
    import scipy.ndimage as ndi
    eroded = ndi.binary_erosion(mask, structure=np.ones((3, 3)), iterations=1)
    if not np.any(eroded):
        eroded = mask  # fallback

    # find rows/cols with at least min_row_px content pixels
    rows = np.sum(eroded, axis=1) >= min_row_px
    cols = np.sum(eroded, axis=0) >= min_row_px

    if not np.any(rows) or not np.any(cols):
        # fallback: try without min_row_px filter
        rows = np.any(eroded, axis=1)
        cols = np.any(eroded, axis=0)
        if not np.any(rows) or not np.any(cols):
            return None

    y1, y2 = np.where(rows)[0][[0, -1]]
    x1, x2 = np.where(cols)[0][[0, -1]]
    return int(x1), int(y1), int(x2), int(y2)


def pack_atlas(crops, padding=2):
    """Simple horizontal strip packing."""
    total_w = sum(crp.size[0] + padding for crp, _, _, _, _ in crops) - padding
    total_h = max(crp.size[1] for crp, _, _, _, _ in crops) if crops else 0
    atlas = Image.new('RGBA', (max(total_w, 1), max(total_h, 1)), (0, 0, 0, 0))
    regions = []
    cx = 0
    for crp, part_name, crop_rect, orig_w, orig_h in crops:
        cw, ch = crp.size
        atlas.paste(crp, (cx, 0))
        regions.append({
            'name': part_name,
            'x': cx, 'y': 0,
            'w': cw, 'h': ch,
            'frame_x': crop_rect[0],
            'frame_y': crop_rect[1],
            'frame_w': orig_w,
            'frame_h': orig_h,
            'pivot_x': crop_rect[0] + (cw - 1) / 2.0,
            'pivot_y': crop_rect[1] + (ch - 1) / 2.0,
        })
        cx += cw + padding
    return atlas, regions


def make_tex_json(regions, atlas_w, atlas_h, image_path):
    subs = []
    for r in regions:
        sub = {
            'name': r['name'],
            'x': r['x'],
            'y': r['y'],
            'width': r['w'],
            'height': r['h'],
        }
        if r['frame_w'] > 0 and r['frame_h'] > 0:
            sub['frameWidth'] = r['frame_w']
            sub['frameHeight'] = r['frame_h']
        subs.append(sub)
    return {
        'name': osp.splitext(osp.basename(image_path))[0],
        'imagePath': image_path,
        'width': atlas_w,
        'height': atlas_h,
        'SubTexture': subs,
    }


Z_ORDER = [
    'back hair', 'tail', 'wings',
    'neckwear',
    'bottomwear',
    'legwear',
    'footwear',
    'topwear',
    'handwear',
    'objects',
    'neck',
    'head',
    'ears', 'earwear',
    'headwear',
    'face',
    'eyewear',
    'eyebrow', 'eyewhite', 'irides', 'eyelash',
    'eyes',
    'nose',
    'mouth',
    'front hair',
]


def make_ske_json(regions, canvas_w, canvas_h, part_names):
    bones = [{
        'name': 'root',
        'length': 0,
    }]
    slots = []
    displays_by_slot = {}
    seen_slots = []

    # assign z-order
    name_to_idx = {}
    for idx, name in enumerate(part_names):
        z = Z_ORDER.index(name) if name in Z_ORDER else 99
        name_to_idx[name] = (z, idx)

    sorted_parts = sorted(part_names, key=lambda n: name_to_idx[n])

    slot_index = 0
    for part_name in sorted_parts:
        r = [x for x in regions if x['name'] == part_name]
        if not r:
            continue
        r = r[0]

        # position in DB coords (Y-up, origin at center of canvas)
        cx = canvas_w / 2.0
        cy = canvas_h / 2.0
        db_x = r['pivot_x'] - cx
        db_y = _flip_y(r['pivot_y'], canvas_h) - _flip_y(cy, canvas_h)
        # Actually simpler: DB y = canvas_h - pivot_y; center in DB = canvas_h/2
        db_x = r['pivot_x'] - cx
        db_y = canvas_h - r['pivot_y'] - (canvas_h - cy)

        slot_name = f'slot_{part_name.replace(" ", "_")}'
        slots.append({
            'name': slot_name,
            'parent': 'root',
        })

        disp = {
            'name': part_name,
            'type': 'image',
            'width': r['w'],
            'height': r['h'],
            'transform': {
                'x': round(db_x, 3),
                'y': round(db_y, 3),
            },
            'pivot': {
                'x': round((r['pivot_x'] - r['frame_x']) / r['w'], 4) if r['w'] > 0 else 0.5,
                'y': round(1.0 - (r['pivot_y'] - r['frame_y']) / r['h'], 4) if r['h'] > 0 else 0.5,
            },
        }
        displays_by_slot[slot_name] = [disp]
        seen_slots.append(slot_name)

    armature = {
        'name': 'Armature',
        'type': 'Armature',
        'frameRate': 30,
        'bone': bones,
        'slot': slots,
        'skin': [
            {
                'slot': [
                    {
                        'name': sn,
                        'display': displays_by_slot[sn],
                    }
                    for sn in seen_slots
                ],
            }
        ],
        'animation': [
            {
                'name': 'idle',
                'duration': 1,
                'playTimes': 0,
                'bone': [
                    {
                        'name': 'root',
                        'translateFrame': [
                            {'duration': 1, 'tweenEasing': 0.0, 'x': 0, 'y': 0},
                        ],
                    },
                ],
                'slot': [
                    {
                        'name': sn,
                        'displayFrame': [
                            {'duration': 1, 'value': 0},
                        ],
                    }
                    for sn in seen_slots
                ],
            },
        ],
    }

    return {
        'name': 'Character',
        'version': '5.5',
        'compatibleVersion': '5.5',
        'frameRate': 30,
        'armature': [armature],
    }


def main():
    parser = argparse.ArgumentParser(description='Convert part PNGs to DragonBones')
    parser.add_argument('input_dir', help='Directory containing part PNGs')
    parser.add_argument('output_dir', help='Output directory for DB files')
    parser.add_argument('--name', default='character', help='Output base name')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # find all part PNGs
    pngs = sorted(glob(osp.join(args.input_dir, '*.png')))
    # filter out src_*, _depth, optimized, reconstruction
    pngs = [p for p in pngs if 'src_' not in osp.basename(p)
            and '_depth' not in osp.basename(p)
            and osp.basename(p) not in ('optimized.png', 'reconstruction.png')]

    if not pngs:
        print('No part PNGs found')
        return

    # find canvas size from biggest part
    canvas_w, canvas_h = 0, 0
    for p in pngs:
        img = Image.open(p)
        if img.width > canvas_w:
            canvas_w = img.width
        if img.height > canvas_h:
            canvas_h = img.height

    crops = []
    part_names = []
    min_area = 20  # skip tiny/noise parts
    for p in pngs:
        name = osp.splitext(osp.basename(p))[0]
        img = Image.open(p).convert('RGBA')
        bbox = find_bbox(img)
        if bbox is None:
            print(f'  skip {name}: no alpha content')
            continue
        x1, y1, x2, y2 = bbox
        cw, ch = x2 - x1 + 1, y2 - y1 + 1
        if cw * ch < min_area:
            print(f'  skip {name}: too small ({cw}x{ch})')
            continue
        crop = img.crop((x1, y1, x2 + 1, y2 + 1))
        crops.append((crop, name, (x1, y1, x2 + 1, y2 + 1), img.width, img.height))
        part_names.append(name)
        print(f'  {name}: bbox=({x1},{y1},{x2},{y2}) size={crop.size}')

    # pack atlas
    atlas_img, regions = pack_atlas(crops)
    tex_name = f'{args.name}_tex.png'
    atlas_img.save(osp.join(args.output_dir, tex_name))

    # write _tex.json
    tex_json = make_tex_json(regions, atlas_img.width, atlas_img.height, tex_name)
    with open(osp.join(args.output_dir, f'{args.name}_tex.json'), 'w', encoding='utf-8') as f:
        json.dump(tex_json, f, indent=2, ensure_ascii=False)

    # write _ske.json
    ske_json = make_ske_json(regions, canvas_w, canvas_h, part_names)
    with open(osp.join(args.output_dir, f'{args.name}_ske.json'), 'w', encoding='utf-8') as f:
        json.dump(ske_json, f, indent=2, ensure_ascii=False)

    print(f'\nDone! Output in {args.output_dir}')
    print(f'  {tex_name} ({atlas_img.width}x{atlas_img.height})')
    print(f'  {args.name}_tex.json ({len(regions)} sub-textures)')
    print(f'  {args.name}_ske.json ({len(part_names)} parts)')


if __name__ == '__main__':
    main()
