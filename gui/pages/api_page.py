"""
API 配置页面
"""
import sys
sys.path.insert(0, 'e:/Avalon/Chaldea/Liying')

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QGroupBox, QPushButton, QComboBox,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox
)
from PyQt6.QtCore import Qt
import os
from pathlib import Path


class ApiPage(QWidget):
    """API 配置页面"""
    
    def __init__(self):
        super().__init__()
        self.env_path = Path("e:/Avalon/Chaldea/Liying/backtend/.env")
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # 内容容器
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 页面标题
        title = QLabel("API 配置")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        # LLM API 配置组
        llm_group = QGroupBox("LLM 大语言模型")
        llm_layout = QFormLayout()
        llm_layout.setSpacing(15)
        
        # API 提供商选择
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["DeepSeek", "OpenAI", "Claude", "自定义"])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        llm_layout.addRow("API 提供商:", self.provider_combo)
        
        # API Base URL
        self.api_base_edit = QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.deepseek.com")
        llm_layout.addRow("API Base URL:", self.api_base_edit)
        
        # API Key
        api_key_layout = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-xxxxxxxxxxxxxxxx")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(40)
        self.show_key_btn.setProperty("class", "secondary")
        self.show_key_btn.clicked.connect(self.toggle_key_visibility)
        
        api_key_layout.addWidget(self.api_key_edit)
        api_key_layout.addWidget(self.show_key_btn)
        llm_layout.addRow("API Key:", api_key_layout)
        
        # 模型选择
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        llm_layout.addRow("模型:", self.model_combo)
        
        # 测试连接按钮
        test_layout = QHBoxLayout()
        test_layout.addStretch()
        self.test_llm_btn = QPushButton("测试连接")
        self.test_llm_btn.setProperty("class", "secondary")
        self.test_llm_btn.clicked.connect(self.test_llm_connection)
        test_layout.addWidget(self.test_llm_btn)
        llm_layout.addRow("", test_layout)
        
        llm_group.setLayout(llm_layout)
        layout.addWidget(llm_group)
        
        # TTS 配置组
        tts_group = QGroupBox("TTS 语音合成")
        tts_layout = QFormLayout()
        tts_layout.setSpacing(15)
        
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
        
        # 高级设置组
        advanced_group = QGroupBox("高级设置")
        advanced_layout = QFormLayout()
        advanced_layout.setSpacing(15)
        
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
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.reset_btn = QPushButton("重置默认")
        self.reset_btn.setProperty("class", "secondary")
        self.reset_btn.clicked.connect(self.reset_settings)
        
        self.save_btn = QPushButton("保存设置")
        self.save_btn.clicked.connect(self.save_settings)
        
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)
        
        layout.addStretch()
        
        scroll.setWidget(content)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
    
    def on_provider_changed(self, provider: str):
        """切换 API 提供商时更新默认值"""
        defaults = {
            "DeepSeek": ("https://api.deepseek.com", ["deepseek-chat", "deepseek-reasoner"]),
            "OpenAI": ("https://api.openai.com/v1", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]),
            "Claude": ("https://api.anthropic.com", ["claude-3-opus", "claude-3-sonnet"]),
            "自定义": ("", [])
        }
        
        if provider in defaults:
            base_url, models = defaults[provider]
            self.api_base_edit.setPlaceholderText(base_url)
            self.model_combo.clear()
            self.model_combo.addItems(models)
    
    def toggle_key_visibility(self):
        """切换 API Key 显示/隐藏"""
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("🔒")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("👁")
    
    def load_settings(self):
        """从 .env 文件加载设置"""
        try:
            if self.env_path.exists():
                env_vars = {}
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip().strip('"\'')
                
                # 设置值
                self.api_base_edit.setText(env_vars.get('OPENAI_API_BASE', ''))
                self.api_key_edit.setText(env_vars.get('OPENAI_API_KEY', ''))
                
                model = env_vars.get('OPENAI_MODEL', '')
                if model:
                    self.model_combo.setCurrentText(model)
                
                self.temperature_edit.setText(env_vars.get('TEMPERATURE', ''))
                self.max_tokens_edit.setText(env_vars.get('MAX_TOKENS', ''))
                self.timeout_edit.setText(env_vars.get('TIMEOUT', ''))
                
        except Exception as e:
            print(f"加载 API 设置失败: {e}")
    
    def save_settings(self):
        """保存设置到 .env 文件"""
        try:
            # 读取现有的 .env 内容
            existing = {}
            if self.env_path.exists():
                with open(self.env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            existing[key.strip()] = value.strip()
            
            # 更新设置
            if self.api_base_edit.text().strip():
                existing['OPENAI_API_BASE'] = self.api_base_edit.text().strip()
            if self.api_key_edit.text().strip():
                existing['OPENAI_API_KEY'] = self.api_key_edit.text().strip()
            if self.model_combo.currentText().strip():
                existing['OPENAI_MODEL'] = self.model_combo.currentText().strip()
            if self.temperature_edit.text().strip():
                existing['TEMPERATURE'] = self.temperature_edit.text().strip()
            if self.max_tokens_edit.text().strip():
                existing['MAX_TOKENS'] = self.max_tokens_edit.text().strip()
            if self.timeout_edit.text().strip():
                existing['TIMEOUT'] = self.timeout_edit.text().strip()
            
            # 写入文件
            self.env_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.env_path, 'w', encoding='utf-8') as f:
                f.write("# API 配置\n")
                for key, value in existing.items():
                    f.write(f"{key}={value}\n")
            
            QMessageBox.information(self, "成功", "API 设置已保存！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败：{e}")
    
    def test_llm_connection(self):
        """测试 LLM 连接"""
        try:
            self.test_llm_btn.setText("测试中...")
            self.test_llm_btn.setEnabled(False)
            
            # 临时设置环境变量
            os.environ['OPENAI_API_BASE'] = self.api_base_edit.text().strip() or "https://api.deepseek.com"
            os.environ['OPENAI_API_KEY'] = self.api_key_edit.text().strip()
            os.environ['OPENAI_MODEL'] = self.model_combo.currentText().strip() or "deepseek-chat"
            
            from backtend.LLM.api_infer import OpenAIInfer
            infer = OpenAIInfer()
            response = infer.chat([{"role": "user", "content": "你好"}])
            
            if response:
                QMessageBox.information(self, "成功", f"连接成功！\n\n模型响应：{response[:100]}...")
            else:
                QMessageBox.warning(self, "失败", "连接失败，未收到响应")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接失败：{e}")
        finally:
            self.test_llm_btn.setText("测试连接")
            self.test_llm_btn.setEnabled(True)
    
    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.provider_combo.setCurrentText("DeepSeek")
            self.api_base_edit.clear()
            self.api_key_edit.clear()
            self.model_combo.setCurrentText("deepseek-chat")
            self.temperature_edit.clear()
            self.max_tokens_edit.clear()
            self.timeout_edit.clear()
