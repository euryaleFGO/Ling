# -*- coding: utf-8 -*-
"""
说话人管理工具

功能：
- 当用户说出自己的名字时，Agent 调用此工具注册或改名
- 列出所有已注册的说话人
"""

from .base_tool import BaseTool, ToolResult, ToolParameter


class SpeakerManageTool(BaseTool):
    """说话人管理工具"""

    def __init__(self):
        self._speaker_manager = None  # 由 Agent 注入
        self._current_speaker_id = None  # 由 Agent 注入当前说话人

    def set_speaker_manager(self, speaker_manager):
        """注入 SpeakerManager 引用"""
        self._speaker_manager = speaker_manager

    def set_current_speaker(self, speaker_id: str):
        """注入当前说话人 ID（由 Agent 在每次对话时调用）"""
        self._current_speaker_id = speaker_id

    @property
    def name(self) -> str:
        return "manage_speaker"

    @property
    def description(self) -> str:
        return "管理说话人。当用户说出自己的名字时，用此工具注册或改名。也可以列出所有已注册的说话人。"

    @property
    def parameters(self):
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型：rename（改名）或 list（列出所有说话人）",
                required=True,
                enum=["rename", "list"],
            ),
            ToolParameter(
                name="new_name",
                type="string",
                description="用户说出的名字（rename 时必填）",
                required=False,
            ),
            ToolParameter(
                name="speaker_id",
                type="string",
                description="要改名的说话人ID（可选，默认当前说话人）",
                required=False,
            ),
        ]

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        new_name = kwargs.get("new_name")
        speaker_id = kwargs.get("speaker_id")

        if not self._speaker_manager:
            return ToolResult(
                success=False,
                error="说话人管理器未初始化",
            )

        if action == "rename":
            return self._handle_rename(speaker_id, new_name)
        elif action == "list":
            return self._handle_list()
        else:
            return ToolResult(
                success=False,
                error=f"未知操作: {action}",
            )

    def _handle_rename(self, speaker_id: str, new_name: str) -> ToolResult:
        if not new_name:
            return ToolResult(
                success=False,
                error="请提供用户的名字（new_name 参数必填）",
            )

        # 如果没有指定 speaker_id，使用当前说话人
        if not speaker_id:
            # 从 SpeakerManager 获取当前说话人（需要外部设置）
            speaker_id = getattr(self, '_current_speaker_id', None)
            if not speaker_id:
                return ToolResult(
                    success=False,
                    error="无法确定当前说话人，请指定 speaker_id",
                )

        success = self._speaker_manager.rename_speaker(speaker_id, new_name)
        if success:
            return ToolResult(
                success=True,
                data={
                    "action": "rename",
                    "old_id": speaker_id,
                    "new_name": new_name,
                    "message": f"已将 {speaker_id} 改名为 {new_name}",
                },
            )
        else:
            return ToolResult(
                success=False,
                error=f"改名失败：{speaker_id} -> {new_name}",
            )

    def _handle_list(self) -> ToolResult:
        speakers = self._speaker_manager.list_speakers()
        speaker_list = []
        for s in speakers:
            speaker_list.append({
                "speaker_id": s.speaker_id,
                "speaker_name": s.speaker_name,
                "registered_at": s.registered_at.isoformat(),
                "quality": s.voiceprint_quality,
                "is_unknown": s.metadata.get("is_unknown", False),
            })

        return ToolResult(
            success=True,
            data={
                "action": "list",
                "count": len(speaker_list),
                "speakers": speaker_list,
            },
        )
