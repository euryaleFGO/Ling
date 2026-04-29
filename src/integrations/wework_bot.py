#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人集成
支持接收企业微信消息并通过现有 Agent 系统回复

企业微信机器人文档: https://developer.work.weixin.qq.com/document/path/101039
"""

import os
import sys
import json
import time
import hashlib
import hmac
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
import logging

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from backend.llm.agent.agent import Agent
from core.log import log

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeWorkBot:
    """企业微信机器人"""
    
    def __init__(self, webhook_key: str = None):
        """
        初始化企业微信机器人
        
        Args:
            webhook_key: 企业微信机器人的 webhook key（用于验证签名）
        """
        self.webhook_key = webhook_key or os.getenv("WEWORK_WEBHOOK_KEY", "")
        
        # 用户会话管理（user_id -> Agent）
        self.user_agents: Dict[str, Agent] = {}
        
        # Flask 应用
        self.app = Flask(__name__)
        self._setup_routes()
        
        logger.info("企业微信机器人初始化完成")
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """企业微信 Webhook 接收消息"""
            try:
                # 验证签名（如果配置了 webhook_key）
                if self.webhook_key and not self._verify_signature(request):
                    logger.warning("签名验证失败")
                    return jsonify({"error": "Invalid signature"}), 401
                
                # 解析消息
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No data"}), 400
                
                logger.info(f"收到企业微信消息: {json.dumps(data, ensure_ascii=False)}")
                
                # 处理消息
                response = self._handle_message(data)
                
                return jsonify(response)
                
            except Exception as e:
                logger.error(f"处理企业微信消息失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """健康检查"""
            return jsonify({
                "status": "ok",
                "timestamp": int(time.time()),
                "active_users": len(self.user_agents)
            })
    
    def _verify_signature(self, request) -> bool:
        """验证企业微信签名"""
        try:
            # 企业微信使用 HMAC-SHA256 签名
            signature = request.headers.get('X-Signature', '')
            if not signature:
                return False
            
            # 计算签名
            body = request.get_data()
            expected = hmac.new(
                self.webhook_key.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected)
            
        except Exception as e:
            logger.error(f"签名验证异常: {e}")
            return False
    
    def _handle_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理企业微信消息
        
        Args:
            data: 企业微信消息数据
            
        Returns:
            响应数据
        """
        # 提取消息信息
        msg_type = data.get('msgtype', '')
        
        if msg_type == 'text':
            return self._handle_text_message(data)
        elif msg_type == 'event':
            return self._handle_event_message(data)
        else:
            logger.warning(f"不支持的消息类型: {msg_type}")
            return {"text": {"content": "抱歉，暂不支持此类型消息"}}
    
    def _handle_text_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理文本消息"""
        try:
            # 提取用户信息和消息内容
            text_data = data.get('text', {})
            content = text_data.get('content', '').strip()
            
            # 提取用户 ID（企业微信会提供发送者信息）
            from_user = data.get('from', {})
            user_id = from_user.get('userid', 'unknown_user')
            user_name = from_user.get('name', user_id)
            
            if not content:
                return {"text": {"content": "请发送有效的文本消息"}}
            
            logger.info(f"用户 {user_name}({user_id}) 发送消息: {content}")
            
            # 获取或创建用户的 Agent
            agent = self._get_user_agent(user_id)
            
            # 生成回复
            try:
                # 使用同步方式获取回复
                response_text = agent.chat_sync(content)
                
                logger.info(f"AI 回复给 {user_name}: {response_text[:100]}...")
                
                return {
                    "msgtype": "text",
                    "text": {
                        "content": response_text,
                        "mentioned_list": []  # 可以 @ 特定用户
                    }
                }
                
            except Exception as e:
                logger.error(f"Agent 处理失败: {e}")
                return {
                    "msgtype": "text", 
                    "text": {
                        "content": f"抱歉，处理消息时出现错误: {str(e)}"
                    }
                }
                
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            return {
                "msgtype": "text",
                "text": {
                    "content": "抱歉，消息处理失败"
                }
            }
    
    def _handle_event_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理事件消息（如用户加入群聊等）"""
        event_type = data.get('event', {}).get('EventType', '')
        
        if event_type == 'enter_chat':
            # 用户进入群聊
            return {
                "msgtype": "text",
                "text": {
                    "content": "欢迎！我是智能助手玲，有什么可以帮助您的吗？"
                }
            }
        
        # 其他事件暂不处理
        return {}
    
    def _get_user_agent(self, user_id: str) -> Agent:
        """获取或创建用户的 Agent 实例"""
        if user_id not in self.user_agents:
            # 为新用户创建 Agent
            agent = Agent(
                user_id=f"wework_{user_id}",  # 添加前缀区分企业微信用户
                enable_tools=True  # 启用工具功能
            )
            agent.start_chat()
            self.user_agents[user_id] = agent
            logger.info(f"为用户 {user_id} 创建新的 Agent 会话")
        
        return self.user_agents[user_id]
    
    def cleanup_inactive_users(self, max_idle_hours: int = 24):
        """清理长时间不活跃的用户会话"""
        # 这里可以添加基于时间的会话清理逻辑
        # 暂时简单实现
        pass
    
    def run(self, host: str = "0.0.0.0", port: int = 8080, debug: bool = False):
        """启动 Flask 服务器"""
        logger.info(f"启动企业微信机器人服务器: http://{host}:{port}")
        logger.info("Webhook 地址: http://{host}:{port}/webhook")
        
        self.app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True  # 支持并发请求
        )


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="企业微信机器人服务")
    parser.add_argument("--host", default="0.0.0.0", help="服务器地址")
    parser.add_argument("--port", type=int, default=8080, help="服务器端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--webhook-key", help="企业微信 Webhook Key")
    
    args = parser.parse_args()
    
    # 创建机器人实例
    bot = WeWorkBot(webhook_key=args.webhook_key)
    
    # 启动服务
    bot.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )


if __name__ == "__main__":
    main()