"""
Live2D 动作工具
当用户说「做个挥手动作」「跳一下」等时，Agent 可调用此工具控制角色做相应动作
"""
from typing import List

from .base_tool import BaseTool, ToolParameter, ToolResult


# 自然语言 → Live2D 动作组映射（模型 hiyori 支持的动作）
MOTION_ALIASES = {
    "idle": ["idle", "待机", "待着", "站着", "休息"],
    "Tap@Body": ["挥手", "招手", "抬手", "举手", "嗨", "你好", "再见", "拜拜", "tapbody", "身体轻触", "挥挥手", "招招手"],
    "Tap": ["轻触", "点一下", "tap", "惊讶", "吃惊", "吓一跳"],
    "Flick": ["快速挥", "甩手", "flick", "生气", "不满", "气死"],
    "FlickDown": ["往下挥", "向下", "flickdown", "低头"],
    "Flick@Body": ["身体快速挥", "flickbody", "快速挥手"],
}

# 所有支持的动作组（model3.json 中的 Motions 键）
VALID_GROUPS = ["Idle", "Tap", "Tap@Body", "Flick", "FlickDown", "Flick@Body"]


def resolve_motion(user_input: str) -> str | None:
    """
    将用户说的动作描述解析为动作组名
    支持直接传 group 名或中文/自然语言描述
    """
    s = (user_input or "").strip().lower()
    if not s:
        return None

    # 直接匹配动作组名（忽略大小写）
    for g in VALID_GROUPS:
        if g.lower() == s:
            return g

    # 通过别名映射
    for group, aliases in MOTION_ALIASES.items():
        group_name = group if group.lower() == "idle" else group
        for a in aliases:
            if a in s or s in a:
                return "Idle" if group == "idle" else group_name

    return None


class Live2DMotionTool(BaseTool):
    """Live2D 动作控制工具"""

    @property
    def name(self) -> str:
        return "live2d_motion"

    @property
    def description(self) -> str:
        return """控制 Live2D 角色做动作。
当用户要求角色做某个动作时使用，例如：
- 做个挥手动作、招招手、举个手
- 跳一下、点一下
- 生气、惊讶
支持的动作：Idle(待机)、Tap(轻触)、Tap@Body(挥手)、Flick(快速挥)、FlickDown(向下挥)、Flick@Body(身体快速挥)。
用户说「做个xx动作」「挥手」「招手」等时调用。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="motion",
                type="string",
                description="动作名称。支持：Idle/Tap/Tap@Body/Flick/FlickDown/Flick@Body，或中文：挥手、招手、待机、轻触、快速挥、惊讶、生气",
                required=True,
            ),
            ToolParameter(
                name="index",
                type="number",
                description="同组内动作索引，从0开始。Idle 有3个(0,1,2)，其余多为0。不传则默认0",
                required=False,
                default=0,
            ),
        ]

    def execute(self, motion: str, index: int = 0) -> ToolResult:
        """
        执行 Live2D 动作

        Args:
            motion: 动作组名或中文描述（挥手、招手、待机等）
            index: 组内索引，默认 0
        """
        try:
            group = resolve_motion(motion)
            if not group:
                return ToolResult(
                    success=False,
                    error=f"未知动作「{motion}」。支持: {', '.join(VALID_GROUPS)}，或中文：挥手、招手、待机、轻触、惊讶、生气",
                )

            try:
                from core.message_server import send_motion
                send_motion(group, int(index))
                return ToolResult(success=True, data={"motion": group, "index": int(index)})
            except ImportError:
                return ToolResult(success=False, error="Live2D 未连接，请先启动桌面宠物")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
