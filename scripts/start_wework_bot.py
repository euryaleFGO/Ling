#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人启动脚本
"""

import os
import sys
import json
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from integrations.wework_bot import WeWorkBot


def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    if config_path is None:
        config_path = project_root / "config" / "wework_bot.json"
    
    if not Path(config_path).exists():
        print(f"配置文件不存在: {config_path}")
        print("请复制 config/wework_bot.example.json 为 config/wework_bot.json 并修改配置")
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("=" * 60)
    print("        企业微信机器人 - 玲 (Liying)")
    print("=" * 60)
    
    # 加载配置
    config = load_config()
    
    # 从环境变量或配置文件获取参数
    webhook_key = os.getenv("WEWORK_WEBHOOK_KEY") or config.get("webhook_key", "")
    host = os.getenv("WEWORK_HOST") or config.get("server", {}).get("host", "0.0.0.0")
    port = int(os.getenv("WEWORK_PORT") or config.get("server", {}).get("port", 8080))
    debug = os.getenv("WEWORK_DEBUG", "false").lower() == "true" or config.get("server", {}).get("debug", False)
    
    if not webhook_key:
        print("⚠️  警告: 未配置 WEWORK_WEBHOOK_KEY，将跳过签名验证")
        print("   建议在 .env 文件中添加: WEWORK_WEBHOOK_KEY=your_key")
    
    print(f"服务器地址: http://{host}:{port}")
    print(f"Webhook 地址: http://{host}:{port}/webhook")
    print(f"健康检查: http://{host}:{port}/health")
    print(f"调试模式: {'开启' if debug else '关闭'}")
    print()
    
    # 创建并启动机器人
    try:
        bot = WeWorkBot(webhook_key=webhook_key)
        bot.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        print("\n用户中断，正在关闭服务器...")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()