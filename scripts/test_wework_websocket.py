#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人 WebSocket 测试脚本
用于验证配置和连接
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()


def check_config():
    """检查配置"""
    print("=" * 60)
    print("企业微信机器人 WebSocket 配置检查")
    print("=" * 60)
    print()
    
    # 检查必需配置
    bot_id = os.getenv("WEWORK_BOT_ID", "")
    secret = os.getenv("WEWORK_SECRET", "")
    ws_url = os.getenv("WEWORK_WS_URL", "wss://openws.work.weixin.qq.com")
    
    issues = []
    
    print("📋 配置检查:")
    print()
    
    # Bot ID
    if bot_id:
        print(f"  ✅ WEWORK_BOT_ID: {bot_id}")
    else:
        print(f"  ❌ WEWORK_BOT_ID: 未配置")
        issues.append("WEWORK_BOT_ID 未配置")
    
    # Secret
    if secret:
        masked_secret = '*' * 8 + secret[-4:] if len(secret) > 4 else '****'
        print(f"  ✅ WEWORK_SECRET: {masked_secret}")
    else:
        print(f"  ❌ WEWORK_SECRET: 未配置")
        issues.append("WEWORK_SECRET 未配置")
    
    # WebSocket URL
    print(f"  ✅ WEWORK_WS_URL: {ws_url}")
    
    print()
    
    if issues:
        print("❌ 配置检查失败:")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("请在 .env 文件中配置以下环境变量:")
        print("  WEWORK_BOT_ID=your_bot_id")
        print("  WEWORK_SECRET=your_secret")
        print()
        return False
    else:
        print("✅ 配置检查通过")
        print()
        return True


def check_dependencies():
    """检查依赖"""
    print("=" * 60)
    print("依赖检查")
    print("=" * 60)
    print()
    
    dependencies = [
        ("websockets", "WebSocket 客户端"),
        ("dotenv", "环境变量加载"),
    ]
    
    issues = []
    
    for module_name, description in dependencies:
        try:
            __import__(module_name)
            print(f"  ✅ {module_name}: {description}")
        except ImportError:
            print(f"  ❌ {module_name}: {description} - 未安装")
            issues.append(module_name)
    
    print()
    
    if issues:
        print("❌ 依赖检查失败:")
        for module in issues:
            print(f"  - {module}")
        print()
        print("请安装缺失的依赖:")
        print(f"  pip install {' '.join(issues)}")
        print()
        return False
    else:
        print("✅ 依赖检查通过")
        print()
        return True


async def test_connection():
    """测试连接"""
    print("=" * 60)
    print("连接测试")
    print("=" * 60)
    print()
    
    try:
        from integrations.wework_bot_websocket import WeWorkBotWebSocket, WeWorkConfig
        
        # 创建配置
        config = WeWorkConfig(
            bot_id=os.getenv("WEWORK_BOT_ID"),
            secret=os.getenv("WEWORK_SECRET")
        )
        
        # 创建机器人
        bot = WeWorkBotWebSocket(config)
        
        print("正在连接到企业微信 WebSocket...")
        print()
        
        # 尝试连接（5 秒超时）
        try:
            await asyncio.wait_for(bot.connect(), timeout=5.0)
            print("✅ 连接成功！")
            print()
            
            # 断开连接
            await bot.disconnect()
            
            return True
            
        except asyncio.TimeoutError:
            print("❌ 连接超时")
            print()
            print("可能的原因:")
            print("  1. 网络连接问题")
            print("  2. Bot ID 或 Secret 错误")
            print("  3. 企业微信服务不可用")
            print()
            return False
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print()
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print()
    print("🤖 企业微信机器人 WebSocket 测试工具")
    print()
    
    # 1. 检查配置
    if not check_config():
        sys.exit(1)
    
    # 2. 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 3. 测试连接
    print("是否要测试连接？(y/n): ", end="")
    choice = input().strip().lower()
    
    if choice == 'y':
        print()
        success = asyncio.run(test_connection())
        
        if success:
            print("=" * 60)
            print("✅ 所有测试通过！")
            print("=" * 60)
            print()
            print("你可以使用以下命令启动机器人:")
            print("  python scripts/start_wework_bot_websocket.py")
            print()
            print("或使用批处理文件（Windows）:")
            print("  启动企业微信机器人WebSocket.bat")
            print()
        else:
            print("=" * 60)
            print("❌ 连接测试失败")
            print("=" * 60)
            print()
            print("请检查:")
            print("  1. Bot ID 和 Secret 是否正确")
            print("  2. 网络连接是否正常")
            print("  3. 企业微信机器人是否已启用")
            print()
            sys.exit(1)
    else:
        print()
        print("=" * 60)
        print("✅ 配置和依赖检查通过！")
        print("=" * 60)
        print()
        print("跳过连接测试。")
        print()
        print("你可以使用以下命令启动机器人:")
        print("  python scripts/start_wework_bot_websocket.py")
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)
