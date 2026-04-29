#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信应用机器人启动脚本
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

from integrations.wework_app_bot import create_flask_app


def main():
    print("=" * 60)
    print("        企业微信应用机器人 - 玲 (Liying)")
    print("=" * 60)
    
    # 从环境变量获取配置
    bot_id = os.getenv("WEWORK_BOT_ID")
    secret = os.getenv("WEWORK_SECRET")
    token = os.getenv("WEWORK_TOKEN", "default_token")
    encoding_aes_key = os.getenv("WEWORK_ENCODING_AES_KEY")
    host = os.getenv("WEWORK_HOST", "0.0.0.0")
    port = int(os.getenv("WEWORK_PORT", "8080"))
    debug = os.getenv("WEWORK_DEBUG", "false").lower() == "true"
    
    # 检查必需配置
    if not bot_id or not secret:
        print("❌ 错误: 缺少必需的配置")
        print("请在 .env 文件中设置:")
        print("  WEWORK_BOT_ID=你的机器人ID")
        print("  WEWORK_SECRET=你的机器人Secret")
        print("  WEWORK_TOKEN=回调验证Token")
        return
    
    print(f"Bot ID: {bot_id}")
    print(f"服务器地址: http://{host}:{port}")
    print(f"Webhook 地址: http://{host}:{port}/webhook")
    print(f"健康检查: http://{host}:{port}/health")
    print(f"调试模式: {'开启' if debug else '关闭'}")
    print()
    
    if not token or token == "default_token":
        print("⚠️  警告: 使用默认 Token，建议设置 WEWORK_TOKEN")
    
    print("配置企业微信回调 URL:")
    print(f"  URL: http://{host}:{port}/webhook")
    print(f"  Token: {token}")
    if encoding_aes_key:
        print(f"  EncodingAESKey: {encoding_aes_key}")
    print()
    
    # 创建并启动应用
    try:
        app, bot = create_flask_app(bot_id, secret, token, encoding_aes_key)
        
        print("🚀 启动企业微信应用机器人...")
        app.run(host=host, port=port, debug=debug, threaded=True)
        
    except KeyboardInterrupt:
        print("\n用户中断，正在关闭服务器...")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()