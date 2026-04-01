#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
玲 (Liying) 一键部署脚本
自动检测未安装的依赖，询问安装路径，并执行安装。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


# 项目根目录（脚本在 scripts/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"


def run_cmd(cmd: list[str], cwd: Path | None = None, capture: bool = True) -> tuple[int, str]:
    """执行命令，返回 (returncode, stdout+stderr)"""
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return -1, "（超时）"
    except FileNotFoundError:
        return -1, "（命令不存在）"
    except Exception as e:
        return -1, str(e)


def get_python_exe() -> Path | None:
    """当前 Python 解释器路径"""
    exe = Path(sys.executable)
    return exe if exe.exists() else None


def get_requirements_specs() -> list[tuple[str, str]]:
    """解析 requirements.txt，返回 [(包名, 版本约束), ...]，跳过注释和空行。"""
    if not REQUIREMENTS_FILE.exists():
        return []
    specs = []
    for line in REQUIREMENTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 简单解析：包名==版本 或 包名>=版本 等
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*([=<>!~].*)?$", line.split("#")[0].strip())
        if match:
            name = match.group(1)
            specs.append((name, match.group(2) or ""))
    return specs


def check_pip_packages(specs: list[tuple[str, str]]) -> list[str]:
    """检查哪些包未安装或版本不符，返回未满足的 requirements 行（用于 pip install -r）。"""
    if not specs:
        return []
    missing = []
    code, out = run_cmd([sys.executable, "-m", "pip", "list", "--format=freeze"])
    if code != 0:
        return [f"{n}{v}".strip() for n, v in specs]
    installed = {}
    for line in out.splitlines():
        if "==" in line:
            p, v = line.split("==", 1)
            installed[p.lower()] = v.strip()
    for name, ver in specs:
        key = name.lower().replace("_", "-")
        key2 = name.lower()
        if key not in installed and key2 not in installed:
            missing.append(f"{name}{ver}".strip())
    return missing


def check_java() -> tuple[bool, str]:
    """检查 Java 是否可用，返回 (是否OK, 版本信息或错误)。"""
    code, out = run_cmd(["java", "-version"])
    if code != 0:
        return False, "未找到 Java 或无法执行"
    for line in out.splitlines():
        if "version" in line.lower():
            return True, line.strip()
    return True, out[:200] if out else "已安装"


def check_maven() -> tuple[bool, str]:
    """检查 Maven 是否可用。"""
    code, out = run_cmd(["mvn", "-v"])
    if code != 0:
        return False, "未找到 Maven 或无法执行"
    first = out.split("\n")[0] if out else ""
    return True, first.strip()


def prompt_path(prompt: str, default: str) -> Path:
    """询问用户输入路径，支持默认值。"""
    print(prompt)
    print(f"  默认: {default}")
    raw = input("  请输入路径（直接回车使用默认）: ").strip()
    if not raw:
        return Path(default)
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def main() -> None:
    print("=" * 60)
    print("        玲 (Liying) 一键部署")
    print("=" * 60)
    print()

    py_exe = get_python_exe()
    if not py_exe:
        print("[错误] 无法获取当前 Python 解释器路径。")
        sys.exit(1)
    print(f"[Python] {py_exe}")
    print(f"  版本: {sys.version.split()[0]}")
    print()

    # 1) 解析并检查 pip 依赖
    specs = get_requirements_specs()
    if not specs:
        print("[提示] 未找到 requirements.txt 或为空，跳过 pip 依赖检查。")
        missing_pip = []
    else:
        missing_pip = check_pip_packages(specs)
        if not missing_pip:
            print("[OK] 当前环境已满足 requirements.txt 中的依赖。")
        else:
            print(f"[待安装] 以下依赖未安装或版本不符（共 {len(missing_pip)} 项）：")
            for s in missing_pip[:20]:
                print(f"  - {s}")
            if len(missing_pip) > 20:
                print(f"  ... 及其他 {len(missing_pip) - 20} 项")
    print()

    # 2) Java / Maven（Live2D 需要）
    java_ok, java_msg = check_java()
    maven_ok, maven_msg = check_maven()
    if java_ok:
        print("[OK] Java:", java_msg)
    else:
        print("[待安装] Java:", java_msg)
    if maven_ok:
        print("[OK] Maven:", maven_msg)
    else:
        print("[待安装] Maven:", maven_msg)
    print()

    # 3) 询问安装路径
    default_install = PROJECT_ROOT / "venv"
    install_path = prompt_path(
        "请选择「安装路径」：将在此处创建/使用 Python 虚拟环境并安装依赖。",
        str(default_install),
    )
    print(f"  使用路径: {install_path}")
    print()

    # 4) 处理 pip 安装
    if missing_pip:
        use_venv = input("是否在以上路径创建/使用虚拟环境并安装依赖？[Y/n]: ").strip().lower()
        if use_venv != "n":
            venv_dir = install_path
            if not (venv_dir / "Scripts" / "python.exe").exists() and not (venv_dir / "bin" / "python").exists():
                print(f"正在创建虚拟环境: {venv_dir}")
                code, out = run_cmd([str(py_exe), "-m", "venv", str(venv_dir)], capture=False)
                if code != 0:
                    print("[错误] 创建虚拟环境失败:", out)
                else:
                    print("[OK] 虚拟环境已创建。")
            if sys.platform == "win32":
                pip_python = venv_dir / "Scripts" / "python.exe"
            else:
                pip_python = venv_dir / "bin" / "python"
            if pip_python.exists():
                print("正在安装 requirements.txt 中的依赖（可能较久）...")
                code, out = run_cmd(
                    [str(pip_python), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE), "-q"],
                    capture=False,
                )
                if code != 0:
                    print("[警告] 部分依赖安装失败，请检查上方输出。")
                    print("  若为 PyTorch/CUDA 相关，可先运行 scripts/install_dependencies.bat 或按 README 安装。")
                else:
                    print("[OK] 依赖安装完成。")
                print()
                print("激活虚拟环境后运行项目：")
                if sys.platform == "win32":
                    print(f"  {venv_dir}\\Scripts\\activate")
                else:
                    print(f"  source {venv_dir}/bin/activate")
                print("  python main.py")
            else:
                print("[跳过] 未找到虚拟环境中的 Python，请手动创建后重新运行本脚本。")
        else:
            print("正在当前环境安装 requirements.txt...")
            code, out = run_cmd(
                [str(py_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE), "-q"],
                capture=False,
            )
            if code != 0:
                print("[警告] 部分依赖安装失败。")
            else:
                print("[OK] 依赖安装完成。")
    else:
        print("无需安装 pip 依赖。")
    print()

    # 5) Java/Maven 未安装时的说明
    if not java_ok or not maven_ok:
        print("--- Live2D 前端（Java）---")
        if not java_ok:
            print("  Java 17 下载: https://adoptium.net/ 或 https://www.oracle.com/java/technologies/downloads/")
            print("  安装后请将 java 加入 PATH。")
        if not maven_ok:
            print("  Maven 下载: https://maven.apache.org/download.cgi")
            print("  解压到任意目录，并将 bin 加入 PATH。")
        print("  若仅使用 Python 对话（不启动 Live2D），可暂不安装。")
    print()
    print("=" * 60)
    print("部署检查结束。请根据上方提示完成未安装项。")
    print("=" * 60)


if __name__ == "__main__":
    main()
