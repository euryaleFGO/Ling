#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业微信机器人 WebSocket 长连接版本
支持流式消息、主动推送、无需公网 IP

官方文档: https://developer.work.weixin.qq.com/document/path/101463
"""

import os
import sys
import json
import time
import asyncio
import threading
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging

import websockets
from websockets.client import WebSocketClientProtocol

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from backend.llm.agent.agent import Agent
from core.log import log

# 配置日志 - 设置为 INFO 级别以显示详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class WeWorkConfig:
    """企业微信机器人配置"""
    bot_id: str                    # 机器人 ID
    secret: str                    # 长连接密钥
    ws_url: str = "wss://openws.work.weixin.qq.com"  # WebSocket 地址
    heartbeat_interval: int = 30   # 心跳间隔（秒）
    reconnect_delay: int = 5       # 重连延迟（秒）
    max_reconnect_attempts: int = 10  # 最大重连次数


class WeWorkBotWebSocket:
    """企业微信机器人 WebSocket 长连接版本"""
    
    def __init__(self, config: WeWorkConfig):
        """
        初始化企业微信机器人
        
        Args:
            config: 机器人配置
        """
        print("=" * 60)
        print("🤖 初始化企业微信机器人...")
        print(f"   Bot ID: {config.bot_id}")
        print(f"   WebSocket URL: {config.ws_url}")
        print("=" * 60)
        logger.info("=" * 60)
        logger.info("🤖 初始化企业微信机器人...")
        logger.info(f"   Bot ID: {config.bot_id}")
        logger.info(f"   WebSocket URL: {config.ws_url}")
        logger.info("=" * 60)
        
        self.config = config
        
        # WebSocket 连接
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.subscribed = False
        
        # 用户会话管理（user_id -> Agent）
        self.user_agents: Dict[str, Agent] = {}
        
        # 流式消息管理（stream_id -> req_id）
        self.stream_sessions: Dict[str, str] = {}
        
        # 事件循环
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = False
        
        # 心跳任务
        self.heartbeat_task: Optional[asyncio.Task] = None
        
        # 回调函数
        self.on_message_callback: Optional[Callable] = None
        self.on_event_callback: Optional[Callable] = None
        
        print("✅ 企业微信机器人初始化完成")
        logger.info("✅ 企业微信机器人初始化完成")
    
    async def connect(self):
        """建立 WebSocket 连接"""
        try:
            print("=" * 60)
            print(f"🔌 正在连接到企业微信 WebSocket...")
            print(f"   URL: {self.config.ws_url}")
            print("=" * 60)
            logger.info("=" * 60)
            logger.info(f"🔌 正在连接到企业微信 WebSocket...")
            logger.info(f"   URL: {self.config.ws_url}")
            logger.info("=" * 60)
            
            # 建立 WebSocket 连接
            self.ws = await websockets.connect(
                self.config.ws_url,
                ping_interval=None,  # 我们自己管理心跳
                ping_timeout=None
            )
            
            self.connected = True
            print("✅ WebSocket 连接建立成功")
            logger.info("✅ WebSocket 连接建立成功")

            # 发送订阅请求
            print("📡 正在发送订阅请求...")
            logger.info("📡 正在发送订阅请求...")
            await self._subscribe()

            # 启动心跳
            print("💓 启动心跳保活...")
            logger.info("💓 启动心跳保活...")
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 开始接收消息
            print("👂 开始监听消息...")
            print("=" * 60)
            print("✅ 企业微信机器人已就绪，等待消息...")
            print("=" * 60)
            logger.info("👂 开始监听消息...")
            logger.info("=" * 60)
            logger.info("✅ 企业微信机器人已就绪，等待消息...")
            logger.info("=" * 60)
            await self._receive_loop()
            
        except Exception as e:
            print(f"❌ WebSocket 连接失败: {e}")
            logger.error(f"❌ WebSocket 连接失败: {e}")
            self.connected = False
            raise
    
    async def _subscribe(self):
        """发送订阅请求"""
        try:
            req_id = self._generate_req_id()
            
            subscribe_msg = {
                "cmd": "aibot_subscribe",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "bot_id": self.config.bot_id,
                    "secret": self.config.secret
                }
            }
            
            print("📡 发送订阅请求...")
            logger.info("📡 发送订阅请求...")
            await self.ws.send(json.dumps(subscribe_msg))

            # 等待订阅响应
            response = await self.ws.recv()
            resp_data = json.loads(response)

            if resp_data.get("errcode") == 0:
                self.subscribed = True
                print("✅ 订阅成功！")
                logger.info("✅ 订阅成功！")
            else:
                error_msg = resp_data.get("errmsg", "Unknown error")
                print(f"❌ 订阅失败: {error_msg}")
                logger.error(f"❌ 订阅失败: {error_msg}")
                raise Exception(f"订阅失败: {error_msg}")

        except Exception as e:
            print(f"❌ 订阅请求失败: {e}")
            logger.error(f"❌ 订阅请求失败: {e}")
            raise
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.connected and self.subscribed:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                if not self.connected:
                    break
                
                # 发送心跳
                req_id = self._generate_req_id()
                ping_msg = {
                    "cmd": "ping",
                    "headers": {
                        "req_id": req_id
                    }
                }
                
                await self.ws.send(json.dumps(ping_msg))
                logger.debug("发送心跳")
                
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                break
    
    async def _receive_loop(self):
        """接收消息循环"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    # 【新增】打印接收到的原始消息
                    print("=" * 60)
                    print("📥 收到 WebSocket 消息:")
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    print("=" * 60)
                    logger.info("=" * 60)
                    logger.info("📥 收到 WebSocket 消息:")
                    logger.info(json.dumps(data, ensure_ascii=False, indent=2))
                    logger.info("=" * 60)
                    
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    print(f"❌ JSON 解析失败: {e}")
                    logger.error(f"❌ JSON 解析失败: {e}")
                except Exception as e:
                    print(f"❌ 处理消息失败: {e}")
                    logger.error(f"❌ 处理消息失败: {e}")
                    import traceback
                    traceback.print_exc()
                    
        except websockets.exceptions.ConnectionClosed:
            print("⚠️  WebSocket 连接已关闭")
            logger.warning("⚠️  WebSocket 连接已关闭")
            self.connected = False
        except Exception as e:
            print(f"❌ 接收消息失败: {e}")
            logger.error(f"❌ 接收消息失败: {e}")
            self.connected = False
    
    async def _handle_message(self, data: Dict[str, Any]):
        """处理接收到的消息"""
        cmd = data.get("cmd", "")
        
        if cmd == "aibot_msg_callback":
            # 消息回调
            await self._handle_msg_callback(data)
        elif cmd == "aibot_event_callback":
            # 事件回调
            await self._handle_event_callback(data)
        elif cmd == "pong":
            # 心跳响应
            logger.debug("收到心跳响应")
        else:
            logger.debug(f"收到其他消息: {cmd}")
    
    async def _handle_msg_callback(self, data: Dict[str, Any]):
        """处理消息回调"""
        try:
            body = data.get("body", {})
            headers = data.get("headers", {})
            req_id = headers.get("req_id", "")
            
            # 提取消息信息
            msgtype = body.get("msgtype", "")
            from_user = body.get("from", {})
            user_id = from_user.get("userid", "unknown")
            user_name = from_user.get("name", user_id)
            chatid = body.get("chatid", "")
            chattype = body.get("chattype", "single")
            
            print("=" * 60)
            print(f"💬 收到消息:")
            print(f"   类型: {msgtype}")
            print(f"   用户: {user_name} ({user_id})")
            print(f"   会话: {chattype} ({chatid})")
            print(f"   请求ID: {req_id}")
            logger.info("=" * 60)
            logger.info(f"💬 收到消息:")
            logger.info(f"   类型: {msgtype}")
            logger.info(f"   用户: {user_name} ({user_id})")
            logger.info(f"   会话: {chattype} ({chatid})")
            logger.info(f"   请求ID: {req_id}")
            
            # 处理文本消息
            if msgtype == "text":
                text_data = body.get("text", {})
                content = text_data.get("content", "").strip()
                mentioned_list = text_data.get("mentioned_list", [])  # @ 提及列表
                
                print(f"   内容: {content}")
                print(f"   @ 列表: {mentioned_list}")
                print("=" * 60)
                logger.info(f"   内容: {content}")
                logger.info(f"   @ 列表: {mentioned_list}")
                logger.info("=" * 60)
                
                if not content:
                    return
                
                # 群聊消息处理
                if chattype == "group":
                    # 检查是否 @ 了机器人
                    # mentioned_list 包含被 @ 的用户 ID，如果包含机器人 ID 则回复
                    bot_mentioned = False
                    
                    # 检查是否 @ 了机器人（通过 Bot ID 或 @all）
                    if self.config.bot_id in mentioned_list or "@all" in mentioned_list:
                        bot_mentioned = True
                    
                    # 也检查消息内容中是否包含 @机器人名称
                    # 企业微信的 @ 格式通常是 "@机器人名称 消息内容"
                    if content.startswith("@"):
                        bot_mentioned = True
                    
                    if not bot_mentioned:
                        print(f"⏭️  群聊消息未 @ 机器人，忽略")
                        logger.info(f"⏭️  群聊消息未 @ 机器人，忽略")
                        return
                    
                    # 移除消息开头的 @ 提及
                    # 格式: "@机器人名称 实际消息内容"
                    if content.startswith("@"):
                        # 找到第一个空格，移除 @ 部分
                        space_idx = content.find(" ")
                        if space_idx > 0:
                            content = content[space_idx + 1:].strip()
                    
                    print(f"✅ 群聊用户 {user_name} @ 机器人: {content}")
                    logger.info(f"✅ 群聊用户 {user_name} @ 机器人: {content}")
                else:
                    print(f"✅ 单聊用户 {user_name} 发送: {content}")
                    logger.info(f"✅ 单聊用户 {user_name} 发送: {content}")
                
                # 获取或创建 Agent
                print(f"🤖 正在为用户 {user_id} 生成回复...")
                logger.info(f"🤖 正在为用户 {user_id} 生成回复...")
                agent = self._get_user_agent(user_id)
                
                # 生成流式回复
                await self._send_stream_response(req_id, agent, content, chatid, chattype)
            
            # 处理其他消息类型
            elif msgtype in ["image", "file", "voice", "video"]:
                print(f"   类型: {msgtype} (暂不支持)")
                print("=" * 60)
                logger.info(f"   类型: {msgtype} (暂不支持)")
                logger.info("=" * 60)
                await self._send_text_response(
                    req_id,
                    f"收到您的{msgtype}消息，暂不支持处理此类型"
                )
            
        except Exception as e:
            print(f"❌ 处理消息回调失败: {e}")
            logger.error(f"❌ 处理消息回调失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_event_callback(self, data: Dict[str, Any]):
        """处理事件回调"""
        try:
            body = data.get("body", {})
            headers = data.get("headers", {})
            req_id = headers.get("req_id", "")
            
            event = body.get("event", {})
            eventtype = event.get("eventtype", "")
            
            print(f"📨 收到事件回调: {eventtype}")
            logger.info(f"📨 收到事件回调: {eventtype}")
            
            # 进入会话事件
            if eventtype == "enter_chat":
                await self._send_welcome_message(req_id)
            
            # 模板卡片事件
            elif eventtype == "template_card_event":
                print("📨 收到模板卡片事件")
                logger.info("📨 收到模板卡片事件")
                # 可以更新卡片
            
            # 连接断开事件
            elif eventtype == "disconnected_event":
                print("⚠️  收到连接断开事件，旧连接被新连接踢掉")
                logger.warning("⚠️  收到连接断开事件，旧连接被新连接踢掉")
                self.connected = False
            
        except Exception as e:
            print(f"❌ 处理事件回调失败: {e}")
            logger.error(f"❌ 处理事件回调失败: {e}")
    
    async def _send_welcome_message(self, req_id: str):
        """发送欢迎消息"""
        try:
            welcome_msg = {
                "cmd": "aibot_respond_welcome_msg",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "msgtype": "text",
                    "text": {
                        "content": "您好！我是智能助手玲，有什么可以帮助您的吗？"
                    }
                }
            }
            
            await self.ws.send(json.dumps(welcome_msg))
            print("📨 发送欢迎消息")
            logger.info("📨 发送欢迎消息")
            
        except Exception as e:
            print(f"❌ 发送欢迎消息失败: {e}")
            logger.error(f"❌ 发送欢迎消息失败: {e}")
    
    async def _send_text_response(self, req_id: str, content: str):
        """发送普通文本回复"""
        try:
            response_msg = {
                "cmd": "aibot_respond_msg",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "msgtype": "text",
                    "text": {
                        "content": content
                    }
                }
            }
            
            await self.ws.send(json.dumps(response_msg))
            print(f"📤 发送回复: {content[:50]}...")
            logger.info(f"📤 发送回复: {content[:50]}...")
            
        except Exception as e:
            print(f"❌ 发送文本回复失败: {e}")
            logger.error(f"❌ 发送文本回复失败: {e}")
    
    async def _send_stream_response(
        self,
        req_id: str,
        agent: Agent,
        user_message: str,
        chatid: str = "",
        chattype: str = "single"
    ):
        """发送流式回复"""
        try:
            # 生成唯一的 stream_id
            stream_id = self._generate_stream_id()
            
            # 记录流式会话
            self.stream_sessions[stream_id] = req_id
            
            # 首次发送流式消息
            await self._send_stream_chunk(
                req_id,
                stream_id,
                "正在思考...",
                finish=False
            )
            
            # 使用 Agent 生成回复（流式）
            full_response = ""
            
            try:
                # 使用流式生成（Agent.chat 返回生成器，逐字符生成）
                char_buffer = ""
                update_threshold = 5  # 每累积 5 个字符更新一次
                
                for char in agent.chat(user_message, stream=True):
                    full_response += char
                    char_buffer += char
                    
                    # 累积一定字符后再更新，减少网络请求
                    if len(char_buffer) >= update_threshold:
                        await self._send_stream_chunk(
                            req_id,
                            stream_id,
                            full_response,
                            finish=False
                        )
                        char_buffer = ""
                        
                        # 控制更新频率
                        await asyncio.sleep(0.05)
                
                # 完成流式消息
                await self._send_stream_chunk(
                    req_id,
                    stream_id,
                    full_response,
                    finish=True
                )
                
                print(f"✅ 回复完成: {full_response[:80]}...")
                logger.info(f"✅ 回复完成: {full_response[:100]}...")
                
                # 【新增】保存对话到数据库
                # 每次对话后都保存，确保对话历史不丢失
                try:
                    # 获取对话历史并保存到数据库
                    # Agent 的 ContextManager 会自动保存到 MongoDB
                    # 这里我们确保会话信息被持久化
                    session_info = agent.get_session_info()
                    logger.debug(f"对话已保存: session_id={session_info.get('session_id')}, "
                               f"message_count={session_info.get('message_count')}")
                except Exception as save_error:
                    logger.warning(f"保存对话失败: {save_error}")
                
            except Exception as e:
                print(f"❌ Agent 生成回复失败: {e}")
                logger.error(f"❌ Agent 生成回复失败: {e}")
                await self._send_stream_chunk(
                    req_id,
                    stream_id,
                    f"抱歉，处理消息时出现错误: {str(e)}",
                    finish=True
                )
            
            # 清理流式会话
            if stream_id in self.stream_sessions:
                del self.stream_sessions[stream_id]
                
        except Exception as e:
            print(f"❌ 发送流式回复失败: {e}")
            logger.error(f"❌ 发送流式回复失败: {e}")
    
    async def _send_stream_chunk(
        self,
        req_id: str,
        stream_id: str,
        content: str,
        finish: bool = False
    ):
        """发送流式消息块"""
        try:
            stream_msg = {
                "cmd": "aibot_respond_msg",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "msgtype": "stream",
                    "stream": {
                        "id": stream_id,
                        "finish": finish,
                        "content": content
                    }
                }
            }
            
            await self.ws.send(json.dumps(stream_msg))
            
            # 【新增】打印发送的消息（只在完成时打印完整内容）
            if finish:
                print("=" * 60)
                print("📤 发送流式消息 (完成):")
                print(f"   请求ID: {req_id}")
                print(f"   流ID: {stream_id}")
                print(f"   内容: {content[:200]}{'...' if len(content) > 200 else ''}")
                print(f"   完整长度: {len(content)} 字符")
                print("=" * 60)
                logger.info("=" * 60)
                logger.info("📤 发送流式消息 (完成):")
                logger.info(f"   请求ID: {req_id}")
                logger.info(f"   流ID: {stream_id}")
                logger.info(f"   内容: {content[:200]}{'...' if len(content) > 200 else ''}")
                logger.info(f"   完整长度: {len(content)} 字符")
                logger.info("=" * 60)
            else:
                logger.debug(f"📤 发送流式消息块: finish={finish}, len={len(content)}")

        except Exception as e:
            print(f"❌ 发送流式消息块失败: {e}")
            logger.error(f"❌ 发送流式消息块失败: {e}")
    
    async def send_message(
        self,
        chatid: str,
        content: str,
        chat_type: int = 1,
        msgtype: str = "markdown"
    ):
        """
        主动推送消息
        
        Args:
            chatid: 会话 ID（单聊填 userid，群聊填 chatid）
            content: 消息内容
            chat_type: 会话类型（1=单聊，2=群聊）
            msgtype: 消息类型（markdown/template_card）
        """
        try:
            req_id = self._generate_req_id()
            
            send_msg = {
                "cmd": "aibot_send_msg",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "chatid": chatid,
                    "chat_type": chat_type,
                    "msgtype": msgtype
                }
            }
            
            # 添加消息内容
            if msgtype == "markdown":
                send_msg["body"]["markdown"] = {
                    "content": content
                }
            elif msgtype == "text":
                send_msg["body"]["text"] = {
                    "content": content
                }
            
            await self.ws.send(json.dumps(send_msg))
            print(f"📤 主动推送消息到 {chatid}")
            logger.info(f"📤 主动推送消息到 {chatid}")
            
        except Exception as e:
            print(f"❌ 主动推送消息失败: {e}")
            logger.error(f"❌ 主动推送消息失败: {e}")
    
    def _get_user_agent(self, user_id: str) -> Agent:
        """获取或创建用户的 Agent 实例"""
        if user_id not in self.user_agents:
            print("=" * 60)
            print(f"🆕 为用户 {user_id} 创建新的 Agent 会话...")
            print("   正在初始化 Agent（可能需要加载模型，请稍候）...")
            logger.info("=" * 60)
            logger.info(f"🆕 为用户 {user_id} 创建新的 Agent 会话...")
            logger.info("   正在初始化 Agent（可能需要加载模型，请稍候）...")

            # 为新用户创建 Agent
            agent = Agent(
                user_id=f"wework_{user_id}",
                enable_tools=True
            )

            print("   Agent 创建完成，正在启动会话...")
            logger.info("   Agent 创建完成，正在启动会话...")
            agent.start_chat()

            self.user_agents[user_id] = agent
            print(f"✅ 用户 {user_id} 的 Agent 会话已就绪")
            print("=" * 60)
            logger.info(f"✅ 用户 {user_id} 的 Agent 会话已就绪")
            logger.info("=" * 60)
        
        return self.user_agents[user_id]
    
    def _generate_req_id(self) -> str:
        """生成请求 ID"""
        return f"req_{uuid.uuid4().hex[:16]}"
    
    def _generate_stream_id(self) -> str:
        """生成流式消息 ID"""
        return f"stream_{uuid.uuid4().hex[:16]}"
    
    async def disconnect(self):
        """断开连接"""
        try:
            self.running = False
            self.connected = False
            self.subscribed = False
            
            # 取消心跳任务
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            
            # 关闭 WebSocket
            if self.ws:
                await self.ws.close()
            
            print("🔌 WebSocket 连接已断开")
            logger.info("🔌 WebSocket 连接已断开")

        except Exception as e:
            print(f"❌ 断开连接失败: {e}")
            logger.error(f"❌ 断开连接失败: {e}")
    
    async def run_async(self):
        """异步运行（带自动重连）"""
        self.running = True
        reconnect_attempts = 0
        
        while self.running:
            try:
                await self.connect()
                reconnect_attempts = 0  # 重置重连次数
                
            except Exception as e:
                print(f"❌ 连接失败: {e}")
                logger.error(f"❌ 连接失败: {e}")

                if reconnect_attempts >= self.config.max_reconnect_attempts:
                    print("❌ 达到最大重连次数，停止重连")
                    logger.error("❌ 达到最大重连次数，停止重连")
                    break

                reconnect_attempts += 1
                print(f"⏳ 等待 {self.config.reconnect_delay} 秒后重连... (尝试 {reconnect_attempts}/{self.config.max_reconnect_attempts})")
                logger.info(f"⏳ 等待 {self.config.reconnect_delay} 秒后重连... (尝试 {reconnect_attempts}/{self.config.max_reconnect_attempts})")
                await asyncio.sleep(self.config.reconnect_delay)
    
    def run(self):
        """同步运行（在独立线程中运行事件循环）"""
        def run_in_thread():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self.run_async())
            finally:
                self.loop.close()
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        
        print("🚀 企业微信机器人已在后台启动")
        logger.info("🚀 企业微信机器人已在后台启动")
        
        # 等待线程
        try:
            thread.join()
        except KeyboardInterrupt:
            print("👋 用户中断，正在关闭...")
            logger.info("👋 用户中断，正在关闭...")
            self.running = False
            if self.loop:
                asyncio.run_coroutine_threadsafe(self.disconnect(), self.loop)


