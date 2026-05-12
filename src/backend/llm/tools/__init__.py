"""
工具系统
提供各种工具供 Agent 调用
"""
from .base_tool import BaseTool, ToolResult
from .datetime_tool import DateTimeTool
from .memory_tool import MemoryTool
from .summary_tool import SummaryTool
from .screenshot_tool import ScreenshotTool
from .camera_tool import CameraCaptureTool
from .file_tool import FileWriteTool, FileReadTool
from .browser_search_tool import BrowserSearchTool
from .vision_tool import VisionTool, ScreenshotAnalyzeTool
from .reminder_tool import ReminderTool, ReminderManager
from .live2d_motion_tool import Live2DMotionTool
from .exit_app_tool import ExitAppTool
from .terminal_tool import TerminalExecuteTool
from .skill_generator_tool import SkillGeneratorTool
from .diagnose_tool import DiagnoseTool
from .auto_fix_tool import AutoFixTool
from .code_modify_tool import CodeModifyTool
from .speaker_manage_tool import SpeakerManageTool
from .song_tool import SongTool
from .web_search_tool import WebSearchTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "DateTimeTool",
    "MemoryTool",
    "SummaryTool",
    "ScreenshotTool",
    "CameraCaptureTool",
    "FileWriteTool",
    "FileReadTool",
    "BrowserSearchTool",
    "VisionTool",
    "ScreenshotAnalyzeTool",
    "ReminderTool",
    "ReminderManager",
    "Live2DMotionTool",
    "ExitAppTool",
    "TerminalExecuteTool",
    "SkillGeneratorTool",
    "DiagnoseTool",
    "AutoFixTool",
    "CodeModifyTool",
    "SpeakerManageTool",
    "SongTool",
    "WebSearchTool",
]
