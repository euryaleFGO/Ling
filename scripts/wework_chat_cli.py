#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人 - 命令行聊天版
无需 Webhook，直接通过命令行与用户对话
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

from integrations.wework_simple_bot import WeWorkSimpleBot
from backend.llm.agent.agent import Agent


def main():
    print("=" * 60)
    print("        企业微信机器人 - 命令行聊天版")
    print("=" * 60)
    
    # 从环境变量获取配置
    corp_id = os.getenv("WEWORK_CORP_ID")
    corp_secret = os.getenv("WEWORK_CORP_SECRET")
    agent_id = os.getenv("WEWORK_AGENT_ID", "1000002")
    
    if not corp_id or not corp_secret:
        print("❌ 错误: 缺少配置")
        print("请在 .env 文件中设置:")
        print("  WEWORK_CORP_ID=你的企业ID")
        print("  WEWORK_CORP_SECRET=你的应用密钥")
        return
    
    print(f"✅ 企业 ID: {corp_id}")
    print(f"✅ 应用 ID: {agent_id}")
    print()
    
    # 创建机器人
    bot = WeWorkSimpleBot(corp_id, corp_secret, agent_id)
    
    # 创建 Agent
    agent = Agent(user_id="wework_cli_user", enable_tools=True)
    agent.start_chat()
    
    print("🤖 企业微信机器人已启动")
    print("📝 使用方式:")
    print("   1. 输入企业微信用户 ID")
    print("   2. 输入要发送的消息")
    print("   3. AI 会生成回复并发送给该用户")
    print()
    print("输入 'quit' 退出")
    print("=" * 60)
    print()
    
    try:
        while True:
            # 获取用户 ID
            user_id = input("👤 企业微信用户 ID: ").strip()
            
            if user_id.lower() in ['quit', 'exit', '退出']:
                break
            
            if not user_id:
                continue
            
            # 获取消息内容
            message = input("💬 消息内容: ").strip()
            
            if not message:
                continue
            
            if message.lower() in ['quit', 'exit', '退出']:
                break
            
            print("\n🤔 AI 正在思考...")
            
            # 生成回复
            try:
                response = agent.chat_sync(message)
                print(f"🤖 AI 回复: {response}\n")
                
                # 发送到企业微信
                print(f"📤 发送给用户 {user_id}...")
                success = bot.send_message(user_id, response)
                
                if success:
                    print("✅ 发送成功！\n")
                else:
                    print("❌ 发送失败，请检查用户 ID 和网络连接\n")
                    
            except Exception as e:
                print(f"❌ 错误: {e}\n")
            
            print("-" * 60)
            print()
    
    except KeyboardInterrupt:
        print("\n\n用户中断")
    finally:
        agent.end_chat()
        print("\n对话结束")


if __name__ == "__main__":
    main()