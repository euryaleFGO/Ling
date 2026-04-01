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
        return """打开摄像头拍一张照片并保存。
当用户说以下内容时使用：
- 打开摄像头拍照
- 帮我拍张照
- 用摄像头拍一张
- 拍个照看看"""

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
