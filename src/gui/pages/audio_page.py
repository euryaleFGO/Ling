"""
音频与打断配置页面
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QComboBox, QCheckBox,
    QFormLayout, QMessageBox, QScrollArea,
    QDoubleSpinBox, QSpinBox
)
from PyQt6.QtCore import Qt

from core.config_manager import get_config_manager


class AudioPage(QWidget):
    """音频与打断配置页面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    # ================================================================
    #  UI 布局
    # ================================================================
    def init_ui(self):
        root = QWidget()
        root.setObjectName("audioPageRoot")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 24)

        # 页面标题
        title = QLabel("音频与打断设置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── 音频设置组 ──
        audio_group = QGroupBox("音频设置")
        audio_layout = QFormLayout()
        audio_layout.setSpacing(14)
        audio_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 采样率
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["8000", "16000", "22050", "44100", "48000"])
        self.sample_rate_combo.setToolTip("音频采样率（Hz）")
        audio_layout.addRow("采样率:", self.sample_rate_combo)

        # 静音阈值
        self.silence_threshold_spin = QDoubleSpinBox()
        self.silence_threshold_spin.setRange(0.0, 1.0)
        self.silence_threshold_spin.setSingleStep(0.01)
        self.silence_threshold_spin.setDecimals(3)
        self.silence_threshold_spin.setToolTip("低于此值视为静音（0.0 - 1.0）")
        audio_layout.addRow("静音阈值:", self.silence_threshold_spin)

        # 静音持续时间
        self.silence_duration_spin = QDoubleSpinBox()
        self.silence_duration_spin.setRange(0.1, 5.0)
        self.silence_duration_spin.setSingleStep(0.1)
        self.silence_duration_spin.setDecimals(2)
        self.silence_duration_spin.setToolTip("检测到静音后等待的时间（秒）")
        audio_layout.addRow("静音持续时间 (s):", self.silence_duration_spin)

        # VAD 后端
        self.vad_backend_combo = QComboBox()
        self.vad_backend_combo.addItems(["rms", "silero"])
        self.vad_backend_combo.setToolTip(
            "VAD 后端：\n"
            "rms - 基于均方根的简单检测\n"
            "silero - 基于 Silero 模型的智能检测"
        )
        audio_layout.addRow("VAD 后端:", self.vad_backend_combo)

        # VAD 预设
        self.vad_preset_combo = QComboBox()
        self.vad_preset_combo.addItems(["sensitive", "balanced", "aggressive"])
        self.vad_preset_combo.setToolTip(
            "VAD 灵敏度预设：\n"
            "sensitive - 高灵敏度，适合安静环境\n"
            "balanced - 平衡模式（推荐）\n"
            "aggressive - 低灵敏度，适合嘈杂环境"
        )
        audio_layout.addRow("VAD 预设:", self.vad_preset_combo)

        # 使用 VAD
        self.use_vad_check = QCheckBox("启用语音活动检测 (VAD)")
        self.use_vad_check.setToolTip("启用后自动识别语音段落")
        audio_layout.addRow("", self.use_vad_check)

        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)

        # ── 打断设置组 ──
        interrupt_group = QGroupBox("打断设置")
        interrupt_layout = QFormLayout()
        interrupt_layout.setSpacing(14)
        interrupt_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 启用打断
        self.enable_barge_in_check = QCheckBox("启用打断 (Barge-in)")
        self.enable_barge_in_check.setToolTip("允许用户在 AI 说话时打断并开始新的输入")
        interrupt_layout.addRow("", self.enable_barge_in_check)

        # VAD 阈值
        self.vad_threshold_spin = QDoubleSpinBox()
        self.vad_threshold_spin.setRange(0.0, 1.0)
        self.vad_threshold_spin.setSingleStep(0.05)
        self.vad_threshold_spin.setDecimals(3)
        self.vad_threshold_spin.setToolTip("打断检测的 VAD 阈值（0.0 - 1.0）")
        interrupt_layout.addRow("VAD 阈值:", self.vad_threshold_spin)

        # 最小语音持续时间
        self.min_speech_ms_spin = QSpinBox()
        self.min_speech_ms_spin.setRange(50, 2000)
        self.min_speech_ms_spin.setSingleStep(50)
        self.min_speech_ms_spin.setSuffix(" ms")
        self.min_speech_ms_spin.setToolTip("判断为有效语音的最短持续时间（毫秒）")
        interrupt_layout.addRow("最小语音时长:", self.min_speech_ms_spin)

        # 响应时间
        self.response_time_ms_spin = QSpinBox()
        self.response_time_ms_spin.setRange(100, 5000)
        self.response_time_ms_spin.setSingleStep(100)
        self.response_time_ms_spin.setSuffix(" ms")
        self.response_time_ms_spin.setToolTip("打断后等待响应的时间（毫秒）")
        interrupt_layout.addRow("响应时间:", self.response_time_ms_spin)

        # 上下文模式
        self.context_mode_combo = QComboBox()
        self.context_mode_combo.addItems(["reset", "continue"])
        self.context_mode_combo.setToolTip(
            "上下文模式：\n"
            "reset - 打断后重置上下文\n"
            "continue - 打断后保留上下文"
        )
        interrupt_layout.addRow("上下文模式:", self.context_mode_combo)

        # 反馈启用
        self.feedback_enabled_check = QCheckBox("启用反馈")
        self.feedback_enabled_check.setToolTip("打断时提供视觉/听觉反馈")
        interrupt_layout.addRow("", self.feedback_enabled_check)

        # 声音启用
        self.sound_enabled_check = QCheckBox("启用声音提示")
        self.sound_enabled_check.setToolTip("打断时播放提示音")
        interrupt_layout.addRow("", self.sound_enabled_check)

        interrupt_group.setLayout(interrupt_layout)
        layout.addWidget(interrupt_group)

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
            audio = cfg.audio
            interrupt = cfg.interrupt

            # 音频设置
            self.sample_rate_combo.setCurrentText(str(audio.sample_rate))
            self.silence_threshold_spin.setValue(audio.silence_threshold)
            self.silence_duration_spin.setValue(audio.silence_duration)
            idx = self.vad_backend_combo.findText(audio.vad_backend)
            if idx >= 0:
                self.vad_backend_combo.setCurrentIndex(idx)
            idx = self.vad_preset_combo.findText(audio.vad_preset)
            if idx >= 0:
                self.vad_preset_combo.setCurrentIndex(idx)
            self.use_vad_check.setChecked(audio.use_vad)

            # 打断设置
            self.enable_barge_in_check.setChecked(interrupt.enable_barge_in)
            self.vad_threshold_spin.setValue(interrupt.vad_threshold)
            self.min_speech_ms_spin.setValue(interrupt.min_speech_ms)
            self.response_time_ms_spin.setValue(interrupt.response_time_ms)
            idx = self.context_mode_combo.findText(interrupt.context_mode)
            if idx >= 0:
                self.context_mode_combo.setCurrentIndex(idx)
            self.feedback_enabled_check.setChecked(interrupt.feedback_enabled)
            self.sound_enabled_check.setChecked(interrupt.sound_enabled)

        except Exception as e:
            print(f"加载音频/打断设置失败: {e}")

    def save_settings(self):
        """保存设置到 ConfigManager"""
        try:
            cfg = get_config_manager()
            audio = cfg.config.audio
            interrupt = cfg.config.interrupt

            # 音频设置
            audio.sample_rate = int(self.sample_rate_combo.currentText())
            audio.silence_threshold = self.silence_threshold_spin.value()
            audio.silence_duration = self.silence_duration_spin.value()
            audio.vad_backend = self.vad_backend_combo.currentText()
            audio.vad_preset = self.vad_preset_combo.currentText()
            audio.use_vad = self.use_vad_check.isChecked()

            # 打断设置
            interrupt.enable_barge_in = self.enable_barge_in_check.isChecked()
            interrupt.vad_threshold = self.vad_threshold_spin.value()
            interrupt.min_speech_ms = self.min_speech_ms_spin.value()
            interrupt.response_time_ms = self.response_time_ms_spin.value()
            interrupt.context_mode = self.context_mode_combo.currentText()
            interrupt.feedback_enabled = self.feedback_enabled_check.isChecked()
            interrupt.sound_enabled = self.sound_enabled_check.isChecked()

            cfg.save()
            try:
                self.window().notify_config_saved("audio")
            except Exception:
                pass
            QMessageBox.information(self, "保存成功", "音频与打断设置已保存到 settings.json")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置失败: {e}")

    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # 音频默认值
            self.sample_rate_combo.setCurrentText("16000")
            self.silence_threshold_spin.setValue(0.01)
            self.silence_duration_spin.setValue(0.6)
            self.vad_backend_combo.setCurrentText("rms")
            self.vad_preset_combo.setCurrentText("balanced")
            self.use_vad_check.setChecked(True)

            # 打断默认值
            self.enable_barge_in_check.setChecked(True)
            self.vad_threshold_spin.setValue(0.5)
            self.min_speech_ms_spin.setValue(300)
            self.response_time_ms_spin.setValue(200)
            self.context_mode_combo.setCurrentText("reset")
            self.feedback_enabled_check.setChecked(True)
            self.sound_enabled_check.setChecked(False)