def main():
    """主函数"""
    import argparse
    from dotenv import load_dotenv
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="企业微信机器人 WebSocket 长连接服务")
    parser.add_argument("--bot-id", help="机器人 ID")
    parser.add_argument("--secret", help="长连接密钥")
    parser.add_argument("--config", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 从环境变量或参数获取配置
    bot_id = args.bot_id or os.getenv("WEWORK_BOT_ID", "")
    secret = args.secret or os.getenv("WEWORK_SECRET", "")
    
    if not bot_id or not secret:
        print("❌ 缺少必要配置: bot_id 和 secret")
        print("请设置环境变量 WEWORK_BOT_ID 和 WEWORK_SECRET")
        print("或使用参数: --bot-id <BOT_ID> --secret <SECRET>")
        logger.error("❌ 缺少必要配置: bot_id 和 secret")
        logger.error("请设置环境变量 WEWORK_BOT_ID 和 WEWORK_SECRET")
        logger.error("或使用参数: --bot-id <BOT_ID> --secret <SECRET>")
        return
    
    # 创建配置
    config = WeWorkConfig(
        bot_id=bot_id,
        secret=secret
    )
    
    # 创建并启动机器人
    bot = WeWorkBotWebSocket(config)
    
    print("=" * 60)
    print("企业微信机器人 WebSocket 长连接版本")
    print("=" * 60)
    print(f"Bot ID: {bot_id}")
    print(f"WebSocket URL: {config.ws_url}")
    print("=" * 60)
    logger.info("=" * 60)
    logger.info("企业微信机器人 WebSocket 长连接版本")
    logger.info("=" * 60)
    logger.info(f"Bot ID: {bot_id}")
    logger.info(f"WebSocket URL: {config.ws_url}")
    logger.info("=" * 60)
    
    bot.run()


if __name__ == "__main__":
    main()
