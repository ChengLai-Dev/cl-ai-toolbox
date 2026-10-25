#!/usr/bin/env python
"""环境自检：确认流水线、ComfyUI、模型、Godot、内存是否就绪。"""

import ctypes
import os
import subprocess
from pathlib import Path

PIPELINE_ROOT = Path(os.environ.get("AI_GAME_PIPELINE_ROOT", r"D:\Code\opencode-workspace\ai-game-pipeline"))
COMFY_DIR = Path(os.environ.get("AI_GAME_COMFY_DIR", r"D:\Code\ComfyUI\ComfyUI-0.36.0"))
GODOT = Path(os.environ.get("AI_GAME_GODOT", r"D:\Code\Godot\godot.exe"))


def mark(ok):
    return "OK  " if ok else "MISS"


def check_file(path, label):
    exists = Path(path).exists()
    print(f"{mark(exists)} {label}: {path}")
    return exists


def check_comfy_running():
    result = subprocess.run(
        ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}", "--max-time", "3",
         "http://127.0.0.1:8188/system_stats"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() == "200"


def free_ram_gb():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / (1024 ** 3), status.ullTotalPhys / (1024 ** 3)


def gpu_info():
    """查显存占用。Z-Image + ControlNet 峰值约 7.7GB，8GB 卡上不能有别的程序占着。"""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free",
         "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("MISS nvidia-smi 不可用")
        return
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name, total, used, free = parts[0], parts[1], parts[2], parts[3]
        used_mb = int(used.split()[0])
        ok = used_mb < 1024
        print(f"{mark(ok)} gpu: {name}  used {used} / {total}  free {free}")
        if not ok:
            print("      显存被别的程序占用，关掉再跑（Z-Image 峰值约 7.7GB）")


def main():
    print("=== 流水线 ===")
    check_file(PIPELINE_ROOT, "pipeline root")
    for name in ("run_pipeline.py", "gen_look.py", "run_wan_a14b.py", "import_frames.py",
                 "pack_atlas.py", "make_control.py", "device_scheduler.py",
                 "post_process.py", "prep_source.py", "comfy_client.py", "comfy_ctl.py"):
        check_file(PIPELINE_ROOT / "pipeline" / name, name)

    print("\n=== Z-Image 模型 ===")
    check_file(PIPELINE_ROOT / "models" / "z-image-gguf" / "z_image_turbo-Q6_K.gguf", "gguf Q6")
    check_file(PIPELINE_ROOT / "models" / "z-image-gguf" / "config.json", "gguf config")
    check_file(PIPELINE_ROOT / "models" / "z-image-turbo" / "model_index.json", "z-image index")

    print("\n=== ControlNet 模型（默认流程必需）===")
    check_file(PIPELINE_ROOT / "models" / "z-image-controlnet" /
               "Z-Image-Turbo-Fun-Controlnet-Union.safetensors", "controlnet weights")
    check_file(PIPELINE_ROOT / "models" / "z-image-controlnet" / "config.json", "controlnet config")

    print("\n=== ComfyUI ===")
    check_file(COMFY_DIR / "main.py", "comfy dir")
    check_file(COMFY_DIR / "models" / "diffusion_models" / "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "A14B high")
    check_file(COMFY_DIR / "models" / "diffusion_models" / "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "A14B low")
    check_file(COMFY_DIR / "models" / "text_encoders" / "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5")
    check_file(COMFY_DIR / "models" / "vae" / "wan_2.1_vae.safetensors", "wan2.1 vae")
    check_file(COMFY_DIR / "models" / "loras" / "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "4-step lora")

    running = check_comfy_running()
    print(f"{mark(running)} ComfyUI service: {'running' if running else 'not running (run_comfyui.bat)'}")

    print("\n=== 后处理模型（静态资源模式用）===")
    check_file(COMFY_DIR / "models" / "background_removal" / "birefnet.safetensors",
               "birefnet (BiRefNet, MIT)")
    check_file(COMFY_DIR / "models" / "background_removal" / "lucida.safetensors",
               "lucida (BiRefNet 插画版, 可选)")
    check_file(COMFY_DIR / "models" / "upscale_models" / "4x-UltraSharp.pth",
               "4x-UltraSharp (ESRGAN, BSD-3)")

    print("\n=== 引擎 ===")
    check_file(GODOT, "godot")

    print("\n=== 显存 ===")
    gpu_info()

    print("\n=== 内存 ===")
    free, total = free_ram_gb()
    ok = free >= 20
    print(f"{mark(ok)} free RAM: {free:.1f} / {total:.1f} GB (need >= 20 for Z-Image + Wan)")
    if not ok:
        print("      close games/browsers before running gen_look.py")


if __name__ == "__main__":
    main()
