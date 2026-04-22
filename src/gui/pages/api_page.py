"""
API 配置页面
支持多配置方案管理
"""
import sys

import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QComboBox,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox,
    QInputDialog, QFrame, QDialog
)
from PyQt6.QtCore import Qt
import os
from pathlib import Path


class CustomInputDialog(QDialog):
    """自定义输入对话框 - 避免黑色背景问题"""
    
    def __init__(self, parent=None, title="", label="", placeholder=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        
        # 设置样式 - 使用应用的绿色主题
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fdf8;
            }
            QLabel {
                color: #2d3a2d;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #f1f8e9;
                border: 1.5px solid #a5d6a7;
                border-radius: 10px;
                padding: 10px 14px;
                color: #2d3a2d;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #43a047;
                background-color: #ffffff;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #4caf50, stop:1 #43a047);
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #66bb6a, stop:1 #4caf50);
            }
            QPushButton[class="secondary"] {
                background: transparent;
                border: 1.5px solid #a5d6a7;
                color: #43a047;
            }
            QPushButton[class="secondary"]:hover {
                border-color: #43a047;
                background-color: #e8f5e9;
                color: #2e7d32;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标签
        if label:
            label_widget = QLabel(label)
            label_widget.setWordWrap(True)
            layout.addWidget(label_widget)
        
        # 输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(placeholder)
        self.input_field.setMinimumHeight(35)
        layout.addWidget(self.input_field)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setProperty("class", "secondary")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # 设置焦点
        self.input_field.setFocus()
    
    def get_text(self):
        """获取输入的文本"""
        return self.input_field.text().strip()


class ApiPage(QWidget):
    """API 配置页面 — 白底绿色清新风格"""

    def __init__(self):
        super().__init__()
        project_root = Path(__file__).parent.parent.parent.parent
        self.env_path = project_root / ".env"
        self.backend_env_path = project_root / "src" / "backend" / "llm" / "api_infer" / ".env"
        self.profiles_path = project_root / "config" / "llm_profiles.json"
        self._profiles: dict = {"active": "", "profiles": {}}
        self._loading = False          # 加载期间禁止信号触发
        self.init_ui()
        self.load_settings()

    # ================================================================
    #  UI 布局
    # ================================================================
    def init_ui(self):
        root = QWidget()
        root.setObjectName("apiPageRoot")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(18)
        layout.setContentsMargins(30, 24, 30, 24)

        # 页面标题
        title = QLabel("API 配置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── LLM 配置组 ──
        llm_group = QGroupBox("LLM 大语言模型")
        llm_layout = QFormLayout()
        llm_layout.setSpacing(14)
        llm_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 配置方案说明
        profile_hint = QLabel("💡 配置方案：保存的完整配置（包含提供商、密钥等）")
        profile_hint.setStyleSheet("color: #666; font-size: 11px; padding: 5px 0;")
        llm_layout.addRow("", profile_hint)

        # 配置方案行
        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.currentTextChanged.connect(self.on_profile_selection_changed)
        profile_row.addWidget(self.profile_combo, 1)

        self.new_profile_btn = QPushButton("+ 新建")
        self.new_profile_btn.setToolTip("创建新的配置方案")
        self.new_profile_btn.clicked.connect(self.create_new_profile)
        profile_row.addWidget(self.new_profile_btn)

        self.switch_profile_btn = QPushButton("切换")
        self.switch_profile_btn.setToolTip("加载所选方案到表单并写入 .env")
        self.switch_profile_btn.setProperty("class", "secondary")
        self.switch_profile_btn.clicked.connect(self.switch_to_selected_profile)
        profile_row.addWidget(self.switch_profile_btn)

        self.save_current_btn = QPushButton("保存")
        self.save_current_btn.setToolTip("将表单覆盖保存到当前选中的方案")
        self.save_current_btn.clicked.connect(self.save_to_current_profile)
        profile_row.addWidget(self.save_current_btn)

        self.delete_profile_btn = QPushButton("删除")
        self.delete_profile_btn.setToolTip("删除所选方案")
        self.delete_profile_btn.setProperty("class", "danger")
        self.delete_profile_btn.clicked.connect(self.delete_current_profile)
        profile_row.addWidget(self.delete_profile_btn)

        llm_layout.addRow("配置方案:", profile_row)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: #e0e0e0; margin: 10px 0;")
        llm_layout.addRow("", separator)

        # 提供商配置说明
        provider_hint = QLabel("⚙️ 以下配置当前方案的详细参数")
        provider_hint.setStyleSheet("color: #666; font-size: 11px; padding: 5px 0;")
        llm_layout.addRow("", provider_hint)

        # API 提供商
        provider_layout = QHBoxLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.setEditable(True)  # 允许用户输入自定义提供商名称
        self.provider_combo.addItems([
            "DeepSeek", 
            "OpenAI", 
            "Claude", 
            "Xiaomi MiMo (按量)", 
            "Xiaomi MiMo (Token Plan)",
            "自定义"
        ])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addWidget(self.provider_combo, 1)
        
        # 添加帮助按钮
        help_btn = QPushButton("?")
        help_btn.setFixedWidth(30)
        help_btn.setToolTip("查看提供商说明")
        help_btn.clicked.connect(self.show_provider_help)
        provider_layout.addWidget(help_btn)
        
        llm_layout.addRow("API 提供商:", provider_layout)

        # API Base URL
        self.api_base_edit = QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.deepseek.com")
        llm_layout.addRow("API Base URL:", self.api_base_edit)

        # API Key
        api_key_layout = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-xxxxx 或 tp-xxxxx (Token Plan)")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setObjectName("showKeyBtn")
        self.show_key_btn.setFixedWidth(38)
        self.show_key_btn.clicked.connect(self.toggle_key_visibility)
        api_key_layout.addWidget(self.api_key_edit, 1)
        api_key_layout.addWidget(self.show_key_btn)
        llm_layout.addRow("API Key:", api_key_layout)

        # 模型
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        llm_layout.addRow("模型:", self.model_combo)

        # 测试连接
        test_layout = QHBoxLayout()
        test_layout.addStretch()
        self.test_llm_btn = QPushButton("测试连接")
        self.test_llm_btn.setProperty("class", "secondary")
        self.test_llm_btn.clicked.connect(self.test_llm_connection)
        test_layout.addWidget(self.test_llm_btn)
        llm_layout.addRow("", test_layout)

        llm_group.setLayout(llm_layout)
        layout.addWidget(llm_group)

        # ── TTS 配置组 ──
        tts_group = QGroupBox("TTS 语音合成")
        tts_layout = QFormLayout()
        tts_layout.setSpacing(14)
        tts_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.tts_enabled = QCheckBox("启用语音合成")
        tts_layout.addRow("", self.tts_enabled)

        self.tts_provider_combo = QComboBox()
        self.tts_provider_combo.addItems(["Edge TTS (免费)", "Azure TTS", "自定义"])
        tts_layout.addRow("TTS 提供商:", self.tts_provider_combo)

        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.addItems([
            "zh-CN-XiaoxiaoNeural",
            "zh-CN-XiaoyiNeural",
            "zh-CN-YunjianNeural",
            "zh-CN-YunxiNeural"
        ])
        self.tts_voice_combo.setEditable(True)
        tts_layout.addRow("语音:", self.tts_voice_combo)

        tts_group.setLayout(tts_layout)
        layout.addWidget(tts_group)

        # ── 高级设置组 ──
        advanced_group = QGroupBox("高级设置")
        advanced_layout = QFormLayout()
        advanced_layout.setSpacing(14)
        advanced_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.temperature_edit = QLineEdit()
        self.temperature_edit.setPlaceholderText("0.7")
        advanced_layout.addRow("Temperature:", self.temperature_edit)

        self.max_tokens_edit = QLineEdit()
        self.max_tokens_edit.setPlaceholderText("2048")
        advanced_layout.addRow("Max Tokens:", self.max_tokens_edit)

        self.timeout_edit = QLineEdit()
        self.timeout_edit.setPlaceholderText("30")
        advanced_layout.addRow("超时时间(秒):", self.timeout_edit)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

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
    #  提供商切换
    # ================================================================
    def on_provider_changed(self, provider: str):
        """提供商切换 → 更新 placeholder 和模型预设"""
        if self._loading:
            return
        
        # 预设配置字典
        defaults = {
            "DeepSeek": (
                "https://api.deepseek.com", 
                ["deepseek-chat", "deepseek-reasoner"]
            ),
            "OpenAI": (
                "https://api.openai.com/v1", 
                ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
            ),
            "Claude": (
                "https://api.anthropic.com", 
                ["claude-3-opus", "claude-3-sonnet"]
            ),
            "Xiaomi MiMo (按量)": (
                "https://api.xiaomimimo.com/v1",
                ["mimo-v2-pro", "mimo-v2-omni", "mimo-v2-flash"]
            ),
            "Xiaomi MiMo (Token Plan)": (
                "https://token-plan-cn.xiaomimimo.com/v1",
                ["mimo-v2-pro", "mimo-v2-omni", "mimo-v2-flash"]
            ),
            "自定义": ("", [])
        }
        
        # 如果是预设提供商，应用默认配置
        if provider in defaults:
            base_url, models = defaults[provider]
            self.api_base_edit.setPlaceholderText(base_url)
            if models:
                self.model_combo.clear()
                self.model_combo.addItems(models)
        else:
            # 自定义提供商，清空 placeholder
            self.api_base_edit.setPlaceholderText("https://your-api-endpoint.com/v1")

    def toggle_key_visibility(self):
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("🔒")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("👁")
    
    def show_provider_help(self):
        """显示提供商帮助信息"""
        help_text = """
<h3>API 提供商说明</h3>

<p><b>Xiaomi MiMo (按量)</b></p>
<ul>
<li>按实际使用量计费</li>
<li>API 端点: https://api.xiaomimimo.com/v1</li>
<li>API Key 格式: sk-xxxxx</li>
<li>定价: ≤256K 上下文 $1/1M input, $3/1M output</li>
</ul>

<p><b>Xiaomi MiMo (Token Plan)</b></p>
<ul>
<li>固定订阅费用，按套餐限额调用</li>
<li>API 端点: https://token-plan-cn.xiaomimimo.com/v1</li>
<li>API Key 格式: tp-xxxxx</li>
<li>需要先在平台订阅 Token Plan</li>
</ul>

<p><b>自定义提供商</b></p>
<ul>
<li>可以输入任意提供商名称</li>
<li>手动填写 API Base URL 和模型名称</li>
<li>适用于兼容 OpenAI 格式的第三方 API</li>
</ul>

<p>参考文档: <a href="https://platform.xiaomimimo.com">https://platform.xiaomimimo.com</a></p>
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("提供商说明")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(help_text)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    # ================================================================
    #  Profile ↔ 表单 互转
    # ================================================================
    def _form_to_profile_dict(self) -> dict:
        return {
            "provider":    self.provider_combo.currentText().strip(),
            "api_base":    self.api_base_edit.text().strip(),
            "api_key":     self.api_key_edit.text().strip(),
            "model":       self.model_combo.currentText().strip(),
            "temperature": self.temperature_edit.text().strip(),
            "max_tokens":  self.max_tokens_edit.text().strip(),
            "timeout":     self.timeout_edit.text().strip(),
        }

    def _apply_profile_to_form(self, profile: dict):
        self._loading = True
        
        # 提供商 - 改进逻辑：保留原始提供商名称
        provider = profile.get("provider", "")
        if provider:
            # 先尝试在下拉列表中查找
            idx = self.provider_combo.findText(provider)
            if idx >= 0:
                # 找到了，直接选中
                self.provider_combo.setCurrentIndex(idx)
            else:
                # 没找到，说明是自定义提供商，直接设置文本（因为 combo 可编辑）
                self.provider_combo.setCurrentText(provider)
        
        # 其它字段
        self.api_base_edit.setText(profile.get("api_base", ""))
        self.api_key_edit.setText(profile.get("api_key", ""))
        model = profile.get("model", "")
        if model:
            self.model_combo.setCurrentText(model)
        self.temperature_edit.setText(profile.get("temperature", ""))
        self.max_tokens_edit.setText(profile.get("max_tokens", ""))
        self.timeout_edit.setText(profile.get("timeout", ""))
        self._loading = False

    # ================================================================
    #  .env 读写
    # ================================================================
    def _read_env_file(self, path: Path) -> dict:
        result = {}
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            result[key.strip()] = value.strip().strip('"\'')
        except Exception as e:
            print(f"读取 .env 失败 ({path}): {e}")
        return result

    def _write_env_file(self, path: Path, env_vars: dict):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            written_keys = set()
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    for raw in f:
                        stripped = raw.strip()
                        if stripped and not stripped.startswith('#') and '=' in stripped:
                            key = stripped.split('=', 1)[0].strip()
                            if key in env_vars:
                                lines.append(f"{key}={env_vars[key]}\n")
                                written_keys.add(key)
                            else:
                                lines.append(raw if raw.endswith('\n') else raw + '\n')
                        else:
                            lines.append(raw if raw.endswith('\n') else raw + '\n')
            for key, value in env_vars.items():
                if key not in written_keys:
                    lines.append(f"{key}={value}\n")
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as e:
            print(f"写入 .env 失败 ({path}): {e}")

    def _apply_profile_to_envs(self, profile: dict):
        api_base    = profile.get("api_base", "")
        api_key     = profile.get("api_key", "")
        model       = profile.get("model", "")
        temperature = profile.get("temperature", "")
        max_tokens  = profile.get("max_tokens", "")
        timeout     = profile.get("timeout", "")

        gui_vars = {}
        if api_base:    gui_vars["OPENAI_API_BASE"] = api_base
        if api_key:     gui_vars["OPENAI_API_KEY"]  = api_key
        if model:       gui_vars["OPENAI_MODEL"]    = model
        if temperature: gui_vars["TEMPERATURE"]     = temperature
        if max_tokens:  gui_vars["MAX_TOKENS"]      = max_tokens
        if timeout:     gui_vars["TIMEOUT"]         = timeout
        if gui_vars:
            self._write_env_file(self.env_path, gui_vars)

        backend_vars = {}
        if api_base: backend_vars["BASE_URL"]         = api_base
        if api_key:  backend_vars["DEEPSEEK_API_KEY"] = api_key
        if model:    backend_vars["MODEL"]            = model
        if backend_vars:
            self._write_env_file(self.backend_env_path, backend_vars)

    # ================================================================
    #  profiles.json 读写
    # ================================================================
    def load_profiles(self):
        try:
            if self.profiles_path.exists():
                with open(self.profiles_path, 'r', encoding='utf-8') as f:
                    self._profiles = json.load(f)
            else:
                self._profiles = {"active": "", "profiles": {}}
        except Exception as e:
            print(f"加载配置方案失败: {e}")
            self._profiles = {"active": "", "profiles": {}}

    def save_profiles(self):
        try:
            self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.profiles_path, 'w', encoding='utf-8') as f:
                json.dump(self._profiles, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置方案失败: {e}")

    def _refresh_profile_combo(self):
        self._loading = True
        self.profile_combo.clear()
        for name in self._profiles.get("profiles", {}):
            self.profile_combo.addItem(name)
        active = self._profiles.get("active", "")
        if active:
            idx = self.profile_combo.findText(active)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        self._loading = False

    # ================================================================
    #  加载 & 保存
    # ================================================================
    def load_settings(self):
        self.load_profiles()
        self._refresh_profile_combo()

        active = self._profiles.get("active", "")
        profiles = self._profiles.get("profiles", {})

        if active and active in profiles:
            self._apply_profile_to_form(profiles[active])
        else:
            try:
                env_vars = self._read_env_file(self.backend_env_path)
                if not env_vars:
                    env_vars = self._read_env_file(self.env_path)
                self.api_base_edit.setText(
                    env_vars.get('BASE_URL', env_vars.get('OPENAI_API_BASE', '')))
                self.api_key_edit.setText(
                    env_vars.get('DEEPSEEK_API_KEY', env_vars.get('OPENAI_API_KEY', '')))
                model = env_vars.get('MODEL', env_vars.get('OPENAI_MODEL', ''))
                if model:
                    self.model_combo.setCurrentText(model)
                self.temperature_edit.setText(env_vars.get('TEMPERATURE', ''))
                self.max_tokens_edit.setText(env_vars.get('MAX_TOKENS', ''))
                self.timeout_edit.setText(env_vars.get('TIMEOUT', ''))
            except Exception as e:
                print(f"加载 API 设置失败: {e}")

    # ================================================================
    #  方案操作
    # ================================================================
    def on_profile_selection_changed(self, profile_name: str):
        """配置方案选择变化时的处理"""
        # 防止加载期间触发
        if self._loading:
            return
        
        # 如果选择的是现有方案，不做任何操作（用户需要点击"切换"按钮）
        # 这样可以避免误操作
        pass
    
    def create_new_profile(self):
        """创建新配置方案 - 先命名，后配置"""
        # 使用自定义对话框输入方案名称
        dialog = CustomInputDialog(
            parent=self,
            title="新建配置方案",
            label="请输入新方案名称：\n\n提示：可以根据用途命名，如 'Xiaomi MiMo 工作用'、'DeepSeek 测试' 等",
            placeholder="例如：Xiaomi MiMo 工作用"
        )
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        name = dialog.get_text()
        if not name:
            return
        
        profiles = self._profiles.get("profiles", {})
        
        # 检查是否已存在
        if name in profiles:
            QMessageBox.warning(
                self, "名称冲突",
                f'方案 "{name}" 已存在，请使用其他名称。')
            return
        
        # 清空表单，准备配置新方案
        self._loading = True
        self.provider_combo.setCurrentText("自定义")
        self.api_base_edit.clear()
        self.api_key_edit.clear()
        self.model_combo.clear()
        self.temperature_edit.clear()
        self.max_tokens_edit.clear()
        self.timeout_edit.clear()
        self._loading = False
        
        # 创建空方案
        profiles[name] = {
            "provider": "自定义",
            "api_base": "",
            "api_key": "",
            "model": "",
            "temperature": "",
            "max_tokens": "",
            "timeout": ""
        }
        self._profiles["profiles"] = profiles
        self._profiles["active"] = name
        self.save_profiles()
        self._refresh_profile_combo()
        
        # 显示引导提示
        QMessageBox.information(
            self, "方案已创建",
            f'✅ 方案 "{name}" 已创建！\n\n'
            f'📝 接下来请配置：\n'
            f'1️⃣ 选择 API 提供商（如 Xiaomi MiMo）\n'
            f'2️⃣ 填写 API Key 和模型\n'
            f'3️⃣ 点击"测试连接"验证\n'
            f'4️⃣ 点击"保存"保存配置\n'
            f'5️⃣ 点击"切换"激活配置')
        
        # 创建空方案
        profiles[name] = {
            "provider": "自定义",
            "api_base": "",
            "api_key": "",
            "model": "",
            "temperature": "",
            "max_tokens": "",
            "timeout": ""
        }
        self._profiles["profiles"] = profiles
        self._profiles["active"] = name
        self.save_profiles()
        self._refresh_profile_combo()
        
        # 显示引导提示
        QMessageBox.information(
            self, "方案已创建",
            f'✅ 方案 "{name}" 已创建！\n\n'
            f'📝 接下来请配置：\n'
            f'1️⃣ 选择 API 提供商（如 Xiaomi MiMo）\n'
            f'2️⃣ 填写 API Key 和模型\n'
            f'3️⃣ 点击"测试连接"验证\n'
            f'4️⃣ 点击"保存"保存配置\n'
            f'5️⃣ 点击"切换"激活配置')
    
    def switch_to_selected_profile(self):
        """切换：加载所选方案到表单 + 写入 .env"""
        name = self.profile_combo.currentText()
        if not name:
            return
        profiles = self._profiles.get("profiles", {})
        if name not in profiles:
            QMessageBox.warning(self, "错误", f'找不到方案 "{name}"')
            return
        self._apply_profile_to_form(profiles[name])
        self._apply_profile_to_envs(profiles[name])
        self._profiles["active"] = name
        self.save_profiles()
        QMessageBox.information(
            self, "已切换",
            f"已切换到方案：{name}\n配置已写入 .env，重启后端服务后完全生效。")

    def save_to_current_profile(self):
        """保存：将表单覆盖写入当前选中的方案"""
        name = self.profile_combo.currentText()
        if not name:
            QMessageBox.warning(
                self, "提示",
                "请先选择一个配置方案，或点击 '+ 新建' 创建新方案。")
            return
        
        profile_data = self._form_to_profile_dict()
        self._profiles.setdefault("profiles", {})[name] = profile_data
        self._profiles["active"] = name
        self.save_profiles()
        self._apply_profile_to_envs(profile_data)
        self._refresh_profile_combo()
        QMessageBox.information(
            self, "已保存",
            f'方案 "{name}" 已更新，并同步写入 .env 文件。')

    def save_as_new_profile(self):
        """另存为：将表单保存到新名称（已被 create_new_profile 替代，保留以防兼容性问题）"""
        # 使用自定义对话框
        dialog = CustomInputDialog(
            parent=self,
            title="另存为新方案",
            label="请输入新方案名称：",
            placeholder="例如：Xiaomi MiMo 备用"
        )
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        name = dialog.get_text()
        if not name:
            return
        
        profiles = self._profiles.setdefault("profiles", {})
        if name in profiles:
            reply = QMessageBox.question(
                self, "覆盖确认",
                f'方案 "{name}" 已存在，是否覆盖？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        profiles[name] = self._form_to_profile_dict()
        self._profiles["active"] = name
        self.save_profiles()
        self._refresh_profile_combo()
        QMessageBox.information(
            self, "已保存",
            f'方案 "{name}" 已保存。\n点击"切换"可将其写入 .env 并生效。')

    def delete_current_profile(self):
        """删除所选方案"""
        name = self.profile_combo.currentText()
        if not name:
            return
        profiles = self._profiles.get("profiles", {})
        if name not in profiles:
            return
        if len(profiles) <= 1:
            QMessageBox.warning(
                self, "无法删除", 
                "至少保留一个配置方案。\n\n如果要删除当前方案，请先创建其他方案。")
            return
        
        # 使用更友好的确认对话框
        reply = QMessageBox.question(
            self, "确认删除",
            f'确定要删除配置方案 "{name}" 吗？\n\n'
            f'此操作不可恢复。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)  # 默认选择 No，更安全
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        del profiles[name]
        if self._profiles.get("active") == name:
            self._profiles["active"] = next(iter(profiles))
        self.save_profiles()
        self._refresh_profile_combo()
        new_active = self._profiles.get("active", "")
        if new_active and new_active in profiles:
            self._apply_profile_to_form(profiles[new_active])
        QMessageBox.information(
            self, "已删除", 
            f'方案 "{name}" 已删除。\n\n当前激活方案：{new_active}')

    # ================================================================
    #  测试连接 / 重置
    # ================================================================
    def test_llm_connection(self):
        try:
            self.test_llm_btn.setText("测试中...")
            self.test_llm_btn.setEnabled(False)

            base_url = self.api_base_edit.text().strip() or "https://api.deepseek.com"
            api_key  = self.api_key_edit.text().strip()
            model    = self.model_combo.currentText().strip() or "deepseek-chat"

            from backend.llm.api_infer import APIInfer
            infer = APIInfer(url=base_url, api_key=api_key, model_name=model)
            response = infer.infer(
                messages=[{"role": "user", "content": "你好"}],
                stream=False
            )

            if response and response.choices:
                text = response.choices[0].message.content or ""
                QMessageBox.information(
                    self, "成功", f"连接成功！\n\n模型响应：{text[:100]}...")
            else:
                QMessageBox.warning(self, "失败", "连接失败，未收到响应")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接失败：{e}")
        finally:
            self.test_llm_btn.setText("测试连接")
            self.test_llm_btn.setEnabled(True)

    def reset_settings(self):
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.provider_combo.setCurrentText("DeepSeek")
            self.api_base_edit.clear()
            self.api_key_edit.clear()
            self.model_combo.setCurrentText("deepseek-chat")
            self.temperature_edit.clear()
            self.max_tokens_edit.clear()
            self.timeout_edit.clear()
