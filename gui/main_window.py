"""
设置管理主窗口
左侧导航栏 + 右侧内容区
"""
import sys
sys.path.insert(0, 'e:/Avalon/Chaldea/Liying')

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QStackedWidget, QLabel,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont
from pathlib import Path

from gui.pages import CharacterPage, ApiPage, DatabasePage
import platform
import subprocess
import time


class MainWindow(QMainWindow):
    """设置管理主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("玲 - 设置管理")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        
        # 加载样式
        self.load_style()
        
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
        
        # 右侧内容区
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("content")
        
        # 添加页面
        self.pages = {
            'character': CharacterPage(),
            'api': ApiPage(),
            'database': DatabasePage(),
        }
        
        for page in self.pages.values():
            self.content_stack.addWidget(page)
        
        main_layout.addWidget(self.content_stack, 1)
        
        # 默认显示角色设定页
        self.switch_page('character')
    
    def ensure_mongodb_service(self):
        """检查 MongoDB 是否运行，如果没有则启动"""
        try:
            if platform.system() != "Windows":
                return
            
            page = self.pages.get('database')
            host = 'localhost'
            port = 27017
            try:
                if page:
                    host = (page.mongo_host.text() or 'localhost').strip()
                    port = int((page.mongo_port.text() or '27017').strip())
            except Exception:
                pass
            
            # 只处理本地 MongoDB
            if host not in ("localhost", "127.0.0.1") or port != 27017:
                return

            # 首先检查 MongoDB 是否在运行
            if self._is_mongodb_running():
                return

            # 检查是否有 Windows 服务
            names = ["MongoDB", "MongoDB Server", "mongodb"]
            for name in names:
                try:
                    status = subprocess.run([
                        "powershell", "-NoProfile", "-Command",
                        f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status"
                    ], capture_output=True, text=True, timeout=5)
                    
                    out = (status.stdout or "").strip()
                    if out and out.lower() == "running":
                        return
                    elif out and out.lower() != "running":
                        try:
                            subprocess.run([
                                "powershell", "-NoProfile", "-Command",
                                f"Start-Service -Name '{name}'"
                            ], capture_output=True, text=True, timeout=15, check=True)
                            time.sleep(2)
                            if self._is_mongodb_running():
                                return
                        except subprocess.CalledProcessError:
                            break
                except Exception:
                    continue

            # 如果没有服务或服务启动失败，直接启动 MongoDB 进程
            self._start_mongodb_process()
        except Exception:
            pass

    def _is_mongodb_running(self):
        """检查 MongoDB 是否在运行（通过进程和端口）"""
        try:
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
                if ":27017" in port_check.stdout and "LISTENING" in port_check.stdout:
                    return True
        except Exception:
            pass
        return False

    def _start_mongodb_process(self):
        """启动 MongoDB 进程"""
        mongodb_path = Path("E:/MongoDB")
        mongod_exe = mongodb_path / "bin" / "mongod.exe"
        config_file = mongodb_path / "mongod.cfg"

        if not mongod_exe.exists():
            return

        try:
            # 使用 Start-Process 在后台启动，隐藏窗口
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"Start-Process -FilePath '{mongod_exe}' -ArgumentList '--config', '{config_file}' -WindowStyle Hidden"
            ], timeout=10)
            
            # 等待几秒让 MongoDB 启动
            for _ in range(5):
                time.sleep(1)
                if self._is_mongodb_running():
                    return
        except Exception:
            pass
    
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
            color: #89b4fa;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("✦ 设置管理 ✦")
        subtitle.setObjectName("sidebarSubtitle")
        subtitle.setStyleSheet("""
            font-size: 13px;
            color: #6c7086;
            letter-spacing: 3px;
        """)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)
        
        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #313244; max-height: 1px;")
        layout.addWidget(line)
        
        # 导航按钮
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 20, 0, 20)
        nav_layout.setSpacing(5)
        
        self.nav_buttons = {}
        
        nav_items = [
            ('character', '🎭', '角色设定'),
            ('api', '🔑', 'API 配置'),
            ('database', '💾', '数据库管理'),
        ]
        
        for key, icon, text in nav_items:
            btn = QPushButton(f"  {icon}  {text}")
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
        version.setStyleSheet("color: #6c7086; font-size: 12px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(version)
        
        layout.addWidget(footer)
        
        return sidebar
    
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
                    pass


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
