"""
ASR 语音识别配置页面
"""
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QComboBox,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox,
    QFrame
)
from PyQt6.QtCore import Qt
from pathlib import Path

from core.config_manager import get_config_manager


class AsrPage(QWidget):
    """ASR 语音识别配置页面"""

    def __init__(self):
        super().__init__()
        self._loading = False
        self.init_ui()
        self.load_settings()

    # ================================================================
    #  UI 布局
    # ================================================================
    def init_ui(self):
        root = QWidget()
        root.setObjectName("asrPageRoot")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 24)

        # 页面标题
        title = QLabel("ASR 语音识别")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── 基础配置组 ──
        basic_group = QGroupBox("基础配置")
        basic_layout = QFormLayout()
        basic_layout.setSpacing(14)
        basic_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # ASR 提供商
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["funasr", "whisper"])
        self.provider_combo.setToolTip("选择 ASR 引擎：funasr（本地/远程）或 whisper（OpenAI API）")
        basic_layout.addRow("ASR 提供商:", self.provider_combo)

        # 远程 URL
        self.remote_url_edit = QLineEdit()
        self.remote_url_edit.setPlaceholderText("ws://localhost:10095 或 http://localhost:5002")
        self.remote_url_edit.setToolTip("远程 ASR 服务地址，支持 ws:// (WebSocket) 和 http:// (REST) 协议")
        basic_layout.addRow("远程服务地址:", self.remote_url_edit)

        # 设备
        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)
        self.device_combo.addItems(["auto", "cpu", "cuda:0", "cuda:1"])
        self.device_combo.setToolTip("推理设备：auto 自动检测，cpu 使用 CPU，cuda:0 使用第一块 GPU")
        basic_layout.addRow("推理设备:", self.device_combo)

        # 流式配置
        self.stream_profile_combo = QComboBox()
        self.stream_profile_combo.addItems(["low_latency", "balanced", "accuracy"])
        self.stream_profile_combo.setToolTip(
            "流式识别配置：\n"
            "low_latency - 低延迟，适合实时对话\n"
            "balanced - 平衡延迟和准确度\n"
            "accuracy - 高准确度，延迟稍高"
        )
        basic_layout.addRow("流式配置:", self.stream_profile_combo)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # ── Whisper 配置组 ──
        whisper_group = QGroupBox("Whisper API 配置")
        whisper_layout = QFormLayout()
        whisper_layout.setSpacing(14)
        whisper_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.whisper_api_base_edit = QLineEdit()
        self.whisper_api_base_edit.setPlaceholderText("https://api.openai.com/v1")
        whisper_layout.addRow("API Base URL:", self.whisper_api_base_edit)

        whisper_api_key_layout = QHBoxLayout()
        self.whisper_api_key_edit = QLineEdit()
        self.whisper_api_key_edit.setPlaceholderText("sk-xxxxx")
        self.whisper_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_whisper_key_btn = QPushButton("👁")
        self.show_whisper_key_btn.setFixedWidth(38)
        self.show_whisper_key_btn.clicked.connect(self.toggle_whisper_key_visibility)
        whisper_api_key_layout.addWidget(self.whisper_api_key_edit, 1)
        whisper_api_key_layout.addWidget(self.show_whisper_key_btn)
        whisper_layout.addRow("API Key:", whisper_api_key_layout)

        whisper_group.setLayout(whisper_layout)
        layout.addWidget(whisper_group)

        # ── 热词配置组 ──
        hotword_group = QGroupBox("热词配置")
        hotword_layout = QFormLayout()
        hotword_layout.setSpacing(14)
        hotword_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.hotwords_edit = QLineEdit()
        self.hotwords_edit.setPlaceholderText("用逗号分隔，如：玲,语音助手,AI")
        self.hotwords_edit.setToolTip("热词列表，用逗号分隔，可以提高特定词汇的识别率")
        hotword_layout.addRow("热词列表:", self.hotwords_edit)

        self.hotword_weight_edit = QLineEdit()
        self.hotword_weight_edit.setPlaceholderText("10.0")
        self.hotword_weight_edit.setToolTip("热词权重，值越大热词越容易被识别（默认 10.0）")
        hotword_layout.addRow("热词权重:", self.hotword_weight_edit)

        hotword_group.setLayout(hotword_layout)
        layout.addWidget(hotword_group)

        # ── 缓存配置组 ──
        cache_group = QGroupBox("模型缓存")
        cache_layout = QFormLayout()
        cache_layout.setSpacing(14)
        cache_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.enable_cache_check = QCheckBox("启用模型缓存")
        self.enable_cache_check.setToolTip("缓存已加载的模型，避免重复加载")
        cache_layout.addRow("", self.enable_cache_check)

        self.cache_warmup_check = QCheckBox("启动时预热缓存")
        self.cache_warmup_check.setToolTip("程序启动时预先加载模型到缓存")
        cache_layout.addRow("", self.cache_warmup_check)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        # ── 操作按钮 ──
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.test_btn = QPushButton("测试连接")
        self.test_btn.setProperty("class", "secondary")
        self.test_btn.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_btn)

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
        self._loading = True
        try:
            cfg = get_config_manager().config
            asr = cfg.asr

            # 基础配置
            idx = self.provider_combo.findText(asr.provider)
            if idx >= 0:
                self.provider_combo.setCurrentIndex(idx)
            self.remote_url_edit.setText(asr.remote_url)
            self.device_combo.setCurrentText(asr.device)
            idx = self.stream_profile_combo.findText(asr.stream_profile)
            if idx >= 0:
                self.stream_profile_combo.setCurrentIndex(idx)

            # Whisper 配置
            self.whisper_api_base_edit.setText(asr.whisper_api_base)
            self.whisper_api_key_edit.setText(asr.whisper_api_key)

            # 热词配置
            if asr.hotwords:
                self.hotwords_edit.setText(",".join(asr.hotwords))
            self.hotword_weight_edit.setText(str(asr.hotword_weight))

            # 缓存配置
            self.enable_cache_check.setChecked(asr.enable_model_cache)
            self.cache_warmup_check.setChecked(asr.cache_warmup)

        except Exception as e:
            print(f"加载 ASR 设置失败: {e}")
        finally:
            self._loading = False

    def save_settings(self):
        """保存设置到 ConfigManager"""
        try:
            cfg = get_config_manager()
            asr = cfg.config.asr

            # 基础配置
            asr.provider = self.provider_combo.currentText()
            asr.remote_url = self.remote_url_edit.text().strip()
            asr.device = self.device_combo.currentText().strip()
            asr.stream_profile = self.stream_profile_combo.currentText()

            # Whisper 配置
            asr.whisper_api_base = self.whisper_api_base_edit.text().strip()
            asr.whisper_api_key = self.whisper_api_key_edit.text().strip()

            # 热词配置
            hotwords_text = self.hotwords_edit.text().strip()
            if hotwords_text:
                asr.hotwords = [w.strip() for w in hotwords_text.split(",") if w.strip()]
            else:
                asr.hotwords = []
            try:
                asr.hotword_weight = float(self.hotword_weight_edit.text().strip() or "10.0")
            except ValueError:
                asr.hotword_weight = 10.0

            # 缓存配置
            asr.enable_model_cache = self.enable_cache_check.isChecked()
            asr.cache_warmup = self.cache_warmup_check.isChecked()

            cfg.save()
            QMessageBox.information(self, "保存成功", "ASR 设置已保存到 settings.json")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置失败: {e}")

    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.provider_combo.setCurrentText("funasr")
            self.remote_url_edit.clear()
            self.device_combo.setCurrentText("auto")
            self.stream_profile_combo.setCurrentText("balanced")
            self.whisper_api_base_edit.clear()
            self.whisper_api_key_edit.clear()
            self.hotwords_edit.clear()
            self.hotword_weight_edit.setText("10.0")
            self.enable_cache_check.setChecked(True)
            self.cache_warmup_check.setChecked(False)

    # ================================================================
    #  辅助方法
    # ================================================================
    def toggle_whisper_key_visibility(self):
        """切换 Whisper API Key 显示/隐藏"""
        if self.whisper_api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.whisper_api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_whisper_key_btn.setText("🔒")
        else:
            self.whisper_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_whisper_key_btn.setText("👁")

    def test_connection(self):
        """测试 ASR 连接"""
        provider = self.provider_combo.currentText()
        remote_url = self.remote_url_edit.text().strip()

        if not remote_url:
            QMessageBox.warning(self, "提示", "请先填写远程服务地址")
            return

        self.test_btn.setText("测试中...")
        self.test_btn.setEnabled(False)

        try:
            if provider == "funasr":
                if remote_url.startswith("ws://") or remote_url.startswith("wss://"):
                    from backend.asr.providers import FunASRWebSocketProvider
                    ws_asr = FunASRWebSocketProvider(uri=remote_url)
                    if ws_asr.health_check(timeout=5.0):
                        QMessageBox.information(self, "连接成功", f"WebSocket 连接成功: {remote_url}")
                    else:
                        QMessageBox.warning(self, "连接失败", f"WebSocket 连接超时: {remote_url}")
                    ws_asr.stop()
                else:
                    from backend.asr.providers import FunASRRemoteProvider
                    remote = FunASRRemoteProvider(base_url=remote_url)
                    if remote._client.health_check():
                        QMessageBox.information(self, "连接成功", f"HTTP 连接成功: {remote_url}")
                    else:
                        QMessageBox.warning(self, "连接失败", f"HTTP 连接失败: {remote_url}")
            elif provider == "whisper":
                api_base = self.whisper_api_base_edit.text().strip() or "https://api.openai.com/v1"
                api_key = self.whisper_api_key_edit.text().strip()
                if not api_key:
                    QMessageBox.warning(self, "提示", "请先填写 Whisper API Key")
                    return
                # 简单测试：尝试创建 provider
                from backend.asr.providers import WhisperRemoteProvider
                WhisperRemoteProvider(api_base=api_base, api_key=api_key)
                QMessageBox.information(self, "配置有效", "Whisper API 配置格式正确（实际连接需要录音测试）")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"测试失败: {e}")
        finally:
            self.test_btn.setText("测试连接")
            self.test_btn.setEnabled(True)
