"""
TTS 语音合成配置页面
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox,
    QSpinBox
)
from PyQt6.QtCore import Qt

from core.config_manager import get_config_manager


class TtsPage(QWidget):
    """TTS 语音合成配置页面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    # ================================================================
    #  UI 布局
    # ================================================================
    def init_ui(self):
        root = QWidget()
        root.setObjectName("ttsPageRoot")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 24)

        # 页面标题
        title = QLabel("TTS 语音合成")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── 远程 TTS 组 ──
        remote_group = QGroupBox("远程 TTS")
        remote_layout = QFormLayout()
        remote_layout.setSpacing(14)
        remote_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.remote_url_edit = QLineEdit()
        self.remote_url_edit.setPlaceholderText("http://localhost:5001")
        self.remote_url_edit.setToolTip("远程 TTS 服务地址，留空则使用本地引擎")
        remote_layout.addRow("远程服务地址:", self.remote_url_edit)

        self.spk_id_edit = QLineEdit()
        self.spk_id_edit.setPlaceholderText("玲")
        self.spk_id_edit.setToolTip("说话人 ID，默认为 玲")
        remote_layout.addRow("说话人 ID:", self.spk_id_edit)

        remote_group.setLayout(remote_layout)
        layout.addWidget(remote_group)

        # ── 缓存组 ──
        cache_group = QGroupBox("缓存")
        cache_layout = QFormLayout()
        cache_layout.setSpacing(14)
        cache_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.enable_cache_check = QCheckBox("启用 TTS 缓存")
        self.enable_cache_check.setToolTip("缓存常用语音片段，减少重复合成")
        cache_layout.addRow("", self.enable_cache_check)

        self.cache_size_spin = QSpinBox()
        self.cache_size_spin.setRange(10, 10000)
        self.cache_size_spin.setSuffix(" 条")
        self.cache_size_spin.setToolTip("缓存条目上限（10 ~ 10000）")
        cache_layout.addRow("缓存大小:", self.cache_size_spin)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        # ── 并行合成组 ──
        parallel_group = QGroupBox("并行合成")
        parallel_layout = QFormLayout()
        parallel_layout.setSpacing(14)
        parallel_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.parallel_synthesis_check = QCheckBox("启用并行合成")
        self.parallel_synthesis_check.setToolTip("同时合成多个语音片段，降低总延迟")
        parallel_layout.addRow("", self.parallel_synthesis_check)

        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 8)
        self.max_workers_spin.setSuffix(" 个")
        self.max_workers_spin.setToolTip("并行合成的最大线程数（1 ~ 8）")
        parallel_layout.addRow("最大并行数:", self.max_workers_spin)

        parallel_group.setLayout(parallel_layout)
        layout.addWidget(parallel_group)

        # ── 操作按钮 ──
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("保存设置")
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("重置默认")
        self.reset_btn.setProperty("class", "secondary")
        self.reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

        scroll.setWidget(content)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

    # ================================================================
    #  加载 & 保存
    # ================================================================
    def load_settings(self):
        """从 ConfigManager 加载设置"""
        try:
            cfg = get_config_manager().config
            tts = cfg.tts

            # 远程 TTS
            self.remote_url_edit.setText(tts.remote_url)
            self.spk_id_edit.setText(tts.spk_id)

            # 缓存
            self.enable_cache_check.setChecked(tts.enable_cache)
            self.cache_size_spin.setValue(tts.cache_size)

            # 并行合成
            self.parallel_synthesis_check.setChecked(tts.parallel_synthesis)
            self.max_workers_spin.setValue(tts.max_workers)

        except Exception as e:
            print(f"加载 TTS 设置失败: {e}")

    def save_settings(self):
        """保存设置到 ConfigManager"""
        try:
            cfg = get_config_manager()
            tts = cfg.config.tts

            # 远程 TTS
            tts.remote_url = self.remote_url_edit.text().strip()
            spk = self.spk_id_edit.text().strip()
            tts.spk_id = spk if spk else "玲"

            # 缓存
            tts.enable_cache = self.enable_cache_check.isChecked()
            tts.cache_size = self.cache_size_spin.value()

            # 并行合成
            tts.parallel_synthesis = self.parallel_synthesis_check.isChecked()
            tts.max_workers = self.max_workers_spin.value()

            cfg.save()
            try:
                self.window().notify_config_saved("tts")
            except Exception:
                pass
            QMessageBox.information(self, "保存成功", "TTS 设置已保存到 settings.json")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置失败: {e}")

    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.remote_url_edit.clear()
            self.spk_id_edit.setText("玲")
            self.enable_cache_check.setChecked(True)
            self.cache_size_spin.setValue(100)
            self.parallel_synthesis_check.setChecked(True)
            self.max_workers_spin.setValue(2)
