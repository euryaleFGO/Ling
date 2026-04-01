"""
退出应用工具

当用户表达告别或要求结束会话时，Agent 可调用该工具触发程序优雅退出。
"""

from __future__ import annotations

from typing import List

from .base_tool import BaseTool, ToolParameter, ToolResult


class ExitAppTool(BaseTool):
    """请求应用在当前回复播报后退出。"""

    @property
    def name(self) -> str:
        return "exit_app"

    @property
    def description(self) -> str:
        return (
            "当用户明确表达要结束对话、退出程序、告别离开时调用。"
            "例如：你退下吧、你能自己关机吗、再见、拜拜、byebye、明天见、晚安、早点睡觉。"
            "注意：这是退出当前应用，不是关闭电脑系统。"
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="reason",
                type="string",
                description="退出原因或触发该行为的用户原话摘要",
                required=False,
                default="用户告别，准备退出应用",
            )
        ]

    def execute(self, **kwargs) -> ToolResult:
        reason = kwargs.get("reason", "用户告别，准备退出应用")
        try:
            from core.exit_signal import request_exit

            request_exit(reason=reason)
            return ToolResult(
                success=True,
                data={
                    "message": "已收到退出请求。系统会在本轮语音播报完成后自动退出程序。",
                    "reason": reason,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"触发退出失败: {e}")
