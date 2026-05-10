"""
设置管理主窗口
左侧导航栏 + 右侧内容区 + 底部聊天面板
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QStackedWidget, QLabel,
    QFrame, QSizePolicy, QTextEdit, QLineEdit, QSplitter
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QTextCursor
from pathlib import Path

from gui.pages import (
    CharacterPage, ApiPage, DatabasePage, SpeakerPage, GeneralPage, AsrPage,
    TtsPage, AudioPage, ModelsPage, ServicesPage,
)
import platform
import subprocess
import time


class MainWindow(QMainWindow):
    """设置管理主窗口"""

    # 配置保存信号（section 名称，如 "asr"、"tts"）
    config_saved = pyqtSignal(str)
    # 聊天输入信号（线程安全，从 GUI 线程发到对话管理器）
    chat_text_submitted = pyqtSignal(str)
    # 聊天消息接收信号（线程安全，从对话线程发到 GUI 线程）
    chat_message_received = pyqtSignal(str, str, str)  # sender, message, color

    def __init__(self, show_chat: bool = False):
        super().__init__()
        self.setWindowTitle("玲 - 设置管理")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        self._show_chat = show_chat

        # 加载样式
        self.load_style()

        # 连接消息信号到显示方法（线程安全）
        self.chat_message_received.connect(self.append_chat_message)

        # 初始化 UI
        self.init_ui()

    def load_style(self):
        """加载 QSS 样式表"""
        style_path = Path(__file__).parent / "styles" / "style.qss"
        if style_path.exists():
            with open(style_path, 'r', encoding='utf-8') as f:
                self.setStyleSheet(f.read())

    def init_ui(self):
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)

        # 主布局（水平）
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧导航栏
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)

        # 右侧内容区（垂直分割：设置页 + 聊天面板）
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        if self._show_chat:
            # 分割器：设置页在上，聊天在下
            self._splitter = QSplitter(Qt.Orientation.Vertical)

            # 设置页面
            self.content_stack = QStackedWidget()
            self.content_stack.setObjectName("content")

            # 添加页面
            self.pages = {
                'character': CharacterPage(),
                'api': ApiPage(),
                'asr': AsrPage(),
                'tts': TtsPage(),
                'audio': AudioPage(),
                'models': ModelsPage(),
                'services': ServicesPage(),
                'database': DatabasePage(),
                'speaker': SpeakerPage(),
                'general': GeneralPage(),
            }

            for page in self.pages.values():
                self.content_stack.addWidget(page)

            self._splitter.addWidget(self.content_stack)

            # 聊天面板
            chat_panel = self._create_chat_panel()
            self._splitter.addWidget(chat_panel)

            # 设置分割比例（设置页占 65%，聊天占 35%）
            self._splitter.setSizes([650, 350])

            right_layout.addWidget(self._splitter)
        else:
            # 无聊天模式
            self.content_stack = QStackedWidget()
            self.content_stack.setObjectName("content")

            self.pages = {
                'character': CharacterPage(),
                'api': ApiPage(),
                'asr': AsrPage(),
                'tts': TtsPage(),
                'audio': AudioPage(),
                'models': ModelsPage(),
                'services': ServicesPage(),
                'database': DatabasePage(),
                'speaker': SpeakerPage(),
                'general': GeneralPage(),
            }

            for page in self.pages.values():
                self.content_stack.addWidget(page)

            right_layout.addWidget(self.content_stack)

        main_layout.addWidget(right_panel, 1)

        # 默认显示角色设定页
        self.switch_page('character')

    def _create_chat_panel(self) -> QWidget:
        """创建聊天面板"""
        panel = QFrame()
        panel.setObjectName("chatPanel")
        panel.setStyleSheet("""
            #chatPanel {
                background-color: #1e1e2e;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel("聊天")
        title.setStyleSheet("color: #a5d6a7; font-size: 14px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # 消息显示区
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #12121a;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }
        """)
        layout.addWidget(self._chat_display, 1)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入消息，按 Enter 发送...")
        self._chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a3a;
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #a5d6a7;
            }
        """)
        self._chat_input.returnPressed.connect(self._on_send_message)
        input_layout.addWidget(self._chat_input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedWidth(60)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a6741;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a7751;
            }
            QPushButton:pressed {
                background-color: #3a5731;
            }
        """)
        self._send_btn.clicked.connect(self._on_send_message)
        input_layout.addWidget(self._send_btn)

        layout.addLayout(input_layout)

        return panel

    def _on_send_message(self):
        """发送聊天消息"""
        text = self._chat_input.text().strip()
        if not text:
            return

        self._chat_input.clear()

        # 显示用户消息
        self.append_chat_message("你", text, "#90caf9")

        # 通过信号发送到对话管理器（线程安全）
        self.chat_text_submitted.emit(text)

    def append_chat_message(self, sender: str, message: str, color: str = "#e0e0e0"):
        """在聊天面板追加一条消息"""
        if not hasattr(self, '_chat_display'):
            return
        html = f'<p style="margin: 2px 0;"><span style="color: {color}; font-weight: bold;">{sender}:</span> <span style="color: #e0e0e0;">{message}</span></p>'
        self._chat_display.append(html)
        # 滚动到底部
        cursor = self._chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._chat_display.setTextCursor(cursor)

    def clear_chat_display(self):
        """清空聊天显示"""
        if hasattr(self, '_chat_display'):
            self._chat_display.clear()

    def ensure_mongodb_service(self):
        """非阻塞地检查并启动 MongoDB"""
        from PyQt6.QtCore import QThread, pyqtSignal

        # Read host/port from ConfigManager (M11 fix — not from hardcoded GUI widgets)
        host = 'localhost'
        port = 27017
        try:
            from core.config_manager import get_config_manager
            cfg = get_config_manager().config
            uri = cfg.mongodb.uri or "mongodb://localhost:27017"
            tail = uri.split("://", 1)[1] if "://" in uri else uri
            host_port = tail.split("/", 1)[0]
            if ":" in host_port:
                h, p = host_port.rsplit(":", 1)
                host = h or 'localhost'
                port = int(p)
            else:
                host = host_port or 'localhost'
        except Exception:
            logger.warning("Failed to read MongoDB host/port from ConfigManager, using defaults")

        class MongoCheckThread(QThread):
            """后台线程执行 MongoDB 检查与启动"""
            finished = pyqtSignal()

            def __init__(self, outer, host, port):
                super().__init__()
                self._outer = outer
                self._host = host
                self._port = port

            def run(self):
                try:
                    if platform.system() != "Windows":
                        return

                    # 只处理本地 MongoDB
                    if self._host not in ("localhost", "127.0.0.1") or self._port != 27017:
                        return

                    # 首先检查 MongoDB 是否在运行
                    if self._outer._is_mongodb_running():
                        return

                    # 检查是否有 Windows 服务 (hardcoded whitelist, safe from injection)
                    names = ["MongoDB", "MongoDB Server", "mongodb"]
                    for name in names:
                        try:
                            # Pass service name as PowerShell argument to avoid injection (Fix 6.2)
                            status = subprocess.run([
                                "powershell", "-NoProfile", "-Command",
                                "& { param($n); (Get-Service -Name $n -ErrorAction SilentlyContinue).Status }",
                                name
                            ], capture_output=True, text=True, timeout=5)

                            out = (status.stdout or "").strip()
                            if out and out.lower() == "running":
                                return
                            elif out and out.lower() != "running":
                                try:
                                    subprocess.run([
                                        "powershell", "-NoProfile", "-Command",
                                        "& { param($n); Start-Service -Name $n }",
                                        name
                                    ], capture_output=True, text=True, timeout=15, check=True)
                                    time.sleep(2)
                                    if self._outer._is_mongodb_running():
                                        return
                                except subprocess.CalledProcessError:
                                    break
                        except Exception:
                            logger.debug("Failed to query service '%s', trying next", name)
                            continue

                    # 如果没有服务或服务启动失败，直接启动 MongoDB 进程
                    self._outer._start_mongodb_process()
                except Exception:
                    logger.error("Failed to ensure MongoDB service is running", exc_info=True)

        self._mongo_check_thread = MongoCheckThread(self, host, port)
        self._mongo_check_thread.finished.connect(self._mongo_check_thread.deleteLater)
        self._mongo_check_thread.start()

    def _is_mongodb_running(self):
        """检查 MongoDB 是否在运行（通过进程和端口）"""
        try:
            expected_port = 27017
            try:
                from core.config_manager import get_config_manager
                cfg = get_config_manager().config
                if cfg.mongodb.uri and "://" in cfg.mongodb.uri:
                    tail = cfg.mongodb.uri.split("://", 1)[1]
                    host_port = tail.split("/", 1)[0]
                    if ":" in host_port:
                        expected_port = int(host_port.rsplit(":", 1)[1])
            except Exception:
                logger.debug("Failed to parse MongoDB port from ConfigManager, using default 27017")
                expected_port = 27017

            # 检查进程
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mongod.exe"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "mongod.exe" in result.stdout:
                # 再检查端口是否在监听
                port_check = subprocess.run(
                    ["netstat", "-an"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if f":{expected_port}" in port_check.stdout and "LISTENING" in port_check.stdout:
                    return True
        except Exception:
            logger.debug("Failed to check if MongoDB is running", exc_info=True)
        return False

    def _start_mongodb_process(self):
        """启动 MongoDB 进程"""
        mongod_exe_env = os.environ.get("MONGOD_EXE", "").strip()
        mongod_cfg_env = os.environ.get("MONGOD_CFG", "").strip()
        if not mongod_exe_env:
            return
        mongod_exe = Path(mongod_exe_env)
        config_file = Path(mongod_cfg_env) if mongod_cfg_env else None

        if not mongod_exe.exists():
            return

        try:
            # Use direct subprocess.Popen with argument list to avoid command injection (Fix 6.2)
            cmd = [str(mongod_exe)]
            if config_file and config_file.exists():
                cmd.extend(["--config", str(config_file)])

            # Start with CREATE_NO_WINDOW on Windows to hide the console
            popen_kwargs = {}
            if platform.system() == "Windows":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            subprocess.Popen(cmd, **popen_kwargs)

            # 等待几秒让 MongoDB 启动
            for _ in range(5):
                time.sleep(1)
                if self._is_mongodb_running():
                    return
        except Exception:
            logger.error("Failed to start MongoDB process", exc_info=True)

    def create_sidebar(self) -> QWidget:
        """创建左侧导航栏"""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo/标题区域
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 35, 20, 35)

        title = QLabel("玲")
        title.setObjectName("sidebarTitle")
        title.setStyleSheet("""
            font-size: 42px;
            font-weight: bold;
            color: #a5d6a7;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("设置管理")
        subtitle.setObjectName("sidebarSubtitle")
        subtitle.setStyleSheet("""
            font-size: 13px;
            color: rgba(255, 255, 255, 0.55);
            letter-spacing: 3px;
        """)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.15); max-height: 1px;")
        layout.addWidget(line)

        # 导航按钮
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 20, 0, 20)
        nav_layout.setSpacing(5)

        self.nav_buttons = {}

        nav_items = [
            ('character', '角色设定'),
            ('api', 'API 配置'),
            ('asr', '语音识别'),
            ('tts', '语音合成'),
            ('audio', '音频/打断'),
            ('models', '模型服务'),
            ('services', '网络服务'),
            ('database', '数据库管理'),
            ('speaker', '说话人管理'),
            ('general', '通用设置'),
        ]

        for key, text in nav_items:
            btn = QPushButton(f"  {text}")
            btn.setCheckable(True)
            btn.setMinimumHeight(45)
            btn.clicked.connect(lambda checked, k=key: self.switch_page(k))
            nav_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        layout.addWidget(nav_widget)
        layout.addStretch()

        # 底部信息
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(20, 20, 20, 20)

        version = QLabel("v0.1.0")
        version.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 12px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(version)

        layout.addWidget(footer)

        return sidebar

    def notify_config_saved(self, section: str):
        """GUI 页面保存配置后调用，通知 Launcher 热更新"""
        self.config_saved.emit(section)

    def switch_page(self, page_key: str):
        """切换页面"""
        # 更新按钮状态
        for key, btn in self.nav_buttons.items():
            btn.setChecked(key == page_key)

        # 切换页面
        if page_key in self.pages:
            self.content_stack.setCurrentWidget(self.pages[page_key])
            if page_key == 'database':
                self.ensure_mongodb_service()
                try:
                    self.pages['database'].check_connection()
                except Exception:
                    logger.warning("Failed to check database connection on page switch")


def main():
    app = QApplication(sys.argv)

    # 设置应用程序属性
    app.setApplicationName("玲 - 设置管理")
    app.setStyle("Fusion")  # 使用 Fusion 风格作为基础

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
