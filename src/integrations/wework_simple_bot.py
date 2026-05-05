#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人 - 简化版
基于企业微信官方接入方式，无需复杂的 token 验证
"""

import os
import sys
import json
import time
import logging
import requests
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

from backend.llm.agent.agent import Agent
from core.log import log
from integrations.base_bot import BaseBot

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeWorkSimpleBot(BaseBot):
    """企业微信机器人 - 简化版"""

    def __init__(self, corp_id: str, corp_secret: str, agent_id: str = "1000002"):
        """
        初始化企业微信机器人

        Args:
            corp_id: 企业 ID (Bot ID)
            corp_secret: 应用密钥 (Secret)
            agent_id: 应用 ID
        """
        super().__init__(agent_id_prefix="wework_")
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.agent_id = agent_id

        # API 配置
        self.api_base = "https://qyapi.weixin.qq.com/cgi-bin"
        self.access_token = None
        self.token_expires_at = None

        logger.info("企业微信机器人初始化完成")
    
    def get_access_token(self) -> Optional[str]:
        """获取访问令牌"""
        # 检查现有 token 是否有效
        if (self.access_token and self.token_expires_at and 
            datetime.now() < self.token_expires_at):
            return self.access_token
        
        # 获取新的 access_token
        url = f"{self.api_base}/gettoken"
        params = {
            "corpid": self.corp_id,
            "corpsecret": self.corp_secret
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("errcode") == 0:
                self.access_token = data["access_token"]
                # token 有效期 7200 秒，提前 5 分钟刷新
                expires_in = data.get("expires_in", 7200)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                logger.info("获取 access_token 成功")
                return self.access_token
            else:
                logger.error(f"获取 access_token 失败: {data}")
                return None
                
        except Exception as e:
            logger.error(f"获取 access_token 异常: {e}")
            return None
    
    def send_message(self, user_id: str, content: str) -> bool:
        """发送消息给用户"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("无法获取 access_token")
            return False
        
        url = f"{self.api_base}/message/send"
        params = {"access_token": access_token}
        
        # 构建消息
        message_data = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": int(self.agent_id),
            "text": {
                "content": content
            },
            "safe": 0
        }
        
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
        return self.get_or_create_agent(user_id)
    
    def handle_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理接收到的消息"""
        try:
            # 企业微信消息格式
            from_user = message_data.get("FromUserName", "")
            msg_type = message_data.get("MsgType", "")
            
            if msg_type == "text":
                content = message_data.get("Content", "").strip()
                
                if not content:
                    return {"errcode": 0, "errmsg": "ok"}
                
                logger.info(f"用户 {from_user} 发送消息: {content}")
                
                # 获取 Agent 并生成回复
                agent = self._get_user_agent(from_user)
                
                try:
                    # 生成回复
                    response_text = agent.chat_sync(content)
                    
                    # 发送回复
                    success = self.send_message(from_user, response_text)
                    
                    if success:
                        logger.info(f"AI 回复给 {from_user}: {response_text[:100]}...")
                    else:
                        logger.error(f"发送回复失败给用户 {from_user}")
                    
                except Exception as e:
                    logger.error(f"Agent 处理失败: {e}")
                    # 发送错误提示
                    self.send_message(from_user, "抱歉，处理消息时出现错误，请稍后重试。")
            
            elif msg_type == "event":
                # 处理事件消息
                event = message_data.get("Event", "")
                if event in ["subscribe", "enter_agent"]:
                    # 用户关注或进入应用
                    self.send_message(from_user, "欢迎！我是智能助手玲，有什么可以帮助您的吗？")
            
            return {"errcode": 0, "errmsg": "ok"}
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return {"errcode": -1, "errmsg": str(e)}


def create_flask_app(corp_id: str, corp_secret: str, agent_id: str = "1000002"):
    """创建 Flask 应用"""
    app = Flask(__name__)
    bot = WeWorkSimpleBot(corp_id, corp_secret, agent_id)
    
    @app.route('/webhook', methods=['GET', 'POST'])
    def webhook():
        """企业微信 Webhook 接口"""
        if request.method == 'GET':
            # URL 验证（企业微信会发送 GET 请求验证 URL）
            echostr = request.args.get('echostr', '')
            return echostr
        
        elif request.method == 'POST':
            # 处理消息
            try:
                # 获取 XML 数据并转换为字典
                data = request.get_data()
                
                # 简单的 XML 解析（实际项目中建议使用专业的 XML 解析库）
                message_dict = parse_wework_xml(data)
                
                if message_dict:
                    result = bot.handle_message(message_dict)
                    return jsonify(result)
                else:
                    return jsonify({"errcode": 0, "errmsg": "ok"})
                    
            except Exception as e:
                logger.error(f"处理 Webhook 请求失败: {e}")
                return jsonify({"errcode": -1, "errmsg": str(e)})
    
    @app.route('/health', methods=['GET'])
    def health():
        """健康检查"""
        return jsonify({
            "status": "ok",
            "corp_id": corp_id,
            "agent_id": agent_id,
            "active_users": len(bot.user_agents),
            "timestamp": int(time.time())
        })
    
    @app.route('/send', methods=['POST'])
    def send_message():
        """手动发送消息接口（测试用）"""
        try:
            data = request.get_json()
            user_id = data.get('user_id')
            content = data.get('content')
            
            if not user_id or not content:
                return jsonify({"error": "缺少 user_id 或 content"}), 400
            
            success = bot.send_message(user_id, content)
            
            if success:
                return jsonify({"success": True, "message": "发送成功"})
            else:
                return jsonify({"success": False, "message": "发送失败"}), 500
                
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return app, bot


def parse_wework_xml(xml_data: bytes) -> Dict[str, Any]:
    """
    解析企业微信 XML 消息
    简化版实现，实际项目建议使用 xmltodict 或其他专业库
    """
    try:
        import xml.etree.ElementTree as ET
        
        # 解析 XML
        root = ET.fromstring(xml_data)
        
        # 转换为字典
        message_dict = {}
        for child in root:
            message_dict[child.tag] = child.text
        
        return message_dict
        
    except Exception as e:
        logger.error(f"XML 解析失败: {e}")
        return {}


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="企业微信机器人服务 - 简化版")
    parser.add_argument("--corp-id", help="企业 ID (Bot ID)")
    parser.add_argument("--corp-secret", help="应用密钥 (Secret)")
    parser.add_argument("--agent-id", default="1000002", help="应用 ID")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址 (默认: 127.0.0.1，仅本地访问)")
    parser.add_argument("--port", type=int, default=8080, help="服务器端口")
    
    args = parser.parse_args()
    
    # 从环境变量获取配置
    corp_id = args.corp_id or os.getenv("WEWORK_CORP_ID") or os.getenv("WEWORK_BOT_ID")
    corp_secret = args.corp_secret or os.getenv("WEWORK_CORP_SECRET") or os.getenv("WEWORK_SECRET")
    agent_id = args.agent_id or os.getenv("WEWORK_AGENT_ID", "1000002")
    
    if not corp_id or not corp_secret:
        logger.error("❌ 错误: 缺少必需的配置")
        logger.info("请设置环境变量或使用命令行参数:")
        logger.info("  WEWORK_CORP_ID=你的企业ID")
        logger.info("  WEWORK_CORP_SECRET=你的应用密钥")
        return

    logger.info("=" * 60)
    logger.info("        企业微信机器人 - 简化版")
    logger.info("=" * 60)
    logger.info(f"企业 ID: {corp_id}")
    logger.info(f"应用 ID: {agent_id}")
    logger.info(f"服务器地址: http://{args.host}:{args.port}")
    logger.info(f"Webhook 地址: http://{args.host}:{args.port}/webhook")
    
    # 创建并启动应用
    try:
        app, bot = create_flask_app(corp_id, corp_secret, agent_id)
        
        logger.info("🚀 启动企业微信机器人...")
        app.run(host=args.host, port=args.port, debug=False, threaded=True)

    except KeyboardInterrupt:
        logger.info("\n用户中断，正在关闭服务器...")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()