# -*- coding: utf-8 -*-
"""
Bot 基类 - 统一 Agent 池管理与自动清理

所有 Bot 继承此基类，获得:
- 用户 Agent 的创建/获取/清理
- 定期清理不活跃 Agent（防内存泄漏）
- 统一的生命周期管理
"""

import time
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, Optional

from backend.llm.agent.agent import Agent

logger = logging.getLogger(__name__)


class BaseBot(ABC):
    """
    Bot 基类

    子类只需实现各自的通信协议（Webhook、WebSocket 等），
    Agent 池管理由基类统一处理。

    使用示例:
        class MyBot(BaseBot):
            def _create_agent(self, user_id: str) -> Agent:
                agent = Agent(user_id=f"my_{user_id}", enable_tools=True)
                agent.start_chat()
                return agent

            async def start(self):
                ...

            async def stop(self):
                ...
    """

    def __init__(
        self,
        agent_id_prefix: str = "",
        max_idle_seconds: int = 3600,
        cleanup_interval_seconds: int = 300,
    ):
        """
        Args:
            agent_id_prefix: Agent ID 前缀（如 "wework_", "ws_"）
            max_idle_seconds: Agent 最大空闲时间（秒），超过则自动清理
            cleanup_interval_seconds: 清理检查间隔（秒）
        """
        self.agent_id_prefix = agent_id_prefix
        self._max_idle_seconds = max_idle_seconds
        self._cleanup_interval = cleanup_interval_seconds

        # Agent 池: user_id -> Agent
        self.user_agents: Dict[str, Agent] = {}
        # 最后活跃时间: user_id -> timestamp
        self._last_active: Dict[str, float] = {}

        # 后台清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_running = False

    def _create_agent(self, user_id: str) -> Agent:
        """
        创建新的 Agent 实例（子类可覆写以定制 Agent 配置）

        Args:
            user_id: 用户 ID

        Returns:
            新创建的 Agent 实例
        """
        agent = Agent(
            user_id=f"{self.agent_id_prefix}{user_id}",
            enable_tools=True,
        )
        agent.start_chat()
        return agent

    def get_or_create_agent(self, user_id: str) -> Agent:
        """
        获取或创建用户的 Agent 实例

        Args:
            user_id: 用户 ID

        Returns:
            Agent 实例
        """
        self._last_active[user_id] = time.time()

        if user_id not in self.user_agents:
            agent = self._create_agent(user_id)
            self.user_agents[user_id] = agent
            logger.info("为用户 %s 创建新的 Agent 会话", user_id)

        return self.user_agents[user_id]

    def remove_agent(self, user_id: str) -> bool:
        """
        移除指定用户的 Agent

        Args:
            user_id: 用户 ID

        Returns:
            是否成功移除
        """
        if user_id in self.user_agents:
            del self.user_agents[user_id]
            self._last_active.pop(user_id, None)
            logger.info("已清理用户 %s 的 Agent 会话", user_id)
            return True
        return False

    def cleanup_inactive_agents(self):
        """清理超过最大空闲时间的 Agent"""
        now = time.time()
        inactive = [
            uid
            for uid, ts in self._last_active.items()
            if now - ts > self._max_idle_seconds
        ]
        for uid in inactive:
            self.remove_agent(uid)

        if inactive:
            logger.info("清理了 %d 个不活跃的 Agent 会话", len(inactive))

    def _cleanup_loop(self):
        """后台清理循环"""
        while self._cleanup_running:
            try:
                self.cleanup_inactive_agents()
            except Exception as e:
                logger.debug("Agent 清理异常: %s", e)

            # 使用 Event 实现可中断的 sleep
            self._cleanup_event.wait(self._cleanup_interval)

    def start_cleanup_thread(self):
        """启动后台清理线程"""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return

        self._cleanup_running = True
        self._cleanup_event = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name=f"{self.__class__.__name__}-cleanup",
        )
        self._cleanup_thread.start()
        logger.info(
            "Agent 自动清理已启动（间隔 %ds，空闲超时 %ds）",
            self._cleanup_interval,
            self._max_idle_seconds,
        )

    def stop_cleanup_thread(self):
        """停止后台清理线程"""
        self._cleanup_running = False
        if hasattr(self, "_cleanup_event"):
            self._cleanup_event.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        self._cleanup_thread = None

    def get_active_user_count(self) -> int:
        """获取当前活跃用户数"""
        return len(self.user_agents)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "active_users": len(self.user_agents),
            "user_ids": list(self.user_agents.keys()),
        }

    def shutdown(self):
        """关闭 Bot，清理所有资源"""
        self.stop_cleanup_thread()
        for uid in list(self.user_agents.keys()):
            self.remove_agent(uid)
        logger.info("%s 已关闭", self.__class__.__name__)
