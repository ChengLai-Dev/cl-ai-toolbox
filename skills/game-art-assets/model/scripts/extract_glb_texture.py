"""从 GLB 的 BIN chunk 里抽出内嵌贴图。

用途：
    Blender -> FBX -> UE 这条链路经常丢内嵌贴图，UE 会报
        UInterchangeTextureFactory: Invalid translator couldn't retrieve a payload
    这时直接从 GLB 里把 image 抽出来单独导入。

用法:
    python extract_glb_texture.py <in.glb> [out_dir]

注意：
    Quaternius 一类资产的"贴图"其实是一条 32x32 的调色板色带，
    抽出来就是几块纯色。这是资产本身的样子，不是抽取失败。
    导入 UE 后把 Filter 设为 TF_NEAREST，否则相邻色块会互相渗色。
"""

import json
import os
import struct
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: extract_glb_texture.py <in.glb> [out_dir]")

    glb = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(glb)
    os.makedirs(out_dir, exist_ok=True)

    with open(glb, "rb") as f:
        data = f.read()

    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise SystemExit("not a glb: %s" % glb)

    offset = 12
    chunks = {}
    while offset < total:
        clen, ctype = struct.unpack_from("<I4s", data, offset)
        offset += 8
        chunks[ctype] = data[offset:offset + clen]
        offset += clen

    gltf = json.loads(chunks[b"JSON"].decode("utf-8"))
    images = gltf.get("images", [])
    print("images", len(images))

    if not images:
        print("NO_EMBEDDED_IMAGE  该 GLB 没有内嵌贴图（多为纯色材质）")
        return

    bin_chunk = chunks.get(b"BIN\x00", b"")
    for i, img in enumerate(images):
        if "bufferView" not in img:
            print("SKIP image[%d] 外部引用: %s" % (i, img.get("uri")))
            continue
        bv = gltf["bufferViews"][img["bufferView"]]
        start = bv.get("byteOffset", 0)
        blob = bin_chunk[start:start + bv["byteLength"]]
        ext = ".png" if "png" in img.get("mimeType", "") else ".jpg"
        name = img.get("name") or ("texture_%02d" % i)
        path = os.path.join(out_dir, name + ext)
        with open(path, "wb") as f:
            f.write(blob)
        print("WROTE", path, len(blob), "bytes")


main()
