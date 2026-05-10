"""
通用设置页面
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QCheckBox, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QScrollArea, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt
from core.config_manager import get_config_manager

# 通用的 QGroupBox 样式
_GROUP_STYLE = """
    QGroupBox {
        font-size: 14px; font-weight: bold;
        border: 1.5px solid #c8e6c9; border-radius: 10px;
        margin-top: 12px; padding: 18px 16px 16px 16px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 16px; top: 4px;
        padding: 0 6px; color: #2e7d32;
    }
"""
_LABEL_STYLE = "font-size: 13px; color: #2d3a2d;"


class GeneralPage(QWidget):
    """通用设置页"""

    def __init__(self):
        super().__init__()
        self._config_mgr = get_config_manager()
        self._loading = False
        self.init_ui()
        self.load_settings()
        self._connect_auto_save()

    def init_ui(self):
        # 外层用 ScrollArea 包裹，防止内容过多时溢出
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 标题
        title = QLabel("通用设置")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2d3a2d;")
        layout.addWidget(title)

        # ── 常规设置 (GeneralConfig) ──
        general_group = QGroupBox("常规设置")
        general_group.setStyleSheet(_GROUP_STYLE)
        general_form = QFormLayout()
        general_form.setSpacing(12)

        # use_text_input
        self.text_input_cb = QCheckBox("启用文字输入模式（不使用麦克风）")
        self.text_input_cb.setStyleSheet(_LABEL_STYLE)
        general_form.addRow("", self.text_input_cb)
        hint = QLabel("开启后将使用文字对话，需要重启对话系统才能生效。")
        hint.setStyleSheet("color: rgba(45, 58, 45, 0.55); font-size: 12px;")
        hint.setWordWrap(True)
        general_form.addRow("", hint)

        # user_id
        self.user_id_edit = QLineEdit()
        self.user_id_edit.setStyleSheet(_LABEL_STYLE)
        self.user_id_edit.setPlaceholderText("default_user")
        general_form.addRow("用户 ID:", self.user_id_edit)

        # auto_listen
        self.auto_listen_cb = QCheckBox("自动监听")
        self.auto_listen_cb.setStyleSheet(_LABEL_STYLE)
        general_form.addRow("", self.auto_listen_cb)

        # ws_api_key
        self.ws_api_key_edit = QLineEdit()
        self.ws_api_key_edit.setStyleSheet(_LABEL_STYLE)
        self.ws_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ws_api_key_edit.setPlaceholderText("留空表示无密钥")
        general_form.addRow("WebSocket API 密钥:", self.ws_api_key_edit)

        general_group.setLayout(general_form)
        layout.addWidget(general_group)

        # ── 高级设置 (AdvancedConfig) ──
        advanced_group = QGroupBox("高级设置")
        advanced_group.setStyleSheet(_GROUP_STYLE)
        advanced_form = QFormLayout()
        advanced_form.setSpacing(12)

        # enable_debug_logging
        self.debug_logging_cb = QCheckBox("启用调试日志")
        self.debug_logging_cb.setStyleSheet(_LABEL_STYLE)
        advanced_form.addRow("", self.debug_logging_cb)

        # log_performance_metrics
        self.perf_metrics_cb = QCheckBox("记录性能指标")
        self.perf_metrics_cb.setStyleSheet(_LABEL_STYLE)
        advanced_form.addRow("", self.perf_metrics_cb)

        # auto_optimize
        self.auto_optimize_cb = QCheckBox("自动优化")
        self.auto_optimize_cb.setStyleSheet(_LABEL_STYLE)
        advanced_form.addRow("", self.auto_optimize_cb)

        # chroma_dir
        self.chroma_dir_edit = QLineEdit()
        self.chroma_dir_edit.setStyleSheet(_LABEL_STYLE)
        self.chroma_dir_edit.setPlaceholderText("留空使用默认路径")
        advanced_form.addRow("Chroma 存储目录:", self.chroma_dir_edit)

        advanced_group.setLayout(advanced_form)
        layout.addWidget(advanced_group)

        # ── 性能监控 (PerformanceConfig) ──
        perf_group = QGroupBox("性能监控")
        perf_group.setStyleSheet(_GROUP_STYLE)
        perf_form = QFormLayout()
        perf_form.setSpacing(12)

        # enable_monitoring
        self.monitoring_cb = QCheckBox("启用性能监控")
        self.monitoring_cb.setStyleSheet(_LABEL_STYLE)
        perf_form.addRow("", self.monitoring_cb)

        # max_history_size
        self.history_size_spin = QSpinBox()
        self.history_size_spin.setRange(100, 100000)
        self.history_size_spin.setStyleSheet(_LABEL_STYLE)
        perf_form.addRow("最大历史记录数:", self.history_size_spin)

        # export_interval_seconds
        self.export_interval_spin = QSpinBox()
        self.export_interval_spin.setRange(60, 86400)
        self.export_interval_spin.setSuffix(" 秒")
        self.export_interval_spin.setStyleSheet(_LABEL_STYLE)
        perf_form.addRow("导出间隔:", self.export_interval_spin)

        # export_format
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["json", "csv"])
        self.export_format_combo.setStyleSheet(_LABEL_STYLE)
        perf_form.addRow("导出格式:", self.export_format_combo)

        perf_group.setLayout(perf_form)
        layout.addWidget(perf_group)

        # ── 说话人识别 (SpeakerRecognitionConfig) ──
        spk_group = QGroupBox("说话人识别")
        spk_group.setStyleSheet(_GROUP_STYLE)
        spk_form = QFormLayout()
        spk_form.setSpacing(12)

        # enable
        self.spk_enable_cb = QCheckBox("启用说话人识别")
        self.spk_enable_cb.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("", self.spk_enable_cb)

        # async_recognition
        self.spk_async_cb = QCheckBox("异步识别")
        self.spk_async_cb.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("", self.spk_async_cb)

        # timeout_ms  (H2: range 100..30000 so default 500 is not clamped)
        self.spk_timeout_spin = QSpinBox()
        self.spk_timeout_spin.setRange(100, 30000)
        self.spk_timeout_spin.setSuffix(" ms")
        self.spk_timeout_spin.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("超时:", self.spk_timeout_spin)

        # enable_cache
        self.spk_cache_cb = QCheckBox("启用缓存")
        self.spk_cache_cb.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("", self.spk_cache_cb)

        # cache_size
        self.spk_cache_size_spin = QSpinBox()
        self.spk_cache_size_spin.setRange(10, 10000)
        self.spk_cache_size_spin.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("缓存大小:", self.spk_cache_size_spin)

        # passive_registration
        self.spk_passive_cb = QCheckBox("未知说话人自动询问")
        self.spk_passive_cb.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("", self.spk_passive_cb)

        # passive_prompt
        self.spk_passive_prompt_edit = QLineEdit()
        self.spk_passive_prompt_edit.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("询问提示语:", self.spk_passive_prompt_edit)

        # match_threshold
        self.spk_threshold_spin = QDoubleSpinBox()
        self.spk_threshold_spin.setRange(0.0, 1.0)
        self.spk_threshold_spin.setSingleStep(0.05)
        self.spk_threshold_spin.setDecimals(2)
        self.spk_threshold_spin.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("匹配阈值:", self.spk_threshold_spin)

        # voiceprint_dir
        self.spk_voiceprint_dir_edit = QLineEdit()
        self.spk_voiceprint_dir_edit.setStyleSheet(_LABEL_STYLE)
        spk_form.addRow("声纹目录:", self.spk_voiceprint_dir_edit)

        spk_group.setLayout(spk_form)
        layout.addWidget(spk_group)

        # ── 按钮栏 (C2) ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.setFixedWidth(100)
        self.save_btn.setStyleSheet(
            "QPushButton { background: #43a047; color: white; border-radius: 6px; "
            "padding: 6px 16px; font-size: 13px; }"
            "QPushButton:hover { background: #388e3c; }"
        )
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.setFixedWidth(100)
        self.reset_btn.setStyleSheet(
            "QPushButton { background: #e53935; color: white; border-radius: 6px; "
            "padding: 6px 16px; font-size: 13px; }"
            "QPushButton:hover { background: #c62828; }"
        )
        self.reset_btn.clicked.connect(self.reset_settings)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        # 将 container 放入 scroll area
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ─────────────────────────────────────────────
    #  自动保存信号连接 (C1)
    # ─────────────────────────────────────────────

    def _connect_auto_save(self):
        """Connect all widget change signals to auto-save."""
        _auto = lambda: self._on_setting_changed()

        # QCheckBox widgets → stateChanged
        for cb in (
            self.text_input_cb, self.auto_listen_cb,
            self.debug_logging_cb, self.perf_metrics_cb, self.auto_optimize_cb,
            self.monitoring_cb,
            self.spk_enable_cb, self.spk_async_cb, self.spk_cache_cb,
            self.spk_passive_cb,
        ):
            cb.stateChanged.connect(_auto)

        # QLineEdit widgets → textChanged
        for edit in (
            self.user_id_edit, self.ws_api_key_edit, self.chroma_dir_edit,
            self.spk_passive_prompt_edit, self.spk_voiceprint_dir_edit,
        ):
            edit.textChanged.connect(_auto)

        # QSpinBox / QDoubleSpinBox widgets → valueChanged
        for spin in (
            self.history_size_spin, self.export_interval_spin,
            self.spk_timeout_spin, self.spk_cache_size_spin,
            self.spk_threshold_spin,
        ):
            spin.valueChanged.connect(_auto)

        # QComboBox → currentIndexChanged
        self.export_format_combo.currentIndexChanged.connect(_auto)

    # ─────────────────────────────────────────────
    #  加载 / 保存
    # ─────────────────────────────────────────────

    def load_settings(self):
        self._loading = True
        cfg = self._config_mgr.config

        # GeneralConfig
        self.text_input_cb.setChecked(cfg.general.use_text_input)
        self.user_id_edit.setText(cfg.general.user_id)
        self.auto_listen_cb.setChecked(cfg.general.auto_listen)
        self.ws_api_key_edit.setText(cfg.general.ws_api_key)

        # AdvancedConfig
        self.debug_logging_cb.setChecked(cfg.advanced.enable_debug_logging)
        self.perf_metrics_cb.setChecked(cfg.advanced.log_performance_metrics)
        self.auto_optimize_cb.setChecked(cfg.advanced.auto_optimize)
        self.chroma_dir_edit.setText(cfg.advanced.chroma_dir)

        # PerformanceConfig
        self.monitoring_cb.setChecked(cfg.performance.enable_monitoring)
        self.history_size_spin.setValue(cfg.performance.max_history_size)
        self.export_interval_spin.setValue(cfg.performance.export_interval_seconds)
        idx = self.export_format_combo.findText(cfg.performance.export_format)
        if idx >= 0:
            self.export_format_combo.setCurrentIndex(idx)

        # SpeakerRecognitionConfig
        self.spk_enable_cb.setChecked(cfg.speaker_recognition.enable)
        self.spk_async_cb.setChecked(cfg.speaker_recognition.async_recognition)
        self.spk_timeout_spin.setValue(cfg.speaker_recognition.timeout_ms)
        self.spk_cache_cb.setChecked(cfg.speaker_recognition.enable_cache)
        self.spk_cache_size_spin.setValue(cfg.speaker_recognition.cache_size)
        self.spk_passive_cb.setChecked(cfg.speaker_recognition.passive_registration)
        self.spk_passive_prompt_edit.setText(cfg.speaker_recognition.passive_prompt)
        self.spk_threshold_spin.setValue(cfg.speaker_recognition.match_threshold)
        self.spk_voiceprint_dir_edit.setText(cfg.speaker_recognition.voiceprint_dir)

        self._loading = False

    def save_settings(self, config_dict=None):
        """将当前 UI 状态写回配置并持久化。
        config_dict 参数保持接口兼容，本页面直接操作 config manager。"""
        if self._loading:
            return
        cfg = self._config_mgr.config

        # GeneralConfig
        cfg.general.use_text_input = self.text_input_cb.isChecked()
        cfg.general.user_id = self.user_id_edit.text().strip() or "default_user"
        cfg.general.auto_listen = self.auto_listen_cb.isChecked()
        cfg.general.ws_api_key = self.ws_api_key_edit.text()

        # AdvancedConfig
        cfg.advanced.enable_debug_logging = self.debug_logging_cb.isChecked()
        cfg.advanced.log_performance_metrics = self.perf_metrics_cb.isChecked()
        cfg.advanced.auto_optimize = self.auto_optimize_cb.isChecked()
        cfg.advanced.chroma_dir = self.chroma_dir_edit.text().strip()

        # PerformanceConfig
        cfg.performance.enable_monitoring = self.monitoring_cb.isChecked()
        cfg.performance.max_history_size = self.history_size_spin.value()
        cfg.performance.export_interval_seconds = self.export_interval_spin.value()
        cfg.performance.export_format = self.export_format_combo.currentText()

        # SpeakerRecognitionConfig
        cfg.speaker_recognition.enable = self.spk_enable_cb.isChecked()
        cfg.speaker_recognition.async_recognition = self.spk_async_cb.isChecked()
        cfg.speaker_recognition.timeout_ms = self.spk_timeout_spin.value()
        cfg.speaker_recognition.enable_cache = self.spk_cache_cb.isChecked()
        cfg.speaker_recognition.cache_size = self.spk_cache_size_spin.value()
        cfg.speaker_recognition.passive_registration = self.spk_passive_cb.isChecked()
        cfg.speaker_recognition.passive_prompt = self.spk_passive_prompt_edit.text()
        cfg.speaker_recognition.match_threshold = self.spk_threshold_spin.value()
        cfg.speaker_recognition.voiceprint_dir = self.spk_voiceprint_dir_edit.text().strip() or "data/voiceprints"

        self._config_mgr.save()
        try:
            self.window().notify_config_saved("general")
        except Exception:
            pass

    def reset_settings(self):
        """Reset all widgets to their dataclass defaults and save."""
        from core.config_manager import (
            GeneralConfig, AdvancedConfig,
            PerformanceConfig, SpeakerRecognitionConfig,
        )
        defaults_g = GeneralConfig()
        defaults_a = AdvancedConfig()
        defaults_p = PerformanceConfig()
        defaults_s = SpeakerRecognitionConfig()

        self._loading = True

        # GeneralConfig
        self.text_input_cb.setChecked(defaults_g.use_text_input)
        self.user_id_edit.setText(defaults_g.user_id)
        self.auto_listen_cb.setChecked(defaults_g.auto_listen)
        self.ws_api_key_edit.setText(defaults_g.ws_api_key)

        # AdvancedConfig
        self.debug_logging_cb.setChecked(defaults_a.enable_debug_logging)
        self.perf_metrics_cb.setChecked(defaults_a.log_performance_metrics)
        self.auto_optimize_cb.setChecked(defaults_a.auto_optimize)
        self.chroma_dir_edit.setText(defaults_a.chroma_dir)

        # PerformanceConfig
        self.monitoring_cb.setChecked(defaults_p.enable_monitoring)
        self.history_size_spin.setValue(defaults_p.max_history_size)
        self.export_interval_spin.setValue(defaults_p.export_interval_seconds)
        idx = self.export_format_combo.findText(defaults_p.export_format)
        if idx >= 0:
            self.export_format_combo.setCurrentIndex(idx)

        # SpeakerRecognitionConfig
        self.spk_enable_cb.setChecked(defaults_s.enable)
        self.spk_async_cb.setChecked(defaults_s.async_recognition)
        self.spk_timeout_spin.setValue(defaults_s.timeout_ms)
        self.spk_cache_cb.setChecked(defaults_s.enable_cache)
        self.spk_cache_size_spin.setValue(defaults_s.cache_size)
        self.spk_passive_cb.setChecked(defaults_s.passive_registration)
        self.spk_passive_prompt_edit.setText(defaults_s.passive_prompt)
        self.spk_threshold_spin.setValue(defaults_s.match_threshold)
        self.spk_voiceprint_dir_edit.setText(defaults_s.voiceprint_dir)

        self._loading = False
        self.save_settings()

    # ─────────────────────────────────────────────
    #  信号槽
    # ─────────────────────────────────────────────

    def _on_setting_changed(self):
        """任意控件变更时自动保存"""
        if self._loading:
            return
        self.save_settings()
