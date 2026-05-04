#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人测试脚本 - 简化版
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
            print(f"   企业 ID: {data.get('corp_id')}")
            print(f"   应用 ID: {data.get('agent_id')}")
            print(f"   活跃用户: {data.get('active_users')}")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False


def test_webhook_url(base_url: str = "http://localhost:8080"):
    """测试 Webhook URL 可访问性"""
    print("\n🔗 测试 Webhook URL...")
    
    try:
        # 模拟企业微信的 URL 验证（GET 请求）
        response = requests.get(f"{base_url}/webhook?echostr=test123", timeout=5)
        
        if response.status_code == 200:
            print(f"✅ Webhook URL 可访问")
            print(f"   响应内容: {response.text}")
            return True
        else:
            print(f"❌ Webhook URL 访问失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Webhook URL 测试异常: {e}")
        return False


def test_send_message(base_url: str = "http://localhost:8080"):
    """测试发送消息接口"""
    print("\n📤 测试发送消息接口...")
    
    test_data = {
        "user_id": "test_user",
        "content": "这是一条测试消息"
    }
    
    try:
        response = requests.post(
            f"{base_url}/send",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ 消息发送接口正常")
                print(f"   响应: {data.get('message')}")
            else:
                print(f"⚠️  消息发送失败: {data.get('message')}")
            return True
        else:
            print(f"❌ 发送消息失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 发送消息异常: {e}")
        return False


def test_webhook_message(base_url: str = "http://localhost:8080"):
    """测试 Webhook 消息处理"""
    print("\n💬 测试 Webhook 消息处理...")
    
    # 模拟企业微信 XML 消息
    xml_message = """<?xml version="1.0" encoding="UTF-8"?>
<xml>
    <ToUserName><![CDATA[test_bot]]></ToUserName>
    <FromUserName><![CDATA[test_user]]></FromUserName>
    <CreateTime>1640995200</CreateTime>
    <MsgType><![CDATA[text]]></MsgType>
    <Content><![CDATA[你好，这是一条测试消息]]></Content>
    <MsgId>123456789</MsgId>
    <AgentID>1000002</AgentID>
</xml>"""
    
    try:
        response = requests.post(
            f"{base_url}/webhook",
            data=xml_message,
            headers={"Content-Type": "application/xml"},
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"✅ Webhook 消息处理正常")
            try:
                data = response.json()
                print(f"   响应: {data}")
            except ValueError:
                print(f"   响应: {response.text}")
            return True
        else:
            print(f"❌ Webhook 消息处理失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Webhook 消息处理异常: {e}")
        return False


def show_config_info():
    """显示配置信息"""
    print("\n📋 当前配置信息:")
    
    corp_id = os.getenv("WEWORK_CORP_ID", "未设置")
    corp_secret = os.getenv("WEWORK_CORP_SECRET", "未设置")
    agent_id = os.getenv("WEWORK_AGENT_ID", "1000002")
    
    print(f"   企业 ID: {corp_id}")
    print(f"   应用密钥: {'已设置' if corp_secret != '未设置' else '未设置'}")
    print(f"   应用 ID: {agent_id}")
    
    if corp_id == "未设置" or corp_secret == "未设置":
        print("\n⚠️  配置不完整，请在 .env 文件中设置:")
        print("   WEWORK_CORP_ID=你的企业ID")
        print("   WEWORK_CORP_SECRET=你的应用密钥")


def show_next_steps():
    """显示后续步骤"""
    print("\n📝 后续步骤:")
    print("1. 确保服务器可以从外网访问")
    print("2. 在企业微信管理后台配置:")
    print("   - 进入你的应用设置")
    print("   - 找到「接收消息」配置")
    print("   - 设置 URL: http://你的服务器IP:8080/webhook")
    print("   - 保存配置")
    print("3. 在企业微信中找到应用并发送消息测试")
    print("4. 查看服务器日志确认消息处理情况")


def main():
    print("=" * 60)
    print("        企业微信机器人测试 - 简化版")
    print("=" * 60)
    
    base_url = "http://localhost:8080"
    
    # 显示配置信息
    show_config_info()
    
    # 测试健康检查
    health_ok = test_health_check(base_url)
    
    if not health_ok:
        print("\n❌ 服务未启动或不可用，请先启动机器人服务")
        print("   启动命令: python scripts/start_wework_simple_bot.py")
        return
    
    # 测试各个接口
    test_webhook_url(base_url)
    test_send_message(base_url)
    test_webhook_message(base_url)
    
    print("\n" + "=" * 60)
    print("测试完成")
    
    # 显示后续步骤
    show_next_steps()
    
    print("=" * 60)


if __name__ == "__main__":
    main()