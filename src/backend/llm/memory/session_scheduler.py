"""
会话定时轮转调度器

每天凌晨 4 点自动结束旧会话、开启新会话，
并将上一会话摘要注入新会话上下文。
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class SessionScheduler:
    """会话定时轮转调度器"""

    def __init__(
        self,
        agent=None,
        context_manager=None,
        schedule_time: str = "04:00",
        enabled: bool = False
    ):
        self._agent = agent
        self._context_manager = context_manager
        self.schedule_time = schedule_time
        self.enabled = enabled

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_session_rotated: Optional[Callable] = None
        self._loop = None  # asyncio event loop reference

    def set_loop(self, loop):
        """设置事件循环引用（由 AsyncConversationManager 调用）"""
        self._loop = loop

    def start(self):
        """启动调度器"""
        if not self.enabled:
            logger.info("[会话调度] 未启用，跳过启动")
            return

        if self._thread and self._thread.is_alive():
            logger.warning("[会话调度] 调度器已在运行")
            return

        logger.info(f"[会话调度] 启动调度器 (时间: {self.schedule_time})")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="SessionScheduler"
        )
        self._thread.start()

    def stop(self):
        """停止调度器"""
        logger.info("[会话调度] 停止调度器")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def run_now(self):
        """立即执行一次会话轮转"""
        logger.info("[会话调度] 手动触发会话轮转")
        self._rotate_session()

    def _run_loop(self):
        """调度主循环"""
        try:
            import schedule as schedule_lib
        except ImportError:
            logger.error("[会话调度] 需要安装 schedule 库: pip install schedule")
            return

        schedule_lib.every().day.at(self.schedule_time).do(self._rotate_session)

        while not self._stop_event.is_set():
            schedule_lib.run_pending()
            time.sleep(30)

    def _rotate_session(self):
        """执行会话轮转：结束旧会话 → 提取摘要 → 开启新会话"""
        try:
            if not self._agent or not self._context_manager:
                logger.warning("[会话调度] Agent 或 ContextManager 未设置")
                return

            # 如果 Agent 正在处理对话，延迟轮转
            if hasattr(self._agent, '_chat_lock') and self._agent._chat_lock.locked():
                logger.info("[会话调度] Agent 正在处理对话，延迟 60 秒后重试")
                import schedule as schedule_lib
                schedule_lib.every(60).seconds.do(self._rotate_session).tag('_deferred')
                return

            logger.info("[会话调度] 开始会话轮转...")

            # 1. 结束当前会话，生成摘要
            previous_summary = None
            if self._context_manager.session_id:
                try:
                    old_session_id = self._context_manager.session_id
                    self._agent.end_chat(auto_summarize=True)

                    session = self._context_manager._conversation_dao.get_session(
                        old_session_id
                    )
                    if session:
                        previous_summary = session.get("summary")

                except Exception as e:
                    logger.error(f"[会话调度] 结束会话失败: {e}")
                    self._context_manager.end_session(summary="自动轮转（异常）")

            # 2. 开始新会话，注入上一会话摘要
            new_session_id = self._context_manager.start_session(
                previous_summary=previous_summary
            )

            # 3. 清除 Agent 的 system prompt 缓存
            if hasattr(self._agent, '_context_manager'):
                self._agent._context_manager.clear_cache()

            logger.info(
                f"[会话调度] 会话轮转完成: 新会话 {new_session_id}, "
                f"上一会话摘要长度: {len(previous_summary) if previous_summary else 0}"
            )

            if self._on_session_rotated:
                self._on_session_rotated(new_session_id, previous_summary)

            # 清理延迟重试的 job
            try:
                import schedule as schedule_lib
                schedule_lib.clear('_deferred')
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[会话调度] 会话轮转失败: {e}", exc_info=True)


# 全局实例
_session_scheduler: Optional[SessionScheduler] = None
_session_scheduler_lock = threading.Lock()


def get_session_scheduler(**kwargs) -> SessionScheduler:
    """获取会话调度器实例（线程安全）"""
    global _session_scheduler
    if _session_scheduler is None:
        with _session_scheduler_lock:
            if _session_scheduler is None:
                _session_scheduler = SessionScheduler(**kwargs)
    return _session_scheduler


def start_session_scheduler(
    agent=None,
    context_manager=None,
    schedule_time: str = "04:00",
    enabled: bool = True
) -> SessionScheduler:
    """启动会话调度器（便捷函数）"""
    scheduler = get_session_scheduler(
        agent=agent,
        context_manager=context_manager,
        schedule_time=schedule_time,
        enabled=enabled
    )
    scheduler.start()
    return scheduler
