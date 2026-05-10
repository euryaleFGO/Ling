"""
ML 模型服务配置页面
包含：标点恢复、情感识别、声纹验证、说话人分离
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QComboBox,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox,
    QDoubleSpinBox, QSpinBox,
)
from PyQt6.QtCore import Qt

from core.config_manager import get_config_manager


class ModelsPage(QWidget):
    """ML 模型服务配置页面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    # ================================================================
    #  UI 布局
    # ================================================================
    def init_ui(self):
        root = QWidget()
        root.setObjectName("modelsPageRoot")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 24)

        # 页面标题
        title = QLabel("ML 模型服务")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── 标点恢复 (PuncConfig) ──
        punc_group = QGroupBox("标点恢复")
        punc_layout = QFormLayout()
        punc_layout.setSpacing(14)
        punc_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.punc_enable = QCheckBox("启用标点恢复")
        self.punc_enable.setToolTip("对 ASR 识别结果自动添加标点符号")
        punc_layout.addRow("", self.punc_enable)

        self.punc_model_id = QLineEdit()
        self.punc_model_id.setPlaceholderText("ct-punc")
        self.punc_model_id.setToolTip("标点恢复模型 ID，留空使用默认模型")
        punc_layout.addRow("模型 ID:", self.punc_model_id)

        self.punc_device = QComboBox()
        self.punc_device.setEditable(True)
        self.punc_device.addItems(["auto", "cpu", "cuda:0", "cuda:1"])
        self.punc_device.setToolTip("推理设备：auto 自动检测，cpu 使用 CPU，cuda:0 使用第一块 GPU")
        punc_layout.addRow("推理设备:", self.punc_device)

        punc_group.setLayout(punc_layout)
        layout.addWidget(punc_group)

        # ── 情感识别 (SERConfig) ──
        ser_group = QGroupBox("情感识别")
        ser_layout = QFormLayout()
        ser_layout.setSpacing(14)
        ser_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.ser_enable = QCheckBox("启用情感识别")
        self.ser_enable.setToolTip("分析语音中的情感状态")
        ser_layout.addRow("", self.ser_enable)

        self.ser_model_id = QLineEdit()
        self.ser_model_id.setPlaceholderText("emotion2vec_base")
        self.ser_model_id.setToolTip("情感识别模型 ID，留空使用默认模型")
        ser_layout.addRow("模型 ID:", self.ser_model_id)

        self.ser_device = QComboBox()
        self.ser_device.setEditable(True)
        self.ser_device.addItems(["auto", "cpu", "cuda:0", "cuda:1"])
        self.ser_device.setToolTip("推理设备：auto 自动检测，cpu 使用 CPU，cuda:0 使用第一块 GPU")
        ser_layout.addRow("推理设备:", self.ser_device)

        self.ser_min_audio_sec = QDoubleSpinBox()
        self.ser_min_audio_sec.setRange(0.1, 10.0)
        self.ser_min_audio_sec.setSingleStep(0.1)
        self.ser_min_audio_sec.setDecimals(1)
        self.ser_min_audio_sec.setSuffix(" 秒")
        self.ser_min_audio_sec.setToolTip("低于此时长的音频将跳过情感识别")
        ser_layout.addRow("最短音频时长:", self.ser_min_audio_sec)

        ser_group.setLayout(ser_layout)
        layout.addWidget(ser_group)

        # ── 声纹验证 (SVConfig) ──
        sv_group = QGroupBox("声纹验证")
        sv_layout = QFormLayout()
        sv_layout.setSpacing(14)
        sv_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sv_enable = QCheckBox("启用声纹验证")
        self.sv_enable.setToolTip("通过声纹特征验证说话人身份")
        sv_layout.addRow("", self.sv_enable)

        self.sv_model_id = QLineEdit()
        self.sv_model_id.setPlaceholderText("speech_campplus_sv_zh-cn_16k-common")
        self.sv_model_id.setToolTip("声纹验证模型 ID，留空使用默认模型")
        sv_layout.addRow("模型 ID:", self.sv_model_id)

        self.sv_device = QComboBox()
        self.sv_device.setEditable(True)
        self.sv_device.addItems(["auto", "cpu", "cuda:0", "cuda:1"])
        self.sv_device.setToolTip("推理设备：auto 自动检测，cpu 使用 CPU，cuda:0 使用第一块 GPU")
        sv_layout.addRow("推理设备:", self.sv_device)

        self.sv_threshold = QDoubleSpinBox()
        self.sv_threshold.setRange(0.0, 1.0)
        self.sv_threshold.setSingleStep(0.05)
        self.sv_threshold.setDecimals(2)
        self.sv_threshold.setToolTip("声纹相似度高于此阈值时判定为同一说话人")
        sv_layout.addRow("验证阈值:", self.sv_threshold)

        self.sv_min_audio_sec = QDoubleSpinBox()
        self.sv_min_audio_sec.setRange(0.1, 10.0)
        self.sv_min_audio_sec.setSingleStep(0.1)
        self.sv_min_audio_sec.setDecimals(1)
        self.sv_min_audio_sec.setSuffix(" 秒")
        self.sv_min_audio_sec.setToolTip("低于此时长的音频将跳过声纹验证")
        sv_layout.addRow("最短音频时长:", self.sv_min_audio_sec)

        self.sv_enroll_audio = QLineEdit()
        self.sv_enroll_audio.setPlaceholderText("留空使用默认注册音频")
        self.sv_enroll_audio.setToolTip("声纹注册音频文件路径")
        sv_layout.addRow("注册音频路径:", self.sv_enroll_audio)

        self.sv_reject_policy = QComboBox()
        self.sv_reject_policy.addItems(["drop", "reject"])
        self.sv_reject_policy.setToolTip("未通过声纹验证时的处理策略：drop 丢弃，reject 拒绝并提示")
        sv_layout.addRow("拒绝策略:", self.sv_reject_policy)

        sv_group.setLayout(sv_layout)
        layout.addWidget(sv_group)

        # ── 说话人分离 (DiarizationConfig) ──
        diar_group = QGroupBox("说话人分离")
        diar_layout = QFormLayout()
        diar_layout.setSpacing(14)
        diar_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.diar_enable = QCheckBox("启用说话人分离")
        self.diar_enable.setToolTip("自动区分音频中不同的说话人")
        diar_layout.addRow("", self.diar_enable)

        self.diar_model_id = QLineEdit()
        self.diar_model_id.setPlaceholderText("speech_campplus_sv_zh-cn_16k-common")
        self.diar_model_id.setToolTip("说话人分离模型 ID，留空使用默认模型")
        diar_layout.addRow("模型 ID:", self.diar_model_id)

        self.diar_device = QComboBox()
        self.diar_device.setEditable(True)
        self.diar_device.addItems(["auto", "cpu", "cuda:0", "cuda:1"])
        self.diar_device.setToolTip("推理设备：auto 自动检测，cpu 使用 CPU，cuda:0 使用第一块 GPU")
        diar_layout.addRow("推理设备:", self.diar_device)

        self.diar_threshold = QDoubleSpinBox()
        self.diar_threshold.setRange(0.0, 1.0)
        self.diar_threshold.setSingleStep(0.05)
        self.diar_threshold.setDecimals(2)
        self.diar_threshold.setToolTip("说话人聚类阈值，值越小聚类越严格")
        diar_layout.addRow("聚类阈值:", self.diar_threshold)

        self.diar_max_speakers = QSpinBox()
        self.diar_max_speakers.setRange(2, 20)
        self.diar_max_speakers.setToolTip("最多区分的说话人数量")
        diar_layout.addRow("最大说话人数:", self.diar_max_speakers)

        self.diar_timeout_ms = QSpinBox()
        self.diar_timeout_ms.setRange(100, 30000)
        self.diar_timeout_ms.setSingleStep(500)
        self.diar_timeout_ms.setSuffix(" ms")
        self.diar_timeout_ms.setToolTip("说话人分离处理超时时间")
        diar_layout.addRow("超时:", self.diar_timeout_ms)

        self.diar_notify_speaker_change = QCheckBox("说话人切换通知")
        self.diar_notify_speaker_change.setToolTip("检测到说话人切换时发送通知")
        diar_layout.addRow("", self.diar_notify_speaker_change)

        self.diar_auto_register_unknown = QCheckBox("自动注册未知说话人")
        self.diar_auto_register_unknown.setToolTip("遇到未知声纹时自动注册为新说话人")
        diar_layout.addRow("", self.diar_auto_register_unknown)

        self.diar_min_audio_sec = QDoubleSpinBox()
        self.diar_min_audio_sec.setRange(0.1, 10.0)
        self.diar_min_audio_sec.setSingleStep(0.1)
        self.diar_min_audio_sec.setDecimals(1)
        self.diar_min_audio_sec.setSuffix(" 秒")
        self.diar_min_audio_sec.setToolTip("低于此时长的音频将跳过说话人分离")
        diar_layout.addRow("最短音频时长:", self.diar_min_audio_sec)

        self.diar_storage_path = QLineEdit()
        self.diar_storage_path.setPlaceholderText("留空使用默认路径")
        self.diar_storage_path.setToolTip("说话人声纹数据存储路径")
        diar_layout.addRow("存储路径:", self.diar_storage_path)

        self.diar_allow_concurrent = QCheckBox("允许并发说话人")
        self.diar_allow_concurrent.setToolTip("允许同时识别多个并发说话人")
        diar_layout.addRow("", self.diar_allow_concurrent)

        self.diar_cleanup_days = QSpinBox()
        self.diar_cleanup_days.setRange(1, 365)
        self.diar_cleanup_days.setValue(30)
        self.diar_cleanup_days.setSuffix(" 天")
        self.diar_cleanup_days.setToolTip("超过此时长未活动的声纹数据将被自动清理")
        diar_layout.addRow("声纹清理天数:", self.diar_cleanup_days)

        diar_group.setLayout(diar_layout)
        layout.addWidget(diar_group)

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
    def load_settings(self, config=None):
        """从 ConfigManager 加载设置"""
        try:
            cfg = config or get_config_manager().config

            # 标点恢复
            self.punc_enable.setChecked(cfg.punc.enable)
            self.punc_model_id.setText(cfg.punc.model_id)
            self.punc_device.setCurrentText(cfg.punc.device)

            # 情感识别
            self.ser_enable.setChecked(cfg.ser.enable)
            self.ser_model_id.setText(cfg.ser.model_id)
            self.ser_device.setCurrentText(cfg.ser.device)
            self.ser_min_audio_sec.setValue(cfg.ser.min_audio_sec)

            # 声纹验证
            self.sv_enable.setChecked(cfg.sv.enable)
            self.sv_model_id.setText(cfg.sv.model_id)
            self.sv_device.setCurrentText(cfg.sv.device)
            self.sv_threshold.setValue(cfg.sv.threshold)
            self.sv_min_audio_sec.setValue(cfg.sv.min_audio_sec)
            self.sv_enroll_audio.setText(cfg.sv.enroll_audio)
            self.sv_reject_policy.setCurrentText(cfg.sv.reject_policy)

            # 说话人分离
            self.diar_enable.setChecked(cfg.diarization.enable)
            self.diar_model_id.setText(cfg.diarization.model_id)
            self.diar_device.setCurrentText(cfg.diarization.device)
            self.diar_threshold.setValue(cfg.diarization.threshold)
            self.diar_max_speakers.setValue(cfg.diarization.max_speakers)
            self.diar_timeout_ms.setValue(cfg.diarization.timeout_ms)
            self.diar_notify_speaker_change.setChecked(cfg.diarization.notify_speaker_change)
            self.diar_auto_register_unknown.setChecked(cfg.diarization.auto_register_unknown)
            self.diar_min_audio_sec.setValue(cfg.diarization.min_audio_sec)
            self.diar_storage_path.setText(cfg.diarization.storage_path)
            self.diar_allow_concurrent.setChecked(cfg.diarization.allow_concurrent_speakers)
            self.diar_cleanup_days.setValue(cfg.diarization.voiceprint_cleanup_days)

        except Exception as e:
            print(f"加载模型服务设置失败: {e}")

    def save_settings(self):
        """保存设置到 ConfigManager"""
        try:
            cfg = get_config_manager()
            punc = cfg.config.punc
            ser = cfg.config.ser
            sv = cfg.config.sv
            diar = cfg.config.diarization

            # 标点恢复
            punc.enable = self.punc_enable.isChecked()
            punc.model_id = self.punc_model_id.text().strip()
            punc.device = self.punc_device.currentText().strip()

            # 情感识别
            ser.enable = self.ser_enable.isChecked()
            ser.model_id = self.ser_model_id.text().strip()
            ser.device = self.ser_device.currentText().strip()
            ser.min_audio_sec = self.ser_min_audio_sec.value()

            # 声纹验证
            sv.enable = self.sv_enable.isChecked()
            sv.model_id = self.sv_model_id.text().strip()
            sv.device = self.sv_device.currentText().strip()
            sv.threshold = self.sv_threshold.value()
            sv.min_audio_sec = self.sv_min_audio_sec.value()
            sv.enroll_audio = self.sv_enroll_audio.text().strip()
            sv.reject_policy = self.sv_reject_policy.currentText().strip()

            # 说话人分离
            diar.enable = self.diar_enable.isChecked()
            diar.model_id = self.diar_model_id.text().strip()
            diar.device = self.diar_device.currentText().strip()
            diar.threshold = self.diar_threshold.value()
            diar.max_speakers = self.diar_max_speakers.value()
            diar.timeout_ms = self.diar_timeout_ms.value()
            diar.notify_speaker_change = self.diar_notify_speaker_change.isChecked()
            diar.auto_register_unknown = self.diar_auto_register_unknown.isChecked()
            diar.min_audio_sec = self.diar_min_audio_sec.value()
            diar.storage_path = self.diar_storage_path.text().strip()
            diar.allow_concurrent_speakers = self.diar_allow_concurrent.isChecked()
            diar.voiceprint_cleanup_days = self.diar_cleanup_days.value()

            cfg.save()
            try:
                self.window().notify_config_saved("models")
            except Exception:
                pass
            QMessageBox.information(self, "保存成功", "模型服务设置已保存到 settings.json")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置失败: {e}")

    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # 标点恢复默认值
            self.punc_enable.setChecked(True)
            self.punc_model_id.clear()
            self.punc_device.setCurrentText("auto")

            # 情感识别默认值
            self.ser_enable.setChecked(True)
            self.ser_model_id.clear()
            self.ser_device.setCurrentText("auto")
            self.ser_min_audio_sec.setValue(0.8)

            # 声纹验证默认值
            self.sv_enable.setChecked(False)
            self.sv_model_id.clear()
            self.sv_device.setCurrentText("auto")
            self.sv_threshold.setValue(0.38)
            self.sv_min_audio_sec.setValue(0.8)
            self.sv_enroll_audio.clear()
            self.sv_reject_policy.setCurrentText("drop")

            # 说话人分离默认值
            self.diar_enable.setChecked(False)
            self.diar_model_id.clear()
            self.diar_device.setCurrentText("auto")
            self.diar_threshold.setValue(0.75)
            self.diar_max_speakers.setValue(10)
            self.diar_timeout_ms.setValue(500)
            self.diar_notify_speaker_change.setChecked(True)
            self.diar_auto_register_unknown.setChecked(True)
            self.diar_min_audio_sec.setValue(1.0)
            self.diar_storage_path.clear()
            self.diar_allow_concurrent.setChecked(False)
            self.diar_cleanup_days.setValue(30)
