# -*- coding: utf-8 -*-
"""
提醒/闹钟/行程管理工具
支持设置定时提醒、查看行程、取消行程等操作

提醒数据持久化到 MongoDB，后台线程检查触发。
"""

import threading
import time
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Callable, Dict, Any

from .base_tool import BaseTool, ToolParameter, ToolResult

logger = logging.getLogger("tools.reminder")


class ReminderManager:
    """
    提醒管理器（后台单例）
    
    职责：
    1. 持久化存储提醒到 MongoDB
    2. 后台线程定时检查到期提醒
    3. 触发回调通知用户
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> "ReminderManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self._db = None
        self._collection = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_remind: Optional[Callable] = None  # 提醒触发回调
        self._check_interval = 15  # 每 15 秒检查一次
    
    def initialize(self, db=None):
        """
        初始化，连接 MongoDB
        
        Args:
            db: pymongo Database 实例，如果为 None 则自动连接
        """
        if self._collection is not None:
            return
        
        try:
            if db is None:
                # 优先复用项目统一 MongoDB 配置
                try:
                    from backend.llm.database.mongo_client import get_db
                    db = get_db()
                except Exception:
                    from pymongo import MongoClient
                    from core.settings import AppSettings
                    s = AppSettings.load()
                    client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=3000)
                    db = client[s.mongodb_db]
            
            self._db = db
            self._collection = db["reminders"]
            
            # 创建索引
            self._collection.create_index("trigger_time")
            self._collection.create_index("status")
            
            logger.info("提醒管理器初始化完成")
        except Exception as e:
            logger.error(f"提醒管理器初始化失败: {e}")
            # 回退到内存模式
            self._collection = None
    
    def set_on_remind(self, callback: Callable[[Dict[str, Any]], None]):
        """
        设置提醒触发时的回调
        
        Args:
            callback: 接收提醒字典 {"id", "content", "trigger_time", ...}
        """
        self._on_remind = callback
    
    def start(self):
        """启动后台检查线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True, name="ReminderChecker")
        self._thread.start()
        logger.info("提醒检查线程已启动")
    
    def stop(self):
        """停止后台检查线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
    
    def add_reminder(self, content: str, trigger_time: datetime, label: str = "") -> Dict[str, Any]:
        """
        添加提醒
        
        Args:
            content: 提醒内容
            trigger_time: 触发时间
            label: 标签/分类（可选）
            
        Returns:
            创建的提醒信息
        """
        reminder = {
            "reminder_id": str(uuid.uuid4())[:8],
            "content": content,
            "trigger_time": trigger_time,
            "created_at": datetime.now(),
            "status": "pending",  # pending / triggered / cancelled
            "label": label,
        }
        
        if self._collection is not None:
            self._collection.insert_one(reminder.copy())
        else:
            # 内存模式回退
            if not hasattr(self, '_memory_store'):
                self._memory_store = []
            self._memory_store.append(reminder)
        
        logger.info(f"添加提醒: [{reminder['reminder_id']}] {content} @ {trigger_time}")
        return reminder
    
    def cancel_reminder(self, reminder_id: str = None, keyword: str = None) -> int:
        """
        取消提醒
        
        Args:
            reminder_id: 提醒 ID（精确取消）
            keyword: 关键词模糊匹配取消
            
        Returns:
            取消的提醒数量
        """
        if self._collection is not None:
            query = {"status": "pending"}
            if reminder_id:
                query["reminder_id"] = reminder_id
            elif keyword:
                query["content"] = {"$regex": keyword, "$options": "i"}
            else:
                return 0
            
            result = self._collection.update_many(query, {"$set": {"status": "cancelled"}})
            count = result.modified_count
        else:
            count = 0
            if hasattr(self, '_memory_store'):
                for r in self._memory_store:
                    if r["status"] != "pending":
                        continue
                    if reminder_id and r["reminder_id"] == reminder_id:
                        r["status"] = "cancelled"
                        count += 1
                    elif keyword and keyword in r["content"]:
                        r["status"] = "cancelled"
                        count += 1
        
        logger.info(f"取消提醒: {count} 条")
        return count
    
    def list_reminders(self, include_past: bool = False) -> List[Dict[str, Any]]:
        """
        列出提醒
        
        Args:
            include_past: 是否包含已触发/已取消的
            
        Returns:
            提醒列表
        """
        if self._collection is not None:
            query = {}
            if not include_past:
                query["status"] = "pending"
            
            cursor = self._collection.find(query, {"_id": 0}).sort("trigger_time", 1)
            reminders = list(cursor)
        else:
            reminders = []
            if hasattr(self, '_memory_store'):
                reminders = [r for r in self._memory_store 
                            if include_past or r["status"] == "pending"]
                reminders.sort(key=lambda x: x["trigger_time"])
        
        return reminders
    
    def _check_loop(self):
        """后台循环检查到期提醒"""
        while self._running:
            try:
                self._check_and_trigger()
            except Exception as e:
                logger.error(f"检查提醒时出错: {e}")
            time.sleep(self._check_interval)
    
    def _check_and_trigger(self):
        """检查并触发到期的提醒"""
        now = datetime.now()
        
        if self._collection is not None:
            # 查找所有到期未触发的提醒
            query = {
                "status": "pending",
                "trigger_time": {"$lte": now}
            }
            due_reminders = list(self._collection.find(query, {"_id": 0}))
            
            for reminder in due_reminders:
                self._trigger(reminder)
                self._collection.update_one(
                    {"reminder_id": reminder["reminder_id"]},
                    {"$set": {"status": "triggered"}}
                )
        else:
            if hasattr(self, '_memory_store'):
                for r in self._memory_store:
                    if r["status"] == "pending" and r["trigger_time"] <= now:
                        self._trigger(r)
                        r["status"] = "triggered"
    
    def _trigger(self, reminder: Dict[str, Any]):
        """触发单个提醒"""
        content = reminder.get("content", "")
        logger.info(f"⏰ 提醒触发: {content}")
        
        if self._on_remind:
            try:
                self._on_remind(reminder)
            except Exception as e:
                logger.error(f"提醒回调执行失败: {e}")


class ReminderTool(BaseTool):
    """
    提醒/闹钟/行程管理工具
    
    供 Agent 调用，支持：
    - 设置提醒（绝对时间 / 相对时间）
    - 查看行程
    - 取消行程
    """
    
    def __init__(self):
        self._manager = ReminderManager.get_instance()
    
    @property
    def name(self) -> str:
        return "reminder"
    
    @property
    def description(self) -> str:
        return """管理提醒、闹钟和行程。
