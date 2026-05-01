"""
通用设置页面
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QCheckBox, QFormLayout, QFrame
)
from PyQt6.QtCore import Qt
from core.config_manager import get_config_manager


class GeneralPage(QWidget):
    """通用设置页"""

    def __init__(self):
        super().__init__()
        self._config_mgr = get_config_manager()
        self._loading = False
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 标题
        title = QLabel("通用设置")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2d3a2d;")
        layout.addWidget(title)

        # 输入模式
        input_group = QGroupBox("输入模式")
        input_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px; font-weight: bold;
                border: 1.5px solid #c8e6c9; border-radius: 10px;
                margin-top: 12px; padding: 18px 16px 16px 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 16px; top: 4px;
                padding: 0 6px; color: #2e7d32;
            }
        """)
        form = QFormLayout()
        form.setSpacing(12)

        self.text_input_cb = QCheckBox("启用文字输入模式（不使用麦克风）")
        self.text_input_cb.setStyleSheet("font-size: 13px; color: #2d3a2d;")
        self.text_input_cb.stateChanged.connect(self._on_text_input_changed)
        form.addRow("", self.text_input_cb)

        hint = QLabel("开启后将使用文字对话，需要重启对话系统才能生效。")
        hint.setStyleSheet("color: rgba(45, 58, 45, 0.55); font-size: 12px;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        input_group.setLayout(form)
        layout.addWidget(input_group)

        layout.addStretch()

    def load_settings(self):
        self._loading = True
        cfg = self._config_mgr.config
        self.text_input_cb.setChecked(cfg.general.use_text_input)
        self._loading = False

    def _on_text_input_changed(self, state):
        if self._loading:
            return
        val = state == Qt.CheckState.Checked.value
        self._config_mgr.config.general.use_text_input = val
        self._config_mgr.save()
