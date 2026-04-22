#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 Live2D 官方 Cubism SDK（Native/Unity 等）样例资源中导入 Hiyori 的动作 (.motion3.json)，
并更新本项目的 `hiyori_free_t08.model3.json` 的 Motions 列表。

为什么需要脚本：
- 官方 SDK 下载页需要同意许可，无法在代码里直接拉取
- 你本地解压 SDK 后，本脚本可以一键把更多“官方动作”接入到当前 Live2D 工程

用法示例（PowerShell）：
  python scripts/import_official_hiyori_motions.py --sdk-root "D:\\Downloads\\CubismSdkForNative-5-r1"

说明：
- 会在 sdk-root 下递归搜索 `*Hiyori*` 目录中的 `*.motion3.json`
- 会复制到 `src/frontend/live2d/src/main/resources/res/motion/`
- 会尽量把动作按文件名归入已有组（Idle / Tap / Tap@Body / Flick / FlickDown / Flick@Body），无法判断的归入 Idle
- 默认不会覆盖同名文件；用 --overwrite 可覆盖
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


RE_GROUP_HINTS: list[tuple[str, str]] = [
    (r"(?:^|[_-])idle(?:[_-]|$)", "Idle"),
    (r"(?:^|[_-])tapbody(?:[_-]|$)", "Tap@Body"),
    (r"(?:^|[_-])tap(?:[_-]|$)", "Tap"),
    (r"(?:^|[_-])flickdown(?:[_-]|$)", "FlickDown"),
    (r"(?:^|[_-])flickbody(?:[_-]|$)", "Flick@Body"),
    (r"(?:^|[_-])flick(?:[_-]|$)", "Flick"),
]


def _guess_group(filename: str) -> str:
    base = filename.lower()
    for pat, group in RE_GROUP_HINTS:
        if re.search(pat, base):
            return group
    return "Idle"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sdk-root", required=True, help="解压后的官方 Cubism SDK 根目录")
    p.add_argument(
        "--model3",
        default="src/frontend/live2d/src/main/resources/res/hiyori_free_t08.model3.json",
        help="要更新的 model3.json 路径（相对项目根目录）",
    )
    p.add_argument(
        "--motion-dir",
        default="src/frontend/live2d/src/main/resources/res/motion",
        help="本项目动作目录（相对项目根目录）",
    )
    p.add_argument("--overwrite", action="store_true", help="覆盖同名 motion3.json")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    sdk_root = Path(args.sdk_root).expanduser().resolve()
    model3_path = (repo_root / args.model3).resolve()
    dst_motion_dir = (repo_root / args.motion_dir).resolve()
    dst_motion_dir.mkdir(parents=True, exist_ok=True)

    if not sdk_root.exists():
        raise SystemExit(f"sdk-root 不存在：{sdk_root}")
    if not model3_path.exists():
        raise SystemExit(f"model3.json 不存在：{model3_path}")

    # 找 motion3.json（尽量限定在包含 Hiyori 的路径下）
    candidates = []
    for pth in sdk_root.rglob("*.motion3.json"):
        s = str(pth).lower()
        if "hiyori" in s:
            candidates.append(pth)

    if not candidates:
        raise SystemExit(
            "在 sdk-root 下没有找到包含 'Hiyori' 的 *.motion3.json。\n"
            "请确认你解压的是包含 Samples/Resources 的官方 SDK，并且资源里有 Hiyori 模型。"
        )

    model3 = _load_json(model3_path)
    file_refs = model3.setdefault("FileReferences", {})
    motions = file_refs.setdefault("Motions", {})

    added_files: list[tuple[str, Path]] = []
    skipped: list[Path] = []

    for src in sorted(candidates):
        dst_name = src.name.lower()
        # 统一到项目命名风格：hiyori_*.motion3.json
        if not dst_name.startswith("hiyori"):
            dst_name = "hiyori_" + dst_name
        dst = dst_motion_dir / dst_name

        if dst.exists() and not args.overwrite:
            skipped.append(src)
            continue

        shutil.copy2(src, dst)
        group = _guess_group(dst.name)
        motions.setdefault(group, [])

        # model3.json 里使用相对 res/ 的路径
        rel = f"motion/{dst.name}"
        # 去重
        if not any((isinstance(x, dict) and x.get("File") == rel) for x in motions[group]):
            motions[group].append({"File": rel})

        added_files.append((group, dst))

    _save_json(model3_path, model3)

    print(f"[OK] 导入完成：新增 {len(added_files)} 个动作，跳过 {len(skipped)} 个（已存在）")
    if added_files:
        by_group: dict[str, int] = {}
        for g, _ in added_files:
            by_group[g] = by_group.get(g, 0) + 1
        print("[OK] 动作组统计：")
        for g in sorted(by_group):
            print(f"  - {g}: +{by_group[g]}")
    print(f"[OK] 已更新：{model3_path}")


if __name__ == "__main__":
    main()

