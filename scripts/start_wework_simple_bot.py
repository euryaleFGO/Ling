#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人启动脚本 - 简化版
无需复杂的 token 验证，直接使用企业 ID 和应用密钥
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

from integrations.wework_simple_bot import create_flask_app


def main():
    print("=" * 60)
    print("        企业微信机器人 - 玲 (Liying)")
    print("        简化版 - 无需复杂配置")
    print("=" * 60)
    
    # 从环境变量获取配置
    corp_id = os.getenv("WEWORK_CORP_ID")
    corp_secret = os.getenv("WEWORK_CORP_SECRET")
    agent_id = os.getenv("WEWORK_AGENT_ID", "1000002")
    host = os.getenv("WEWORK_HOST", "0.0.0.0")
    port = int(os.getenv("WEWORK_PORT", "8080"))
    
    # 检查必需配置
    if not corp_id or not corp_secret:
        print("❌ 错误: 缺少必需的配置")
        print()
        print("请在 .env 文件中设置:")
        print("  WEWORK_CORP_ID=你的企业ID")
        print("  WEWORK_CORP_SECRET=你的应用密钥")
        print()
        print("当前配置:")
        print(f"  WEWORK_CORP_ID: {'已设置' if corp_id else '未设置'}")
        print(f"  WEWORK_CORP_SECRET: {'已设置' if corp_secret else '未设置'}")
        return
    
    print("✅ 配置信息:")
    print(f"   企业 ID: {corp_id}")
    print(f"   应用 ID: {agent_id}")
    print(f"   应用密钥: {'已设置' if corp_secret else '未设置'}")
    print()
    
    print("🌐 服务信息:")
    print(f"   服务器地址: http://{host}:{port}")
    print(f"   Webhook 地址: http://{host}:{port}/webhook")
    print(f"   健康检查: http://{host}:{port}/health")
    print(f"   测试发送: http://{host}:{port}/send")
    print()
    
    print("📝 企业微信配置:")
    print("   1. 进入企业微信管理后台")
    print("   2. 找到你的应用设置")
    print("   3. 在「接收消息」中设置:")
    print(f"      URL: http://你的服务器IP:{port}/webhook")
    print("   4. 保存配置并测试")
    print()
    
    # 创建并启动应用
    try:
        app, bot = create_flask_app(corp_id, corp_secret, agent_id)
        
        print("🚀 启动企业微信机器人...")
        print("   等待企业微信消息...")
        print()
        
        app.run(host=host, port=port, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        print("\n用户中断，正在关闭服务器...")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()