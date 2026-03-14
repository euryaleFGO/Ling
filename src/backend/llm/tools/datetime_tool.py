"""
日期时间工具
获取当前日期、时间、星期等信息
"""
from datetime import datetime
from typing import List
import calendar

from .base_tool import BaseTool, ToolParameter, ToolResult


class DateTimeTool(BaseTool):
    """日期时间工具"""
    
    @property
    def name(self) -> str:
        return "get_datetime"
    
    @property
    def description(self) -> str:
        return """获取当前日期和时间信息。
当用户询问以下问题时使用此工具：
- 今天几号？今天是几月几日？
- 现在几点了？
- 今天星期几？
- 现在是什么时间？
- 这个月有多少天？"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="info_type",
                type="string",
                description="需要获取的信息类型",
                required=False,
                enum=["full", "date", "time", "weekday", "month_days"],
                default="full"
            )
        ]
    
    def execute(self, info_type: str = "full") -> ToolResult:
        """
        获取日期时间信息
        
        Args:
            info_type: 信息类型
                - full: 完整日期时间
                - date: 仅日期
                - time: 仅时间
                - weekday: 星期几
                - month_days: 本月天数
        """
        try:
            now = datetime.now()
            weekdays = ['一', '二', '三', '四', '五', '六', '日']
            
            if info_type == "date":
                result = {
                    "date": now.strftime("%Y年%m月%d日"),
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                }
            elif info_type == "time":
                result = {
                    "time": now.strftime("%H:%M:%S"),
                    "hour": now.hour,
                    "minute": now.minute,
                    "period": "上午" if now.hour < 12 else ("下午" if now.hour < 18 else "晚上")
                }
            elif info_type == "weekday":
                result = {
                    "weekday": f"星期{weekdays[now.weekday()]}",
                    "weekday_number": now.weekday() + 1,
                    "is_weekend": now.weekday() >= 5
                }
            elif info_type == "month_days":
                _, days = calendar.monthrange(now.year, now.month)
                result = {
                    "month": now.month,
                    "total_days": days,
                    "passed_days": now.day,
                    "remaining_days": days - now.day
                }
            else:  # full
                result = {
                    "datetime": now.strftime("%Y年%m月%d日 %H:%M:%S"),
                    "date": now.strftime("%Y年%m月%d日"),
                    "time": now.strftime("%H:%M"),
                    "weekday": f"星期{weekdays[now.weekday()]}",
                    "period": "上午" if now.hour < 12 else ("下午" if now.hour < 18 else "晚上"),
                    "timestamp": int(now.timestamp())
                }
            
            return ToolResult(success=True, data=result)
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))
