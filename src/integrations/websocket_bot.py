#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 聊天机器人
支持长连接实时对话，可用于网页、移动应用等场景
"""

import os
import sys
import json
import time
import asyncio
import logging
from typing import Dict, Set, Optional
import websockets
from websockets.server import WebSocketServerProtocol

from backend.llm.agent.agent import Agent
from core.log import log

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketChatBot:
    """WebSocket 聊天机器人"""
    
    def __init__(self):
        # 连接管理
        self.connections: Dict[str, WebSocketServerProtocol] = {}
        self.user_agents: Dict[str, Agent] = {}
        
        # 统计信息
        self.total_connections = 0
        self.active_connections = 0
        
        logger.info("WebSocket 聊天机器人初始化完成")
    
    async def register_connection(self, websocket: WebSocketServerProtocol, user_id: str):
        """注册新连接"""
        self.connections[user_id] = websocket
        self.total_connections += 1
        self.active_connections += 1
        
        # 创建用户的 Agent
        if user_id not in self.user_agents:
            agent = Agent(
                user_id=f"ws_{user_id}",
                enable_tools=True
            )
            agent.start_chat()
            self.user_agents[user_id] = agent
            logger.info(f"为用户 {user_id} 创建新的 Agent 会话")
        
        logger.info(f"用户 {user_id} 连接成功，当前活跃连接: {self.active_connections}")
        
        # 发送欢迎消息
        await self.send_message(user_id, {
            "type": "system",
            "message": "欢迎！我是智能助手玲，有什么可以帮助您的吗？",
            "timestamp": int(time.time())
        })
    
    async def unregister_connection(self, user_id: str):
        """注销连接"""
        if user_id in self.connections:
            del self.connections[user_id]
            self.active_connections -= 1
            logger.info(f"用户 {user_id} 断开连接，当前活跃连接: {self.active_connections}")
        
        # 可选：保留 Agent 会话一段时间，以便重连时恢复上下文
        # 这里暂时不删除，让会话保持活跃
    
    async def send_message(self, user_id: str, message: dict):
        """发送消息给指定用户"""
        if user_id in self.connections:
            try:
                await self.connections[user_id].send(json.dumps(message, ensure_ascii=False))
            except websockets.exceptions.ConnectionClosed:
                await self.unregister_connection(user_id)
            except Exception as e:
                logger.error(f"发送消息失败 {user_id}: {e}")
    
    async def broadcast_message(self, message: dict, exclude_user: str = None):
        """广播消息给所有连接的用户"""
        for user_id in list(self.connections.keys()):
            if user_id != exclude_user:
                await self.send_message(user_id, message)
    
    async def handle_user_message(self, user_id: str, message_data: dict):
        """处理用户消息"""
        try:
            message_type = message_data.get("type", "text")
            content = message_data.get("message", "").strip()
            
            if not content:
                await self.send_message(user_id, {
                    "type": "error",
                    "message": "消息内容不能为空",
                    "timestamp": int(time.time())
                })
                return
            
            logger.info(f"用户 {user_id} 发送消息: {content[:50]}...")
            
            # 发送"正在输入"状态
            await self.send_message(user_id, {
                "type": "typing",
                "message": "AI 正在思考中...",
                "timestamp": int(time.time())
            })
            
            # 获取 Agent 并生成回复
            agent = self.user_agents.get(user_id)
            if not agent:
                await self.send_message(user_id, {
                    "type": "error",
                    "message": "会话未初始化，请重新连接",
                    "timestamp": int(time.time())
                })
                return
            
            # 流式回复
            response_parts = []
            chunk_buffer = ""
            
            try:
                for chunk in agent.chat(content, stream=True):
                    response_parts.append(chunk)
                    chunk_buffer += chunk
                    
                    # 每收集一定字符就发送一次中间结果
                    if len(chunk_buffer) >= 10:  # 每10个字符发送一次
                        await self.send_message(user_id, {
                            "type": "partial",
                            "message": "".join(response_parts),
                            "timestamp": int(time.time())
                        })
                        chunk_buffer = ""
                
                # 发送最终完整回复
                full_response = "".join(response_parts)
                await self.send_message(user_id, {
                    "type": "message",
                    "message": full_response,
                    "timestamp": int(time.time())
                })
                
                logger.info(f"AI 回复给 {user_id}: {full_response[:50]}...")
                
            except Exception as e:
                logger.error(f"Agent 处理失败 {user_id}: {e}")
                await self.send_message(user_id, {
                    "type": "error",
                    "message": f"处理消息时出现错误: {str(e)}",
                    "timestamp": int(time.time())
                })
        
        except Exception as e:
            logger.error(f"处理用户消息失败 {user_id}: {e}")
            await self.send_message(user_id, {
                "type": "error",
                "message": "服务器内部错误",
                "timestamp": int(time.time())
            })
    
    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """处理 WebSocket 连接"""
        user_id = None
        
        try:
            # 等待用户发送认证信息
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            
            if auth_data.get("type") != "auth":
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "需要先发送认证信息"
                }))
                return
            
            user_id = auth_data.get("user_id", f"user_{int(time.time())}")
            user_name = auth_data.get("user_name", user_id)
            
            # 注册连接
            await self.register_connection(websocket, user_id)
            
            # 发送认证成功消息
            await websocket.send(json.dumps({
                "type": "auth_success",
                "user_id": user_id,
                "message": f"认证成功，欢迎 {user_name}！",
                "timestamp": int(time.time())
            }))
            
            # 处理后续消息
            async for message in websocket:
                try:
                    message_data = json.loads(message)
                    await self.handle_user_message(user_id, message_data)
                except json.JSONDecodeError:
                    await self.send_message(user_id, {
                        "type": "error",
                        "message": "消息格式错误，请发送有效的 JSON",
                        "timestamp": int(time.time())
                    })
                except Exception as e:
                    logger.error(f"处理消息异常 {user_id}: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"用户 {user_id or 'unknown'} 连接关闭")
        except Exception as e:
            logger.error(f"连接处理异常 {user_id or 'unknown'}: {e}")
        finally:
            if user_id:
                await self.unregister_connection(user_id)
    
    async def get_stats(self):
        """获取统计信息"""
        return {
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "active_users": list(self.connections.keys()),
            "timestamp": int(time.time())
        }
    
    def run(self, host: str = "localhost", port: int = 8765):
        """启动 WebSocket 服务器"""
        logger.info(f"启动 WebSocket 聊天机器人: ws://{host}:{port}")
        logger.info("等待客户端连接...")
        
        # 启动 WebSocket 服务器
        start_server = websockets.serve(
            self.handle_connection,
            host,
            port,
            ping_interval=30,  # 30秒心跳
            ping_timeout=10,   # 10秒超时
            max_size=1024*1024  # 1MB 最大消息大小
        )
        
        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="WebSocket 聊天机器人服务")
    parser.add_argument("--host", default="localhost", help="服务器地址")
    parser.add_argument("--port", type=int, default=8765, help="服务器端口")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("        WebSocket 聊天机器人 - 玲 (Liying)")
    print("=" * 60)
    print(f"服务器地址: ws://{args.host}:{args.port}")
    print("支持功能:")
    print("  ✅ 实时对话")
    print("  ✅ 流式回复")
    print("  ✅ 多用户支持")
    print("  ✅ 上下文记忆")
    print("  ✅ 工具调用")
    print()
    
    # 创建并启动机器人
    try:
        bot = WebSocketChatBot()
        bot.run(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\n用户中断，正在关闭服务器...")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()