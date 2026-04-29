#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人 WebSocket 长连接启动脚本
"""

import os
import sys
import json
import time
import subprocess
import platform
from pathlib import Path

print("=" * 60)
print("🔍 启动脚本开始执行...")
print("=" * 60)

# 添加项目路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

print(f"✅ 项目路径: {project_root}")
print(f"✅ 源码路径: {src_path}")

# 加载环境变量
print("📄 正在加载环境变量...")
from dotenv import load_dotenv
load_dotenv()
print("✅ 环境变量加载完成")

print("=" * 60)
print()

print("📦 正在导入机器人模块...")
from integrations.wework_bot_websocket import WeWorkBotWebSocket, WeWorkConfig
print("✅ 模块导入成功")
print()


def is_mongodb_running():
    """检查 MongoDB 是否在运行"""
    if platform.system() != "Windows":
        # Linux/Mac: 检查进程
        try:
            result = subprocess.run(
                ["pgrep", "-x", "mongod"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    else:
        # Windows: 检查进程
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mongod.exe"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return "mongod.exe" in result.stdout
        except:
            return False


def start_mongodb():
    """启动 MongoDB"""
    if platform.system() != "Windows":
        print("⚠️  非 Windows 系统，请手动启动 MongoDB")
        return False
    
    # 检查环境变量
    mongod_exe = os.getenv("MONGOD_EXE", "").strip()
    mongod_cfg = os.getenv("MONGOD_CFG", "").strip()
    
    if not mongod_exe:
        print("⚠️  未设置 MONGOD_EXE 环境变量")
        print("   请在 .env 文件中设置:")
        print("   MONGOD_EXE=E:\\MongoDB\\bin\\mongod.exe")
        return False
    
    if not Path(mongod_exe).exists():
        print(f"❌ MongoDB 可执行文件不存在: {mongod_exe}")
        return False
    
    print(f"正在启动 MongoDB: {mongod_exe}")
    
    try:
        # 构建启动命令
        cmd = [mongod_exe]
        if mongod_cfg and Path(mongod_cfg).exists():
            cmd.extend(["--config", mongod_cfg])
            print(f"使用配置文件: {mongod_cfg}")
        
        # 启动 MongoDB（后台运行）
        if platform.system() == "Windows":
            # Windows: 使用 CREATE_NEW_CONSOLE 标志
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        # 等待 MongoDB 启动
        print("等待 MongoDB 启动...")
        for i in range(10):
            time.sleep(1)
            if is_mongodb_running():
                print("✅ MongoDB 启动成功")
                return True
        
        print("⚠️  MongoDB 启动超时，但可能仍在启动中")
        return True
        
    except Exception as e:
        print(f"❌ 启动 MongoDB 失败: {e}")
        return False


def ensure_mongodb():
    """确保 MongoDB 正在运行"""
    print("检查 MongoDB 状态...")
    
    if is_mongodb_running():
        print("✅ MongoDB 已在运行")
        return True
    
    print("⚠️  MongoDB 未运行")
    print()
    
    # 尝试启动 MongoDB
    if start_mongodb():
        return True
    
    # 启动失败，提示用户
    print()
    print("=" * 60)
    print("❌ MongoDB 未运行且无法自动启动")
    print("=" * 60)
    print()
    print("请手动启动 MongoDB，或者:")
    print()
    print("1. 如果已安装 MongoDB 服务:")
    print("   net start MongoDB")
    print()
    print("2. 如果未安装服务，手动启动:")
    print("   E:\\MongoDB\\bin\\mongod.exe --config E:\\MongoDB\\mongod.cfg")
    print()
    print("3. 或在 .env 文件中配置:")
    print("   MONGOD_EXE=E:\\MongoDB\\bin\\mongod.exe")
    print("   MONGOD_CFG=E:\\MongoDB\\mongod.cfg")
    print()
    
    return False


def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    if config_path is None:
        config_path = project_root / "config" / "wework_bot_websocket.json"
    
    if not Path(config_path).exists():
        print(f"⚠️  配置文件不存在: {config_path}")
        print("   将使用环境变量配置")
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("=" * 60)
    print("   企业微信机器人 WebSocket 长连接版本 - 玲 (Liying)")
    print("=" * 60)
    print()
    
    # 1. 确保 MongoDB 运行
    if not ensure_mongodb():
        print("按任意键退出...")
        input()
        sys.exit(1)
    
    print()
    print("=" * 60)
    print()
    
    # 2. 加载配置
    config_data = load_config()
    
    # 从环境变量或配置文件获取参数
    bot_id = os.getenv("WEWORK_BOT_ID") or config_data.get("bot_id", "")
    secret = os.getenv("WEWORK_SECRET") or config_data.get("secret", "")
    ws_url = os.getenv("WEWORK_WS_URL") or config_data.get("ws_url", "wss://openws.work.weixin.qq.com")
    
    if not bot_id or not secret:
        print("❌ 错误: 缺少必要配置")
        print()
        print("请设置以下环境变量（在 .env 文件中）：")
        print("  WEWORK_BOT_ID=<你的机器人ID>")
        print("  WEWORK_SECRET=<你的长连接密钥>")
        print()
        print("或创建配置文件: config/wework_bot_websocket.json")
        print("参考: config/wework_bot_websocket.example.json")
        print()
        return
    
    print("✅ 配置信息:")
    print(f"   Bot ID: {bot_id}")
    print(f"   Secret: {'*' * 8}{secret[-4:] if len(secret) > 4 else '****'}")
    print(f"   WebSocket URL: {ws_url}")
    print()
    
    # 创建配置对象
    config = WeWorkConfig(
        bot_id=bot_id,
        secret=secret,
        ws_url=ws_url,
        heartbeat_interval=config_data.get("heartbeat_interval", 30),
        reconnect_delay=config_data.get("reconnect_delay", 5),
        max_reconnect_attempts=config_data.get("max_reconnect_attempts", 10)
    )
    
    print("🚀 正在启动企业微信机器人...")
    print("   支持功能:")
    print("   • 流式消息回复")
    print("   • 主动推送消息")
    print("   • 自动重连")
    print("   • 无需公网 IP")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    print()
    
    # 创建并启动机器人
    try:
        print("🔧 正在创建机器人实例...")
        bot = WeWorkBotWebSocket(config)
        print("✅ 机器人实例创建成功")
        
        print("🚀 正在启动机器人...")
        bot.run()
    except KeyboardInterrupt:
        print("\n\n用户中断，正在关闭服务...")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
