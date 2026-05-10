"""
网络服务配置页面 — MongoDB / WebSocket / SSH 隧道 / 歌声合成
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QComboBox,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox,
    QSpinBox,
)
from PyQt6.QtCore import Qt

from core.config_manager import get_config_manager


class ServicesPage(QWidget):
    """网络服务配置页面"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    # ================================================================
    #  UI 布局
    # ================================================================
    def init_ui(self):
        root = QWidget()
        root.setObjectName("servicesPageRoot")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 24)

        # 页面标题
        title = QLabel("网络服务配置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── MongoDB 配置组 ──
        mongodb_group = QGroupBox("MongoDB")
        mongodb_layout = QFormLayout()
        mongodb_layout.setSpacing(14)
        mongodb_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.mongo_uri_edit = QLineEdit()
        self.mongo_uri_edit.setPlaceholderText("mongodb://localhost:27017")
        self.mongo_uri_edit.setToolTip("MongoDB 连接 URI")
        mongodb_layout.addRow("连接 URI:", self.mongo_uri_edit)

        self.mongo_dbname_edit = QLineEdit()
        self.mongo_dbname_edit.setPlaceholderText("liying_db")
        self.mongo_dbname_edit.setToolTip("数据库名称")
        mongodb_layout.addRow("数据库名:", self.mongo_dbname_edit)

        self.mongo_timeout_spin = QSpinBox()
        self.mongo_timeout_spin.setRange(1000, 60000)
        self.mongo_timeout_spin.setSingleStep(1000)
        self.mongo_timeout_spin.setSuffix(" ms")
        self.mongo_timeout_spin.setToolTip("连接超时时间（毫秒）")
        mongodb_layout.addRow("超时(ms):", self.mongo_timeout_spin)

        mongodb_group.setLayout(mongodb_layout)
        layout.addWidget(mongodb_group)

        # ── WebSocket 服务配置组 ──
        ws_group = QGroupBox("WebSocket 服务")
        ws_layout = QFormLayout()
        ws_layout.setSpacing(14)
        ws_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.ws_host_edit = QLineEdit()
        self.ws_host_edit.setPlaceholderText("0.0.0.0")
        self.ws_host_edit.setToolTip("WebSocket 服务监听地址")
        ws_layout.addRow("主机地址:", self.ws_host_edit)

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setToolTip("WebSocket 服务监听端口")
        ws_layout.addRow("端口:", self.ws_port_spin)

        ws_group.setLayout(ws_layout)
        layout.addWidget(ws_group)

        # ── SSH 隧道配置组 ──
        ssh_group = QGroupBox("SSH 隧道")
        ssh_layout = QFormLayout()
        ssh_layout.setSpacing(14)
        ssh_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.ssh_enable_check = QCheckBox("启用 SSH 隧道")
        self.ssh_enable_check.setToolTip("通过 SSH 隧道转发 TTS/ASR 端口")
        ssh_layout.addRow("", self.ssh_enable_check)

        self.ssh_host_edit = QLineEdit()
        self.ssh_host_edit.setPlaceholderText("远程主机地址")
        self.ssh_host_edit.setToolTip("SSH 远程主机地址")
        ssh_layout.addRow("远程主机:", self.ssh_host_edit)

        self.ssh_port_spin = QSpinBox()
        self.ssh_port_spin.setRange(1, 65535)
        self.ssh_port_spin.setToolTip("SSH 连接端口")
        ssh_layout.addRow("SSH 端口:", self.ssh_port_spin)

        self.ssh_local_tts_spin = QSpinBox()
        self.ssh_local_tts_spin.setRange(1024, 65535)
        self.ssh_local_tts_spin.setToolTip("本地 TTS 转发端口")
        ssh_layout.addRow("本地 TTS 端口:", self.ssh_local_tts_spin)

        self.ssh_remote_tts_spin = QSpinBox()
        self.ssh_remote_tts_spin.setRange(1024, 65535)
        self.ssh_remote_tts_spin.setToolTip("远程 TTS 端口")
        ssh_layout.addRow("远程 TTS 端口:", self.ssh_remote_tts_spin)

        self.ssh_local_asr_spin = QSpinBox()
        self.ssh_local_asr_spin.setRange(1024, 65535)
        self.ssh_local_asr_spin.setToolTip("本地 ASR 转发端口")
        ssh_layout.addRow("本地 ASR 端口:", self.ssh_local_asr_spin)

        self.ssh_remote_asr_spin = QSpinBox()
        self.ssh_remote_asr_spin.setRange(1024, 65535)
        self.ssh_remote_asr_spin.setToolTip("远程 ASR 端口")
        ssh_layout.addRow("远程 ASR 端口:", self.ssh_remote_asr_spin)

        ssh_group.setLayout(ssh_layout)
        layout.addWidget(ssh_group)

        # ── 歌声合成配置组 ──
        singing_group = QGroupBox("歌声合成")
        singing_layout = QFormLayout()
        singing_layout.setSpacing(14)
        singing_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.singing_enable_check = QCheckBox("启用歌声合成")
        self.singing_enable_check.setToolTip("启用 DiffSinger 歌声合成功能")
        singing_layout.addRow("", self.singing_enable_check)

        self.singing_root_edit = QLineEdit()
        self.singing_root_edit.setPlaceholderText("models/Singing/DiffSinger")
        self.singing_root_edit.setToolTip("DiffSinger 项目根目录")
        singing_layout.addRow("DiffSinger 根目录:", self.singing_root_edit)

        self.singing_exp_edit = QLineEdit()
        self.singing_exp_edit.setPlaceholderText("opencpop")
        self.singing_exp_edit.setToolTip("实验名称（对应 checkpoints 下的子目录）")
        singing_layout.addRow("实验名称:", self.singing_exp_edit)

        self.singing_device_combo = QComboBox()
        self.singing_device_combo.setEditable(True)
        self.singing_device_combo.addItems(["auto", "cpu", "cuda", "cuda:0", "cuda:1"])
        self.singing_device_combo.setToolTip("推理设备：auto 自动检测，cpu 使用 CPU，cuda:0 使用第一块 GPU")
        singing_layout.addRow("设备:", self.singing_device_combo)

        self.singing_sample_rate_spin = QSpinBox()
        self.singing_sample_rate_spin.setRange(8000, 96000)
        self.singing_sample_rate_spin.setSingleStep(1000)
        self.singing_sample_rate_spin.setSuffix(" Hz")
        self.singing_sample_rate_spin.setToolTip("歌声合成采样率")
        singing_layout.addRow("采样率:", self.singing_sample_rate_spin)

        self.singing_vocoder_ckpt_edit = QLineEdit()
        self.singing_vocoder_ckpt_edit.setPlaceholderText("checkpoints/nsf_hifigan/model.pt")
        self.singing_vocoder_ckpt_edit.setToolTip("Vocoder 模型路径（NSF-HiFiGAN 等）")
        singing_layout.addRow("Vocoder 路径:", self.singing_vocoder_ckpt_edit)

        singing_group.setLayout(singing_layout)
        layout.addWidget(singing_group)

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

            # MongoDB
            self.mongo_uri_edit.setText(cfg.mongodb.uri)
            self.mongo_dbname_edit.setText(cfg.mongodb.db_name)
            self.mongo_timeout_spin.setValue(cfg.mongodb.timeout_ms)

            # WebSocket
            self.ws_host_edit.setText(cfg.websocket.host)
            self.ws_port_spin.setValue(cfg.websocket.port)

            # SSH 隧道
            self.ssh_enable_check.setChecked(cfg.ssh_tunnel.enable)
            self.ssh_host_edit.setText(cfg.ssh_tunnel.host)
            self.ssh_port_spin.setValue(cfg.ssh_tunnel.port)
            self.ssh_local_tts_spin.setValue(cfg.ssh_tunnel.local_tts_port)
            self.ssh_remote_tts_spin.setValue(cfg.ssh_tunnel.remote_tts_port)
            self.ssh_local_asr_spin.setValue(cfg.ssh_tunnel.local_asr_port)
            self.ssh_remote_asr_spin.setValue(cfg.ssh_tunnel.remote_asr_port)

            # 歌声合成
            self.singing_enable_check.setChecked(cfg.singing.enable)
            self.singing_root_edit.setText(cfg.singing.diffsinger_root)
            self.singing_exp_edit.setText(cfg.singing.exp_name)
            self.singing_device_combo.setCurrentText(cfg.singing.device)
            self.singing_sample_rate_spin.setValue(cfg.singing.sample_rate)
            self.singing_vocoder_ckpt_edit.setText(cfg.singing.vocoder_ckpt)

        except Exception as e:
            print(f"加载网络服务设置失败: {e}")

    def save_settings(self):
        """保存设置到 ConfigManager"""
        try:
            cfg = get_config_manager()
            sys_cfg = cfg.config

            # MongoDB
            sys_cfg.mongodb.uri = self.mongo_uri_edit.text().strip()
            sys_cfg.mongodb.db_name = self.mongo_dbname_edit.text().strip()
            sys_cfg.mongodb.timeout_ms = self.mongo_timeout_spin.value()

            # WebSocket
            sys_cfg.websocket.host = self.ws_host_edit.text().strip()
            sys_cfg.websocket.port = self.ws_port_spin.value()

            # SSH 隧道
            sys_cfg.ssh_tunnel.enable = self.ssh_enable_check.isChecked()
            sys_cfg.ssh_tunnel.host = self.ssh_host_edit.text().strip()
            sys_cfg.ssh_tunnel.port = self.ssh_port_spin.value()
            sys_cfg.ssh_tunnel.local_tts_port = self.ssh_local_tts_spin.value()
            sys_cfg.ssh_tunnel.remote_tts_port = self.ssh_remote_tts_spin.value()
            sys_cfg.ssh_tunnel.local_asr_port = self.ssh_local_asr_spin.value()
            sys_cfg.ssh_tunnel.remote_asr_port = self.ssh_remote_asr_spin.value()

            # 歌声合成
            sys_cfg.singing.enable = self.singing_enable_check.isChecked()
            sys_cfg.singing.diffsinger_root = self.singing_root_edit.text().strip()
            sys_cfg.singing.exp_name = self.singing_exp_edit.text().strip()
            sys_cfg.singing.device = self.singing_device_combo.currentText().strip()
            sys_cfg.singing.sample_rate = self.singing_sample_rate_spin.value()
            sys_cfg.singing.vocoder_ckpt = self.singing_vocoder_ckpt_edit.text().strip()

            cfg.save()
            try:
                self.window().notify_config_saved("services")
            except Exception:
                pass
            QMessageBox.information(self, "保存成功", "网络服务设置已保存到 settings.json")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置失败: {e}")

    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # MongoDB
            self.mongo_uri_edit.setText("mongodb://localhost:27017")
            self.mongo_dbname_edit.setText("liying_db")
            self.mongo_timeout_spin.setValue(5000)

            # WebSocket
            self.ws_host_edit.setText("localhost")
            self.ws_port_spin.setValue(8765)

            # SSH 隧道
            self.ssh_enable_check.setChecked(False)
            self.ssh_host_edit.clear()
            self.ssh_port_spin.setValue(22)
            self.ssh_local_tts_spin.setValue(5001)
            self.ssh_remote_tts_spin.setValue(5001)
            self.ssh_local_asr_spin.setValue(5002)
            self.ssh_remote_asr_spin.setValue(5002)

            # 歌声合成
            self.singing_enable_check.setChecked(False)
            self.singing_root_edit.clear()
            self.singing_exp_edit.setText("opencpop")
            self.singing_device_combo.setCurrentText("cuda")
            self.singing_sample_rate_spin.setValue(44100)
            self.singing_vocoder_ckpt_edit.clear()