使用场景：
1. set: 设置提醒/闹钟。用户说"十分钟后提醒我做XXX"、"下午六点提醒我"、"帮我定一个晚上九点的闹铃"时使用。
2. list: 查看当前所有待触发的提醒/行程。用户说"帮我查看行程"、"我有什么提醒"时使用。
3. cancel: 取消提醒/行程。用户说"取消XXX行程"、"删除那个提醒"时使用。

时间参数说明：
- 相对时间：使用 minutes_later 参数，如"10分钟后" → minutes_later=10
- 绝对时间：使用 absolute_time 参数，格式 "HH:MM" 或 "YYYY-MM-DD HH:MM"
  例如"下午六点" → absolute_time="18:00"
  例如"明天早上八点" → absolute_time="明天 08:00"（会自动解析）
  例如"晚上九点" → absolute_time="21:00"

注意：设置提醒时 content 必填，描述要提醒的事项。"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型：set(设置提醒)、list(查看行程)、cancel(取消提醒)",
                required=True,
                enum=["set", "list", "cancel"]
            ),
            ToolParameter(
                name="content",
                type="string",
                description="提醒内容/事项描述。设置和取消时使用。",
                required=False
            ),
            ToolParameter(
                name="minutes_later",
                type="number",
                description="多少分钟后提醒，用于相对时间。如'10分钟后'→10，'半小时后'→30，'1小时后'→60",
                required=False
            ),
            ToolParameter(
                name="absolute_time",
                type="string",
                description="绝对时间，格式为 'HH:MM' 或 'YYYY-MM-DD HH:MM'。如'下午六点'→'18:00'，'晚上九点'→'21:00'",
                required=False
            ),
            ToolParameter(
                name="reminder_id",
                type="string",
                description="提醒 ID，取消特定提醒时使用",
                required=False
            ),
        ]
    
    def execute(
        self,
        action: str,
        content: str = None,
        minutes_later: float = None,
        absolute_time: str = None,
        reminder_id: str = None,
        **kwargs
    ) -> ToolResult:
        """执行提醒操作"""
        try:
            if action == "set":
                return self._set_reminder(content, minutes_later, absolute_time)
            elif action == "list":
                return self._list_reminders()
            elif action == "cancel":
                return self._cancel_reminder(reminder_id, content)
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
        except Exception as e:
            logger.error(f"提醒工具执行失败: {e}")
            return ToolResult(success=False, error=str(e))
    
    def _set_reminder(self, content: str, minutes_later: float = None, absolute_time: str = None) -> ToolResult:
        """设置提醒"""
        if not content:
            return ToolResult(success=False, error="请提供提醒内容 (content)")
        
        # 解析触发时间
        trigger_time = self._parse_time(minutes_later, absolute_time)
        if trigger_time is None:
            return ToolResult(success=False, error="请提供时间参数 (minutes_later 或 absolute_time)")
        
        now = datetime.now()
        if trigger_time <= now:
            # 如果只给了 HH:MM 且已过今天的这个时间，则设为明天
            if absolute_time and len(absolute_time) <= 5:
                trigger_time += timedelta(days=1)
            else:
                return ToolResult(success=False, error="提醒时间不能是过去的时间")
        
        reminder = self._manager.add_reminder(content, trigger_time)
        
        # 计算距离触发还有多久
        delta = trigger_time - now
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        
        time_desc = ""
        if hours > 0:
            time_desc += f"{hours}小时"
        if minutes > 0:
            time_desc += f"{minutes}分钟"
        if not time_desc:
            time_desc = "不到1分钟"
        
        return ToolResult(
            success=True,
            data={
                "message": f"提醒已设置",
                "reminder_id": reminder["reminder_id"],
                "content": content,
                "trigger_time": trigger_time.strftime("%Y-%m-%d %H:%M"),
                "time_until": f"{time_desc}后触发",
            }
        )
    
    def _list_reminders(self) -> ToolResult:
        """列出提醒"""
        reminders = self._manager.list_reminders(include_past=False)
        
        if not reminders:
            return ToolResult(
                success=True,
                data={"message": "当前没有待触发的提醒", "count": 0, "reminders": []}
            )
        
        now = datetime.now()
        items = []
        for r in reminders:
            trigger_time = r["trigger_time"]
            if isinstance(trigger_time, str):
                trigger_time = datetime.fromisoformat(trigger_time)
            
            delta = trigger_time - now
            total_minutes = int(delta.total_seconds() / 60)
            
            if total_minutes < 0:
                time_desc = "已过期"
            elif total_minutes < 60:
                time_desc = f"{total_minutes}分钟后"
            else:
                hours = total_minutes // 60
                mins = total_minutes % 60
                time_desc = f"{hours}小时{mins}分钟后" if mins else f"{hours}小时后"
            
            items.append({
                "id": r["reminder_id"],
                "content": r["content"],
                "time": trigger_time.strftime("%m-%d %H:%M"),
                "countdown": time_desc,
            })
        
        return ToolResult(
            success=True,
            data={
                "message": f"共 {len(items)} 条待触发提醒",
                "count": len(items),
                "reminders": items,
            }
        )
    
    def _cancel_reminder(self, reminder_id: str = None, keyword: str = None) -> ToolResult:
        """取消提醒"""
        if not reminder_id and not keyword:
            return ToolResult(success=False, error="请提供提醒 ID 或关键词来取消提醒")
        
        count = self._manager.cancel_reminder(reminder_id=reminder_id, keyword=keyword)
        
        if count == 0:
            return ToolResult(
                success=True,
                data={"message": "没有找到匹配的提醒", "cancelled_count": 0}
            )
        
        return ToolResult(
            success=True,
            data={"message": f"已取消 {count} 条提醒", "cancelled_count": count}
        )
    
    def _parse_time(self, minutes_later: float = None, absolute_time: str = None) -> Optional[datetime]:
        """
        解析时间参数
        
        Args:
            minutes_later: 相对分钟数
            absolute_time: 绝对时间字符串
            
        Returns:
            datetime 对象
        """
        now = datetime.now()
        
        # 优先相对时间
        if minutes_later is not None:
            return now + timedelta(minutes=float(minutes_later))
        
        if absolute_time is None:
            return None
        
        absolute_time = absolute_time.strip()
        
        # 处理 "明天 HH:MM" 格式
        if absolute_time.startswith("明天"):
            time_part = absolute_time.replace("明天", "").strip()
            try:
                t = datetime.strptime(time_part, "%H:%M")
                return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0) + timedelta(days=1)
            except ValueError:
                pass
        
        # 处理 "后天 HH:MM" 格式
        if absolute_time.startswith("后天"):
            time_part = absolute_time.replace("后天", "").strip()
            try:
                t = datetime.strptime(time_part, "%H:%M")
                return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0) + timedelta(days=2)
            except ValueError:
                pass
        
        # 尝试完整格式 YYYY-MM-DD HH:MM
        try:
            return datetime.strptime(absolute_time, "%Y-%m-%d %H:%M")
        except ValueError:
            pass
        
        # 尝试 MM-DD HH:MM
        try:
            t = datetime.strptime(absolute_time, "%m-%d %H:%M")
            return t.replace(year=now.year)
        except ValueError:
            pass
        
        # 尝试 HH:MM
        try:
            t = datetime.strptime(absolute_time, "%H:%M")
            return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        except ValueError:
            pass
        
        return None
