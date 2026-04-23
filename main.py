#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
玲 (Liying) - 智能虚拟助手系统
主入口文件

启动参数:
    --debug, -d     调试模式
    --no-voice      禁用语音对话（仅 GUI）
    --text          纯文本对话模式（控制台，无 GUI）
    --text-gui      文字输入模式（GUI + 终端文字对话，不使用麦克风）

使用示例:
    python main.py              # 完整模式（GUI + 语音对话）
    python main.py --debug      # 调试模式
    python main.py --no-voice   # 仅 GUI，不启动语音
    python main.py --text       # 纯文本对话（控制台）
    python main.py --text-gui   # GUI + 终端文字输入对话
"""
import sys
from pathlib import Path

# 添加 src 目录到路径
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# 加载 .env 文件（必须在最开始加载）
from dotenv import load_dotenv
load_dotenv()


def _parse_asr_device(argv) -> str:
    """
    解析 ASR 设备参数。

    支持:
    - --asr-device auto
    - --asr-device cpu
    - --asr-device cuda
    - --asr-device cuda:0
    - --asr-device=<value>
    """
    default = "auto"
    if "--asr-device" in argv:
        i = argv.index("--asr-device")
        if i + 1 < len(argv):
            return argv[i + 1].strip() or default
        return default
    for arg in argv:
        if arg.startswith("--asr-device="):
            v = arg.split("=", 1)[1].strip()
            return v or default
    return default


def main():
    # 解析参数
    debug_mode = "--debug" in sys.argv or "-d" in sys.argv
    no_voice = "--no-voice" in sys.argv
    text_mode = "--text" in sys.argv
    text_gui_mode = "--text-gui" in sys.argv
    asr_device = _parse_asr_device(sys.argv)
    
    print("=" * 60)
    print("        玲 (Liying) - 智能虚拟助手")
    print("=" * 60)
    
    if text_mode:
        # 纯文本模式（控制台对话）
        print("模式: 纯文本对话（控制台）")
        run_text_mode(debug_mode)
    else:
        # GUI 模式
        if text_gui_mode:
            print("模式: GUI + 终端文字输入对话")
        elif no_voice:
            print("模式: GUI（无对话）")
        else:
            print("模式: GUI + 语音对话")
        
        from core.launcher import Launcher
        launcher = Launcher(
            debug_mode=debug_mode,
            enable_conversation=(not no_voice or text_gui_mode),
            text_only=text_gui_mode,
            asr_device=asr_device,
        )
        launcher.app.exec()


def run_text_mode(debug_mode: bool):
    """纯文本对话模式"""
    from backend.llm.agent import Agent
    from backend.llm.database.knowledge_dao import get_knowledge_dao
    
    print("\n正在初始化...")
    agent = Agent(user_id="default_user")
    knowledge_dao = get_knowledge_dao()
    agent.start_chat()
    
    # 显示当前用户称呼
    profile = knowledge_dao.get_user_profile("default_user")
    current_name = profile.get("nickname", "用户") if profile else "用户"
    
    print("\n" + "-" * 40)
    print("对话已开始，输入 'quit' 退出")
    print(f"当前称呼: {current_name}")
    print("输入 /name <名字> 修改AI对你的称呼")
    print("-" * 40 + "\n")
    
    try:
        while True:
            try:
                user_input = input("👤 你: ").strip()
            except EOFError:
                break
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', '退出']:
                break
            
            # 处理 /name 命令
            if user_input.startswith('/name '):
                new_name = user_input[6:].strip()
                if new_name:
                    knowledge_dao.update_user_nickname(
                        user_id="default_user", user_name=new_name
                    )
                    print(f"✅ 称呼已修改为: {new_name}（下次对话生效）\n")
                else:
                    print("❗ 用法: /name <你的名字>\n")
                continue
            
            print("🤖 玲: ", end="", flush=True)

            try:
                for chunk in agent.chat(user_input, stream=True):
                    print(chunk, end="", flush=True)
            except Exception as e:
                # 网络波动或上游 API 异常时，不要让整个会话崩溃
                print(f"\n❗ 回复失败：{type(e).__name__}: {e}")
                print("请检查网络或 API 服务状态，然后重试。\n")
                continue
            
            print("\n")
            
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        agent.end_chat()
        print("\n对话结束")


if __name__ == "__main__":
    main()
