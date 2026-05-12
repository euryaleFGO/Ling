"""
摄像头拍照工具
从默认摄像头抓拍一张照片并保存到 data/camera 目录。
"""

from __future__ import annotations

from datetime import datetime
from typing import List
import os

from .base_tool import BaseTool, ToolParameter, ToolResult


class CameraCaptureTool(BaseTool):
    """摄像头拍照工具"""

    def __init__(self, default_save_dir: str = "data/camera"):
        self._default_save_dir = default_save_dir
        os.makedirs(default_save_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return "camera_capture"

    @property
    def description(self) -> str:
        return """打开本机摄像头拍照并保存到 data/camera。
当用户要打开摄像头、拍照、拍张照、打开摄像等时使用。
语音识别可能把「说吧」听成「闻吧」、「帮我」听成「屏报」；只要语义是「用摄像头拍」就调用本工具。
用户要「截屏/截桌面/分析当前窗口」时用 screenshot_analyze，不要用网络搜索。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filename",
                type="string",
                description="保存文件名（不含路径），留空则自动按时间戳命名",
                required=False,
                default="",
            ),
            ToolParameter(
                name="camera_index",
                type="number",
                description="摄像头编号，默认 0",
                required=False,
                default=0,
            ),
        ]

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Strip path separators to prevent directory traversal."""
        filename = os.path.basename(filename)
        import re
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        return filename

    def execute(self, filename: str = "", camera_index: int = 0) -> ToolResult:
        try:
            import cv2
            import time
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 opencv-python: pip install opencv-python",
            )

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"camera_{timestamp}.jpg"

        # Sanitize to prevent path traversal
        filename = self._sanitize_filename(filename)

        if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            filename += ".jpg"

        save_path = os.path.join(self._default_save_dir, filename)

        cap = cv2.VideoCapture(int(camera_index), cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            return ToolResult(success=False, error=f"无法打开摄像头 index={camera_index}")

        # 让摄像头曝光稳定一下
        time.sleep(0.3)
        ok, frame = cap.read()
        cap.release()

        if not ok or frame is None:
            return ToolResult(success=False, error="摄像头读取失败")

        saved = cv2.imwrite(save_path, frame)
        if not saved:
            return ToolResult(success=False, error=f"保存失败: {save_path}")

        return ToolResult(
            success=True,
            data={
                "message": "拍照已保存",
                "path": save_path,
                "filename": filename,
                "camera_index": int(camera_index),
            },
        )
