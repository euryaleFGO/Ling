#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信应用机器人测试脚本
"""

import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()


def test_health_check(base_url: str = "http://localhost:8080"):
    """测试健康检查接口"""
    print("🔍 测试健康检查接口...")
    
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康检查通过:")
            print(f"   状态: {data.get('status')}")
            print(f"   Bot ID: {data.get('bot_id')}")
            print(f"   活跃用户: {data.get('active_users')}")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False


def test_webhook_verification(base_url: str = "http://localhost:8080"):
    """测试 Webhook URL 验证"""
    print("\n🔐 测试 Webhook URL 验证...")
    
    # 模拟企业微信的 URL 验证请求
    params = {
        'msg_signature': 'test_signature',
        'timestamp': str(int(time.time())),
        'nonce': 'test_nonce',
        'echostr': 'test_echo'
    }
    
    try:
        response = requests.get(f"{base_url}/webhook", params=params, timeout=5)
        print(f"   响应状态: {response.status_code}")
        print(f"   响应内容: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook 验证接口正常")
            return True
        else:
            print("⚠️  Webhook 验证可能需要正确的签名")
            return False
            
    except Exception as e:
        print(f"❌ Webhook 验证异常: {e}")
        return False


def test_message_handling(base_url: str = "http://localhost:8080"):
    """测试消息处理"""
    print("\n💬 测试消息处理...")
    
    # 模拟企业微信消息格式
    test_message = {
        "ToUserName": "test_bot",
        "FromUserName": "test_user",
        "CreateTime": int(time.time()),
        "MsgType": "text",
        "Content": "你好，这是一条测试消息",
        "MsgId": "123456789"
    }
    
    # 模拟签名参数
    params = {
        'msg_signature': 'test_signature',
        'timestamp': str(int(time.time())),
        'nonce': 'test_nonce'
    }
    
    try:
        response = requests.post(
            f"{base_url}/webhook",
            params=params,
            json=test_message,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"   响应状态: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 消息处理成功: {data}")
            return True
        else:
            print(f"❌ 消息处理失败: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 消息处理异常: {e}")
        return False


def show_config_info():
    """显示配置信息"""
    print("\n📋 当前配置信息:")
    
    bot_id = os.getenv("WEWORK_BOT_ID", "未设置")
    secret = os.getenv("WEWORK_SECRET", "未设置")
    token = os.getenv("WEWORK_TOKEN", "未设置")
    
    print(f"   Bot ID: {bot_id}")
    print(f"   Secret: {'已设置' if secret != '未设置' else '未设置'}")
    print(f"   Token: {token}")
    
    if bot_id == "未设置" or secret == "未设置":
        print("\n⚠️  配置不完整，请在 .env 文件中设置:")
        print("   WEWORK_BOT_ID=你的机器人ID")
        print("   WEWORK_SECRET=你的机器人Secret")
        print("   WEWORK_TOKEN=回调验证Token")


def main():
    print("=" * 60)
    print("        企业微信应用机器人测试")
    print("=" * 60)
    
    base_url = "http://localhost:8080"
    
    # 显示配置信息
    show_config_info()
    
    # 测试健康检查
    health_ok = test_health_check(base_url)
    
    if not health_ok:
        print("\n❌ 服务未启动或不可用，请先启动机器人服务")
        print("   启动命令: python scripts/start_wework_app_bot.py")
        return
    
    # 测试 Webhook 验证
    test_webhook_verification(base_url)
    
    # 测试消息处理
    test_message_handling(base_url)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("\n📝 下一步:")
    print("1. 在企业微信管理后台配置回调 URL")
    print(f"   URL: http://你的服务器IP:8080/webhook")
    print("2. 设置正确的 Token 和 EncodingAESKey")
    print("3. 测试实际的企业微信消息")
    print("=" * 60)


if __name__ == "__main__":
    main()