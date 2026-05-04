#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信应用机器人集成（SDK 长连接方式）
支持企业微信应用机器人的完整功能
"""

import os
import sys
import json
import time
import asyncio
import logging
import hashlib
import hmac
import base64
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from backend.llm.agent.agent import Agent
from core.log import log

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeWorkAppBot:
    """企业微信应用机器人（SDK 长连接方式）"""
    
    def __init__(self, bot_id: str, secret: str):
        """
        初始化企业微信应用机器人
        
        Args:
            bot_id: 机器人 Bot ID
            secret: 机器人 Secret
        """
        self.bot_id = bot_id
        self.secret = secret
        
        # API 基础配置
        self.api_base = "https://qyapi.weixin.qq.com/cgi-bin"
        self.access_token = None
        self.token_expires_at = None
        
        # 用户会话管理
        self.user_agents: Dict[str, Agent] = {}
        
        # 消息处理
        self.running = False
        
        logger.info("企业微信应用机器人初始化完成")
    
    async def get_access_token(self) -> str:
        """获取访问令牌"""
        # 检查现有 token 是否有效
        if (self.access_token and self.token_expires_at and 
            datetime.now() < self.token_expires_at):
            return self.access_token
        
        # 获取新的 access_token
        url = f"{self.api_base}/gettoken"
        params = {
            "corpid": self.bot_id,  # 这里可能需要调整为实际的 corpid
            "corpsecret": self.secret
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("errcode") == 0:
                self.access_token = data["access_token"]
                # token 有效期通常是 7200 秒，提前 5 分钟刷新
                self.token_expires_at = datetime.now() + timedelta(seconds=data.get("expires_in", 7200) - 300)
                logger.info("获取 access_token 成功")
                return self.access_token
            else:
                logger.error(f"获取 access_token 失败: {data}")
                return None
                
        except Exception as e:
            logger.error(f"获取 access_token 异常: {e}")
            return None
    
    async def send_message(self, user_id: str, content: str, msg_type: str = "text"):
        """
        发送消息给用户
        
        Args:
            user_id: 用户 ID
            content: 消息内容
            msg_type: 消息类型（text, markdown 等）
        """
        access_token = await self.get_access_token()
        if not access_token:
            logger.error("无法获取 access_token，消息发送失败")
            return False
        
        url = f"{self.api_base}/message/send"
        params = {"access_token": access_token}
        
        # 构建消息体
        message_data = {
            "touser": user_id,
            "msgtype": msg_type,
            "agentid": 0,  # 可能需要配置实际的 agentid
        }
        
        if msg_type == "text":
            message_data["text"] = {"content": content}
        elif msg_type == "markdown":
            message_data["markdown"] = {"content": content}
        
        try:
            response = requests.post(
                url,
                params=params,
                json=message_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            result = response.json()
            if result.get("errcode") == 0:
                logger.info(f"消息发送成功给用户 {user_id}")
                return True
            else:
                logger.error(f"消息发送失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"发送消息异常: {e}")
            return False
    
    def _get_user_agent(self, user_id: str) -> Agent:
        """获取或创建用户的 Agent 实例"""
        if user_id not in self.user_agents:
            agent = Agent(
                user_id=f"wework_app_{user_id}",
                enable_tools=True
            )
            agent.start_chat()
            self.user_agents[user_id] = agent
            logger.info(f"为用户 {user_id} 创建新的 Agent 会话")
        
        return self.user_agents[user_id]
    
    async def handle_message(self, message_data: Dict[str, Any]):
        """
        处理接收到的消息
        
        Args:
            message_data: 企业微信消息数据
        """
        try:
            msg_type = message_data.get("MsgType", "")
            from_user = message_data.get("FromUserName", "")
            
            if msg_type == "text":
                content = message_data.get("Content", "").strip()
                
                if not content:
                    await self.send_message(from_user, "请发送有效的文本消息")
                    return
                
                logger.info(f"用户 {from_user} 发送消息: {content}")
                
                # 获取 Agent 并生成回复
                agent = self._get_user_agent(from_user)
                
                try:
                    # 生成回复
                    response_text = agent.chat_sync(content)
                    
                    # 发送回复
                    await self.send_message(from_user, response_text)
                    
                    logger.info(f"AI 回复给 {from_user}: {response_text[:100]}...")
                    
                except Exception as e:
                    logger.error(f"Agent 处理失败: {e}")
                    await self.send_message(from_user, f"抱歉，处理消息时出现错误: {str(e)}")
            
            elif msg_type == "event":
                # 处理事件消息
                event = message_data.get("Event", "")
                if event == "subscribe":
                    await self.send_message(from_user, "欢迎关注！我是智能助手玲，有什么可以帮助您的吗？")
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    async def start_polling(self, interval: int = 5):
        """
        开始轮询消息（简化版实现）
        实际生产环境建议使用企业微信的回调 URL 方式
        """
        self.running = True
        logger.info("开始消息轮询...")
        
        while self.running:
            try:
                # 这里应该调用企业微信 API 获取新消息
                # 由于企业微信通常使用回调方式，这里只是示例
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"轮询异常: {e}")
                await asyncio.sleep(interval)
    
    def stop(self):
        """停止机器人"""
        self.running = False
        logger.info("机器人已停止")
    
    async def setup_webhook(self, callback_url: str, token: str, encoding_aes_key: str):
        """
        设置 Webhook 回调（推荐方式）
        
        Args:
            callback_url: 回调 URL
            token: 验证 token
            encoding_aes_key: 消息加密密钥
        """
        # 这里需要调用企业微信 API 设置回调 URL
        # 具体实现需要参考企业微信文档
        pass


class WeWorkWebhookHandler:
    """企业微信 Webhook 处理器（推荐使用）"""
    
    def __init__(self, bot: WeWorkAppBot, token: str, encoding_aes_key: str = None):
        self.bot = bot
        self.token = token
        self.encoding_aes_key = encoding_aes_key
    
    def verify_signature(self, signature: str, timestamp: str, nonce: str, echo_str: str = None) -> bool:
        """验证签名"""
        try:
            # 企业微信签名验证
            tmp_list = [self.token, timestamp, nonce]
            if echo_str:
                tmp_list.append(echo_str)
            
            tmp_list.sort()
            tmp_str = "".join(tmp_list)
            
            import hashlib
            hash_obj = hashlib.sha1(tmp_str.encode('utf-8'))
            hashcode = hash_obj.hexdigest()
            
            return hashcode == signature
            
        except Exception as e:
            logger.error(f"签名验证异常: {e}")
            return False
    
    async def handle_webhook(self, request_data: dict, query_params: dict):
        """处理 Webhook 请求"""
        # 验证签名
        signature = query_params.get('msg_signature', '')
        timestamp = query_params.get('timestamp', '')
        nonce = query_params.get('nonce', '')
        
        if not self.verify_signature(signature, timestamp, nonce):
            logger.warning("Webhook 签名验证失败")
            return {"errcode": -1, "errmsg": "Invalid signature"}
        
        # 处理消息
        await self.bot.handle_message(request_data)
        
        return {"errcode": 0, "errmsg": "ok"}


def create_flask_app(bot_id: str, secret: str, token: str, encoding_aes_key: str = None):
    """创建 Flask 应用"""
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    bot = WeWorkAppBot(bot_id, secret)
    webhook_handler = WeWorkWebhookHandler(bot, token, encoding_aes_key)
    
    @app.route('/webhook', methods=['GET', 'POST'])
    async def webhook():
        if request.method == 'GET':
            # 验证回调 URL
            signature = request.args.get('msg_signature', '')
            timestamp = request.args.get('timestamp', '')
            nonce = request.args.get('nonce', '')
            echostr = request.args.get('echostr', '')
            
            if webhook_handler.verify_signature(signature, timestamp, nonce, echostr):
                return echostr
            else:
                return "Invalid signature", 403
        
        elif request.method == 'POST':
            # 处理消息
            data = request.get_json() or {}
            query_params = dict(request.args)
            
            result = await webhook_handler.handle_webhook(data, query_params)
            return jsonify(result)
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({
            "status": "ok",
            "bot_id": bot_id,
            "active_users": len(bot.user_agents),
            "timestamp": int(time.time())
        })
    
    return app, bot


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="企业微信应用机器人服务")
    parser.add_argument("--bot-id", required=True, help="机器人 Bot ID")
    parser.add_argument("--secret", required=True, help="机器人 Secret")
    parser.add_argument("--token", required=True, help="回调验证 Token")
    parser.add_argument("--encoding-aes-key", help="消息加密密钥")
    parser.add_argument("--host", default="0.0.0.0", help="服务器地址")
    parser.add_argument("--port", type=int, default=8080, help="服务器端口")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("        企业微信应用机器人 - 玲 (Liying)")
    print("=" * 60)
    print(f"Bot ID: {args.bot_id}")
    print(f"服务器地址: http://{args.host}:{args.port}")
    print(f"Webhook 地址: http://{args.host}:{args.port}/webhook")
    print()
    
    # 创建 Flask 应用
    app, bot = create_flask_app(
        args.bot_id,
        args.secret,
        args.token,
        args.encoding_aes_key
    )
    
    # 启动服务
    try:
        app.run(host=args.host, port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n用户中断，正在关闭服务器...")
        bot.stop()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()