"""
日志监控脚本
在单独的终端运行，实时查看 Agent 运行日志

用法：
    python -m LLM.log_monitor
    
或者：
    python log_monitor.py
"""
import sys
import time
from pathlib import Path
from datetime import datetime

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent / "logs"


def get_latest_log_file():
    """获取最新的日志文件"""
    log_files = list(LOG_DIR.glob("agent_*.log"))
    if not log_files:
        return None
    return max(log_files, key=lambda f: f.stat().st_mtime)


def tail_file(filepath, lines=20):
    """读取文件最后 N 行"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()[-lines:]
    except (OSError, IOError):
        return []


def monitor():
    """实时监控日志"""
    print("=" * 60)
    print("  🔍 玲 - Agent 日志监控")
    print("=" * 60)
    print(f"  日志目录: {LOG_DIR}")
    print("  按 Ctrl+C 退出")
    print("=" * 60)
    print()
    
    # 确保日志目录存在
    LOG_DIR.mkdir(exist_ok=True)
    
    last_position = 0
    last_file = None
    
    while True:
        try:
            # 获取最新日志文件
            log_file = get_latest_log_file()
            
            if not log_file:
                print(f"\r⏳ 等待日志文件... ({datetime.now().strftime('%H:%M:%S')})", end="", flush=True)
                time.sleep(1)
                continue
            
            # 如果是新文件，重置位置
            if log_file != last_file:
                last_file = log_file
                last_position = 0
                print(f"\n📂 监控文件: {log_file.name}\n")
            
            # 读取新内容
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(last_position)
                new_content = f.read()
                last_position = f.tell()
            
            # 输出新内容（带颜色）
            if new_content:
                for line in new_content.splitlines():
                    print(colorize(line))
            
            time.sleep(0.3)  # 300ms 刷新
            
        except KeyboardInterrupt:
            print("\n\n👋 停止监控")
            break
        except Exception as e:
            print(f"\n❌ 监控错误: {e}")
            time.sleep(1)


def colorize(line: str) -> str:
    """给日志行添加颜色（仅在支持 ANSI 的终端）"""
    # Windows 终端颜色支持
    try:
        import os
        os.system('')  # 启用 ANSI 支持
    except (AttributeError, OSError):
        pass

    # 颜色代码
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    
    if "ERROR" in line or "❌" in line:
        return f"{RED}{line}{RESET}"
    elif "WARNING" in line:
        return f"{YELLOW}{line}{RESET}"
    elif "🔧" in line or "调用工具" in line:
        return f"{CYAN}{line}{RESET}"
    elif "📤" in line or "📥" in line:
        return f"{BLUE}{line}{RESET}"
    elif "INFO" in line:
        return f"{GREEN}{line}{RESET}"
    elif "DEBUG" in line:
        return f"{GRAY}{line}{RESET}"
    
    return line


if __name__ == "__main__":
    monitor()
