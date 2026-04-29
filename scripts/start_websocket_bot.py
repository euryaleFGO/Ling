#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 聊天机器人启动脚本
"""

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from integrations.websocket_bot import WebSocketChatBot


def main():
    print("=" * 60)
    print("        WebSocket 聊天机器人 - 玲 (Liying)")
    print("=" * 60)
    
    # 从环境变量获取配置
    host = os.getenv("WEBSOCKET_HOST", "localhost")
    port = int(os.getenv("WEBSOCKET_PORT", "8765"))
    
    print(f"服务器地址: ws://{host}:{port}")
    print("支持功能:")
    print("  ✅ 实时长连接对话")
    print("  ✅ 流式回复显示")
    print("  ✅ 多用户并发")
    print("  ✅ 上下文记忆")
    print("  ✅ 工具调用支持")
    print()
    print("客户端连接示例:")
    print(f"  JavaScript: new WebSocket('ws://{host}:{port}')")
    print(f"  Python: websockets.connect('ws://{host}:{port}')")
    print()
    
    # 创建并启动机器人
    try:
        bot = WebSocketChatBot()
        bot.run(host=host, port=port)
    except KeyboardInterrupt:
        print("\n用户中断，正在关闭服务器...")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()