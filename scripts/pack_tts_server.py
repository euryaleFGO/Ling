# -*- coding: utf-8 -*-
"""
打包 TTS 服务器部署包
运行: python scripts/pack_tts_server.py
"""

import os
import shutil
import zipfile
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
TTS_DIR = PROJECT_ROOT / "src" / "backend" / "tts"
DEPLOY_DIR = PROJECT_ROOT / "deploy" / "tts_server"
OUTPUT_ZIP = PROJECT_ROOT / "deploy" / "tts_server.zip"

# 需要复制的文件/目录
COPY_LIST = [
    # TTS 核心代码
    (TTS_DIR / "service.py", "service.py"),
    (TTS_DIR / "engine", "engine"),
    (TTS_DIR / "cosyvoice", "cosyvoice"),
    (TTS_DIR / "third_party" / "Matcha-TTS" / "matcha", "third_party/Matcha-TTS/matcha"),
    
    # 部署配置
    (DEPLOY_DIR / "README.md", "README.md"),
    (DEPLOY_DIR / "requirements.txt", "requirements.txt"),
    (DEPLOY_DIR / "start.sh", "start.sh"),
]

# 排除的文件模式
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".DS_Store",
    "*.egg-info",
]

def should_exclude(path: Path) -> bool:
    """判断是否应该排除"""
    name = path.name
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False

def copy_item(src: Path, dst: Path):
    """复制文件或目录"""
    if not src.exists():
        print(f"  [跳过] 不存在: {src}")
        return
    
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  [复制] {src.name}")
    else:
        # 复制目录
        if dst.exists():
            shutil.rmtree(dst)
        
        def ignore_func(dir, files):
            return [f for f in files if should_exclude(Path(dir) / f)]
        
        shutil.copytree(src, dst, ignore=ignore_func)
        print(f"  [复制] {src.name}/ ({count_files(dst)} 个文件)")

def count_files(path: Path) -> int:
    """统计目录下文件数量"""
    return sum(1 for _ in path.rglob("*") if _.is_file())

def create_init_files(base_dir: Path):
    """创建必要的 __init__.py"""
    dirs_need_init = [
        base_dir,
        base_dir / "engine",
        base_dir / "cosyvoice",
        base_dir / "third_party",
        base_dir / "third_party" / "Matcha-TTS",
    ]
    
    for d in dirs_need_init:
        init_file = d / "__init__.py"
        if d.exists() and not init_file.exists():
            init_file.touch()

def create_zip(source_dir: Path, output_path: Path):
    """创建 ZIP 文件"""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file() and not should_exclude(file_path):
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, f"tts_server/{arcname}")
    
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[完成] 创建 ZIP: {output_path}")
    print(f"       大小: {size_mb:.2f} MB")

def main():
    print("=" * 50)
    print("TTS 服务器打包工具")
    print("=" * 50)
    
    # 创建临时打包目录
    pack_dir = PROJECT_ROOT / "deploy" / "_pack_temp"
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True)
    
    print("\n[1/3] 复制文件...")
    for src, dst_rel in COPY_LIST:
        dst = pack_dir / dst_rel
        copy_item(Path(src), dst)
    
    print("\n[2/3] 创建 __init__.py...")
    create_init_files(pack_dir)
    
    # 创建模型目录占位
    models_dir = pack_dir / "models" / "TTS"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / ".gitkeep").touch()
    
    # 创建参考音频目录
    ref_dir = pack_dir / "reference_audio"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / ".gitkeep").touch()
    
    print("\n[3/3] 创建 ZIP 包...")
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    create_zip(pack_dir, OUTPUT_ZIP)
    
    # 清理临时目录
    shutil.rmtree(pack_dir)
    
    print("\n" + "=" * 50)
    print("打包完成！")
    print(f"输出文件: {OUTPUT_ZIP}")
    print("\n上传命令:")
    print(f"  scp -P 46898 {OUTPUT_ZIP} root@connect.cqa1.seetacloud.com:~/")
    print("=" * 50)

if __name__ == "__main__":
    main()
