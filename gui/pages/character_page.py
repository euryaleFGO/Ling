"""
角色设定页面
"""
import sys
sys.path.insert(0, 'e:/Avalon/Chaldea/Liying')

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QTextEdit, QGroupBox, QPushButton,
    QFormLayout, QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt


class CharacterPage(QWidget):
    """角色设定页面"""
    
    def __init__(self):
        super().__init__()
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
        title = QLabel("角色设定")
        title.setProperty("class", "page-title")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        # 基本信息组
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout()
        basic_layout.setSpacing(15)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：玲")
        basic_layout.addRow("角色名称:", self.name_edit)
        
        self.nickname_edit = QLineEdit()
        self.nickname_edit.setPlaceholderText("用户对角色的称呼，例如：小玲")
        basic_layout.addRow("昵称:", self.nickname_edit)
        
        self.user_name_edit = QLineEdit()
        self.user_name_edit.setPlaceholderText("角色如何称呼用户，例如：主人")
        basic_layout.addRow("用户称呼:", self.user_name_edit)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # 性格设定组
        personality_group = QGroupBox("性格设定")
        personality_layout = QVBoxLayout()
        personality_layout.setSpacing(10)
        
        personality_label = QLabel("角色的性格特点和行为方式：")
        self.personality_edit = QTextEdit()
        self.personality_edit.setPlaceholderText(
            "例如：\n"
            "- 温柔体贴，总是关心用户的状态\n"
            "- 有点傲娇，偶尔会害羞\n"
            "- 喜欢撒娇，会用可爱的语气说话\n"
            "- 知识渊博，能够回答各种问题"
        )
        self.personality_edit.setMinimumHeight(120)
        
        personality_layout.addWidget(personality_label)
        personality_layout.addWidget(self.personality_edit)
        personality_group.setLayout(personality_layout)
        layout.addWidget(personality_group)
        
        # 系统提示词组
        prompt_group = QGroupBox("系统提示词")
        prompt_layout = QVBoxLayout()
        prompt_layout.setSpacing(10)
        
        prompt_label = QLabel("发送给 LLM 的系统提示词（高级设置）：")
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setPlaceholderText(
            "留空则使用默认模板。\n"
            "可用变量：{name}=角色名, {user_name}=用户称呼, {personality}=性格设定"
        )
        self.system_prompt_edit.setMinimumHeight(150)
        
        prompt_layout.addWidget(prompt_label)
        prompt_layout.addWidget(self.system_prompt_edit)
        prompt_group.setLayout(prompt_layout)
        layout.addWidget(prompt_group)
        
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
    
    def load_settings(self):
        """从数据库加载设置"""
        try:
            from backtend.LLM.database import KnowledgeDAO
            dao = KnowledgeDAO()
            settings = dao.get_character_settings()
            
            if settings:
                self.name_edit.setText(settings.get('name', ''))
                self.nickname_edit.setText(settings.get('nickname', ''))
                self.user_name_edit.setText(settings.get('user_name', ''))
                self.personality_edit.setPlainText(settings.get('personality', ''))
                self.system_prompt_edit.setPlainText(settings.get('system_prompt', ''))
        except Exception as e:
            print(f"加载角色设置失败: {e}")
    
    def save_settings(self):
        """保存设置到数据库"""
        try:
            from backtend.LLM.database import KnowledgeDAO
            dao = KnowledgeDAO()
            
            settings = {
                'name': self.name_edit.text().strip(),
                'nickname': self.nickname_edit.text().strip(),
                'user_name': self.user_name_edit.text().strip(),
                'personality': self.personality_edit.toPlainText().strip(),
                'system_prompt': self.system_prompt_edit.toPlainText().strip()
            }
            
            dao.save_character_settings(settings)
            QMessageBox.information(self, "成功", "角色设置已保存！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败：{e}")
    
    def reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, "确认重置", 
            "确定要重置为默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.name_edit.setText("玲")
            self.nickname_edit.setText("小玲")
            self.user_name_edit.setText("主人")
            self.personality_edit.setPlainText(
                "- 温柔体贴，总是关心用户的状态\n"
                "- 有点傲娇，偶尔会害羞\n"
                "- 喜欢撒娇，会用可爱的语气说话\n"
                "- 聪明伶俐，知识渊博"
            )
            self.system_prompt_edit.clear()
