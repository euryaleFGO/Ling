#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人测试脚本
用于测试机器人功能是否正常
"""

import requests
import json
import time


def test_health_check(base_url: str = "http://localhost:8080"):
    """测试健康检查接口"""
    print("🔍 测试健康检查接口...")
    
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康检查通过: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False


def test_webhook_message(base_url: str = "http://localhost:8080"):
    """测试 Webhook 消息处理"""
    print("\n💬 测试 Webhook 消息处理...")
    
    # 模拟企业微信文本消息
    test_message = {
        "msgtype": "text",
        "text": {
            "content": "你好，这是一条测试消息"
        },
        "from": {
            "userid": "test_user",
            "name": "测试用户"
        }
    }
    
    try:
        response = requests.post(
            f"{base_url}/webhook",
            json=test_message,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 消息处理成功:")
            print(f"   回复类型: {data.get('msgtype', 'unknown')}")
            if 'text' in data:
                content = data['text'].get('content', '')
                print(f"   回复内容: {content[:100]}{'...' if len(content) > 100 else ''}")
            return True
        else:
            print(f"❌ 消息处理失败: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 消息处理异常: {e}")
        return False


def test_multiple_users(base_url: str = "http://localhost:8080"):
    """测试多用户会话隔离"""
    print("\n👥 测试多用户会话隔离...")
    
    users = [
        {"userid": "user1", "name": "用户1", "message": "我叫张三"},
        {"userid": "user2", "name": "用户2", "message": "我叫李四"},
        {"userid": "user1", "name": "用户1", "message": "我叫什么名字？"},
        {"userid": "user2", "name": "用户2", "message": "我叫什么名字？"}
    ]
    
    for i, user in enumerate(users):
        print(f"\n  第 {i+1} 条消息 - {user['name']}: {user['message']}")
        
        test_message = {
            "msgtype": "text",
            "text": {"content": user['message']},
            "from": {"userid": user['userid'], "name": user['name']}
        }
        
        try:
            response = requests.post(
                f"{base_url}/webhook",
                json=test_message,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'text' in data:
                    content = data['text'].get('content', '')
                    print(f"  AI 回复: {content[:100]}{'...' if len(content) > 100 else ''}")
            else:
                print(f"  ❌ 失败: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ 异常: {e}")
        
        # 间隔一下，避免请求过快
        time.sleep(1)


def main():
    print("=" * 60)
    print("        企业微信机器人测试")
    print("=" * 60)
    
    base_url = "http://localhost:8080"
    
    # 测试健康检查
    health_ok = test_health_check(base_url)
    
    if not health_ok:
        print("\n❌ 服务未启动或不可用，请先启动机器人服务")
        print("   启动命令: python scripts/start_wework_bot.py")
        return
    
    # 测试基本消息处理
    message_ok = test_webhook_message(base_url)
    
    if message_ok:
        # 测试多用户会话
        test_multiple_users(base_url)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()