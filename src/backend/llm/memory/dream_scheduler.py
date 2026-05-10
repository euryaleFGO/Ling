"""
梦境整合调度器

定时运行梦境整合任务，类似 OpenClaw 的 cron 调度
"""

import logging
import time
import threading
from datetime import datetime
from typing import Optional, Callable

from .dream_consolidation import run_dream_consolidation

logger = logging.getLogger(__name__)


class DreamScheduler:
    """梦境整合调度器"""
    
    def __init__(
        self,
        user_id: str = "default_user",
        schedule_time: str = "03:00",  # 默认凌晨 3 点
        days_back: int = 7,
        enabled: bool = False
    ):
        self.user_id = user_id
        self.schedule_time = schedule_time
        self.days_back = days_back
        self.enabled = enabled
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 回调函数
        self.on_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
    
    def start(self):
        """启动调度器"""
        if not self.enabled:
            logger.info("[梦境调度] 未启用，跳过启动")
            return
        
        if self._thread and self._thread.is_alive():
            logger.warning("[梦境调度] 调度器已在运行")
            return
        
        logger.info(f"[梦境调度] 启动调度器 (时间: {self.schedule_time})")

        # 在后台线程运行
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()
    
    def stop(self):
        """停止调度器"""
        logger.info("[梦境调度] 停止调度器")
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
    
    def run_now(self):
        """立即运行一次（手动触发）"""
        logger.info("[梦境调度] 手动触发梦境整合")
        self._run_consolidation()
    
    def _run_scheduler(self):
        """调度器主循环"""
        try:
            import schedule as schedule_lib
        except ImportError:
            logger.error("[梦境调度] 需要安装 schedule 库: pip install schedule")
            return

        # 设置定时任务
        schedule_lib.every().day.at(self.schedule_time).do(self._run_consolidation)

        while not self._stop_event.is_set():
            schedule_lib.run_pending()
            time.sleep(60)  # 每分钟检查一次
    
    def _run_consolidation(self):
        """运行梦境整合"""
        try:
            logger.info(f"[梦境调度] 开始梦境整合 (用户: {self.user_id})")
            
            result = run_dream_consolidation(
                user_id=self.user_id,
                days_back=self.days_back
            )
            
            logger.info(f"[梦境调度] 梦境整合完成: {result}")
            
            # 调用回调
            if self.on_complete:
                self.on_complete(result)
        
        except Exception as e:
            logger.error(f"[梦境调度] 梦境整合失败: {e}", exc_info=True)
            
            # 调用错误回调
            if self.on_error:
                self.on_error(e)


# 全局调度器实例
_scheduler: Optional[DreamScheduler] = None
_scheduler_lock = threading.Lock()


def get_dream_scheduler(
    user_id: str = "default_user",
    **kwargs
) -> DreamScheduler:
    """获取梦境调度器实例（线程安全）"""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = DreamScheduler(user_id=user_id, **kwargs)
    return _scheduler


def start_dream_scheduler(
    user_id: str = "default_user",
    schedule_time: str = "03:00",
    days_back: int = 7,
    enabled: bool = True
):
    """启动梦境调度器（便捷函数）"""
    scheduler = get_dream_scheduler(
        user_id=user_id,
        schedule_time=schedule_time,
        days_back=days_back,
        enabled=enabled
    )
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    scheduler = DreamScheduler(
        user_id="test_user",
        schedule_time="03:00",
        enabled=True
    )
    
    # 立即运行一次测试
    scheduler.run_now()
