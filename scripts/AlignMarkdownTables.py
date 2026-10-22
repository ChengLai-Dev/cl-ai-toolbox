#!/usr/bin/env python3
"""AlignMarkdownTables.py — 按显示宽度对齐 Markdown 表格的竖线。

用法：
    python AlignMarkdownTables.py <文件或目录> [<文件或目录> ...] [选项]

选项：
    --check     只检查不写入；存在需要重排的表格时退出码为 1（可用于落盘后校验）
    --quiet     不打印每个文件的处理结果
    --verbose   打印被跳过的表格及原因

行为约定：
    * 只处理以 "|" 开头、且下一行是分隔行的表格；其余内容一字不动。
    * 跳过围栏代码块（``` / ~~~）内部的内容，不会动示例里的表格样板。
    * 保留表格原有的行首缩进（列表 / 引用里的表格不会被拉回行首）。
    * 保留分隔行的对齐标记（:---、:---:、---:）。
    * 支持单元格内 `\\|` 转义，重排时原样保留。
    * 各行列数不一致时跳过该表并报警，不做猜测性修复。
    * 显示宽度：东亚宽字符(W/F)、emoji 记 2 列；组合字符与变体选择符记 0 列。
    * 行尾风格（LF / CRLF）与 UTF-8 BOM 原样保留；重复执行结果不变（幂等）。
"""

import argparse
import sys
import unicodedata
from pathlib import Path

# east_asian_width 把一部分 emoji 报成 'A'/'N'，但实际渲染占两列，这里显式补齐。
WIDE_OVERRIDES = {
    0x26A0,  # ⚠
    0x26A1,  # ⚡
    0x2714,  # ✔
    0x2716,  # ✖
    0x2757,  # ❗
    0x2753,  # ❓
    0x2B50,  # ⭐
    0x203C,  # ‼
    0x2049,  # ⁉
    0x2139,  # ℹ
}

ZERO_WIDTH = {
    0xFE0E,  # variation selector-15
    0xFE0F,  # variation selector-16
    0x200B,  # zero width space
    0x200C,  # zero width non-joiner
    0x200D,  # zero width joiner
}


def display_width(text: str) -> int:
    total = 0
    for ch in text:
        code = ord(ch)
        if code in ZERO_WIDTH or unicodedata.combining(ch):
            continue
        if code in WIDE_OVERRIDES:
            total += 2
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def split_cells(line: str) -> list[str]:
    """按未转义的 '|' 切分单元格，保留 '\\|' 原样。"""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]

    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            buf.append("\\|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def is_separator(line: str) -> bool:
    stripped = line.strip()
    if "-" not in stripped:
        return False
    if not set(stripped) <= set("|-: \t"):
        return False
    return all(cell.strip(": \t").count("-") > 0 for cell in split_cells(stripped))


def separator_marker(cell: str) -> tuple[bool, bool]:
    """返回 (左对齐标记?, 右对齐标记?)。"""
    stripped = cell.strip()
    return stripped.startswith(":"), stripped.endswith(":")


def render(rows: list[list[str]], markers: list[tuple[bool, bool]], indent: str) -> list[str]:
    widths = [max(display_width(row[c]) for row in rows) for c in range(len(rows[0]))]
    widths = [max(w, 3) for w in widths]

    out: list[str] = []
    for row_index, row in enumerate(rows):
        padded: list[str] = []
        for col, cell in enumerate(row):
            if row_index == 1:  # 分隔行
                left, right = markers[col]
                body = "-" * max(widths[col] - int(left) - int(right), 1)
                padded.append((":" if left else "") + body + (":" if right else ""))
            else:
                padded.append(cell + " " * (widths[col] - display_width(cell)))
        out.append(f"{indent}| " + " | ".join(padded) + " |")
    return out


def align_tables(lines: list[str], verbose: bool) -> tuple[list[str], int, int]:
    """返回 (新行, 重排表格数, 跳过表格数)。"""
    result: list[str] = []
    changed = 0
    skipped = 0
    i = 0
    fence = None  # 当前围栏代码块的标记，None 表示不在代码块内

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块：进入/退出，内部一律不处理
        if fence is None:
            for marker in ("```", "~~~"):
                if stripped.startswith(marker):
                    fence = marker
                    break
        else:
            if stripped.startswith(fence):
                fence = None
            result.append(line)
            i += 1
            continue

        if (
            fence is None
            and stripped.startswith("|")
            and i + 1 < len(lines)
            and is_separator(lines[i + 1])
        ):
            block: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1

            grid = [split_cells(row) for row in block]
            counts = {len(row) for row in grid}
            has_tab = any("\t" in row for row in block)
            if len(counts) != 1 or has_tab:
                skipped += 1
                if verbose:
                    reason = "列数不一致" if len(counts) != 1 else "单元格含制表符"
                    print(f"  [skip] 第 {i - len(block) + 1} 行起的表格：{reason}", file=sys.stderr)
                result.extend(block)
                continue

            indent = block[0][: len(block[0]) - len(block[0].lstrip())]
            markers = [separator_marker(cell) for cell in grid[1]]
            new_block = render(grid, markers, indent)
            if new_block != block:
                changed += 1
            result.extend(new_block)
            continue

        result.append(line)
        i += 1

    return result, changed, skipped


def process_file(path: Path, check: bool, quiet: bool, verbose: bool) -> tuple[int, int, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw

    crlf = b"\r\n" in body
    text = body.decode("utf-8").replace("\r\n", "\n")

    new_lines, changed, skipped = align_tables(text.split("\n"), verbose)
    if changed == 0:
        if not quiet and verbose:
            print(f"{path}: 已对齐（无需改动）")
        return changed, skipped, False

    if not quiet:
        print(f"{path}: 重排 {changed} 张表" + (f"，跳过 {skipped} 张" if skipped else ""))

    if check:
        return changed, skipped, True

    out = "\n".join(new_lines)
    if crlf:
        out = out.replace("\n", "\r\n")
    data = out.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)
    return changed, skipped, True


def collect(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.md") if p.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            print(f"路径不存在：{path}", file=sys.stderr)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="按显示宽度对齐 Markdown 表格竖线")
    parser.add_argument("targets", nargs="+", help="md 文件或目录（目录递归处理 *.md）")
    parser.add_argument("--check", action="store_true", help="只检查不写入，有需重排的表时退出码 1")
    parser.add_argument("--quiet", action="store_true", help="不输出每个文件的结果")
    parser.add_argument("--verbose", action="store_true", help="输出被跳过的表格及原因")
    args = parser.parse_args()

    files = collect(args.targets)
    if not files:
        print("没有找到可处理的 .md 文件", file=sys.stderr)
        return 2

    need_fix = 0
    for path in files:
        _, _, touched = process_file(path, args.check, args.quiet, args.verbose)
        if touched:
            need_fix += 1

    if args.check:
        if need_fix:
            print(f"\n需要重排：{need_fix} 个文件", file=sys.stderr)
            return 1
        if not args.quiet:
            print("\n校验通过：所有表格已对齐")
    return 0


if __name__ == "__main__":
    sys.exit(main())
