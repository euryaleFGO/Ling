"""
数据库管理页面 - 增强版
支持对话记录查看、记忆管理、搜索等功能
"""
import sys
sys.path.insert(0, 'e:/Avalon/Chaldea/Liying')

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QGroupBox, QPushButton, QFormLayout, 
    QMessageBox, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QListWidget, QListWidgetItem,
    QSplitter, QTextEdit, QFrame, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from datetime import datetime


class DatabasePage(QWidget):
    """数据库管理页面"""
    
    def __init__(self):
        super().__init__()
        self.current_session_id = None
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # 页面标题
        title = QLabel("数据库管理")
        title.setProperty("class", "title")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(title)
        
        # 状态栏
        status_widget = self.create_status_bar()
        layout.addWidget(status_widget)
        
        # 标签页
        tabs = QTabWidget()
        tabs.addTab(self.create_conversations_tab(), "💬 对话记录")
        tabs.addTab(self.create_memories_tab(), "🧠 长期记忆")
        tabs.addTab(self.create_settings_tab(), "⚙️ 配置管理")
        layout.addWidget(tabs, 1)
    
    def create_status_bar(self) -> QWidget:
        """创建状态栏"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 15, 20, 15)
        
        # MongoDB 状态
        mongo_icon = QLabel("🗄️")
        mongo_icon.setStyleSheet("font-size: 20px;")
        self.mongo_status = QLabel("MongoDB: 检查中...")
        self.mongo_status.setStyleSheet("color: #f9e2af;")
        
        # 统计信息
        self.stats_label = QLabel("加载中...")
        self.stats_label.setStyleSheet("color: #6c7086;")
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setProperty("class", "secondary")
        refresh_btn.setFixedWidth(100)
        refresh_btn.clicked.connect(self.load_data)
        
        layout.addWidget(mongo_icon)
        layout.addWidget(self.mongo_status)
        layout.addSpacing(30)
        layout.addWidget(self.stats_label)
        layout.addStretch()
        layout.addWidget(refresh_btn)
        
        return widget
    
    def create_conversations_tab(self) -> QWidget:
        """创建对话记录标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 15, 0, 0)
        layout.setSpacing(15)
        
        # 左侧：会话列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        
        # 搜索框
        search_layout = QHBoxLayout()
        self.conv_search = QLineEdit()
        self.conv_search.setPlaceholderText("🔍 搜索对话...")
        self.conv_search.setProperty("class", "search")
        self.conv_search.textChanged.connect(self.filter_conversations)
        search_layout.addWidget(self.conv_search)
        left_layout.addLayout(search_layout)
        
        # 会话列表
        self.session_list = QListWidget()
        self.session_list.setMinimumWidth(280)
        self.session_list.itemClicked.connect(self.on_session_selected)
        left_layout.addWidget(self.session_list)
        
        # 会话操作按钮
        conv_btn_layout = QHBoxLayout()
        self.delete_session_btn = QPushButton("🗑️ 删除会话")
        self.delete_session_btn.setProperty("class", "danger")
        self.delete_session_btn.clicked.connect(self.delete_selected_session)
        self.delete_session_btn.setEnabled(False)
        
        self.clear_all_conv_btn = QPushButton("清空全部")
        self.clear_all_conv_btn.setProperty("class", "secondary")
        self.clear_all_conv_btn.clicked.connect(self.clear_all_conversations)
        
        conv_btn_layout.addWidget(self.delete_session_btn)
        conv_btn_layout.addWidget(self.clear_all_conv_btn)
        left_layout.addLayout(conv_btn_layout)
        
        # 右侧：消息详情
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # 会话信息
        self.session_info = QLabel("选择左侧会话查看详情")
        self.session_info.setStyleSheet("color: #6c7086; font-size: 14px;")
        right_layout.addWidget(self.session_info)
        
        # 消息列表
        self.message_area = QScrollArea()
        self.message_area.setWidgetResizable(True)
        self.message_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.message_layout.setSpacing(10)
        self.message_area.setWidget(self.message_container)
        
        right_layout.addWidget(self.message_area, 1)
        
        # 使用 Splitter 分隔
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 500])
        
        layout.addWidget(splitter)
        
        return widget
    
    def create_memories_tab(self) -> QWidget:
        """创建长期记忆标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 15, 0, 0)
        layout.setSpacing(15)
        
        # 搜索和过滤
        filter_layout = QHBoxLayout()
        
        self.memory_search = QLineEdit()
        self.memory_search.setPlaceholderText("🔍 搜索记忆内容...")
        self.memory_search.textChanged.connect(self.filter_memories)
        
        self.memory_type_filter = QLineEdit()
        self.memory_type_filter.setPlaceholderText("类型筛选 (如: fact, preference)")
        self.memory_type_filter.setMaximumWidth(200)
        
        filter_btn = QPushButton("筛选")
        filter_btn.setProperty("class", "secondary")
        filter_btn.clicked.connect(self.filter_memories)
        
        filter_layout.addWidget(self.memory_search, 1)
        filter_layout.addWidget(self.memory_type_filter)
        filter_layout.addWidget(filter_btn)
        layout.addLayout(filter_layout)
        
        # 记忆表格
        self.memory_table = QTableWidget()
        self.memory_table.setColumnCount(5)
        self.memory_table.setHorizontalHeaderLabels(["类型", "内容", "重要性", "创建时间", "操作"])
        self.memory_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.memory_table.setColumnWidth(0, 100)
        self.memory_table.setColumnWidth(2, 80)
        self.memory_table.setColumnWidth(3, 150)
        self.memory_table.setColumnWidth(4, 80)
        self.memory_table.verticalHeader().setVisible(False)
        self.memory_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.memory_table, 1)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        delete_selected_btn = QPushButton("删除选中")
        delete_selected_btn.setProperty("class", "danger")
        delete_selected_btn.clicked.connect(self.delete_selected_memories)
        
        clear_memories_btn = QPushButton("清空全部记忆")
        clear_memories_btn.setProperty("class", "secondary")
        clear_memories_btn.clicked.connect(self.clear_all_memories)
        
        btn_layout.addWidget(delete_selected_btn)
        btn_layout.addWidget(clear_memories_btn)
        layout.addLayout(btn_layout)
        
        return widget
    
    def create_settings_tab(self) -> QWidget:
        """创建配置管理标签页"""
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(20)
        
        # MongoDB 配置
        mongo_group = QGroupBox("MongoDB 配置")
        mongo_layout = QFormLayout()
        mongo_layout.setSpacing(12)
        mongo_layout.setContentsMargins(15, 20, 15, 15)
        
        self.mongo_host = QLineEdit("localhost")
        self.mongo_port = QLineEdit("27017")
        self.mongo_db = QLineEdit("liying_db")
        
        mongo_layout.addRow("主机:", self.mongo_host)
        mongo_layout.addRow("端口:", self.mongo_port)
        mongo_layout.addRow("数据库:", self.mongo_db)
        
        test_btn = QPushButton("测试连接")
        test_btn.setProperty("class", "secondary")
        test_btn.setMaximumWidth(120)
        test_btn.clicked.connect(self.test_connection)
        mongo_layout.addRow("", test_btn)
        
        mongo_group.setLayout(mongo_layout)
        layout.addWidget(mongo_group)
        
        # 数据统计
        stats_group = QGroupBox("数据统计")
        stats_layout = QVBoxLayout()
        stats_layout.setContentsMargins(15, 20, 15, 15)
        
        self.detail_stats_table = QTableWidget()
        self.detail_stats_table.setColumnCount(2)
        self.detail_stats_table.setHorizontalHeaderLabels(["数据项", "数量"])
        self.detail_stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.detail_stats_table.setColumnWidth(1, 150)
        self.detail_stats_table.verticalHeader().setVisible(False)
        self.detail_stats_table.setMinimumHeight(180)
        self.detail_stats_table.setMaximumHeight(220)
        
        stats_layout.addWidget(self.detail_stats_table)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # 危险操作区
        danger_group = QGroupBox("⚠️ 危险操作")
        danger_group.setStyleSheet("""
            QGroupBox {
                border-color: #f38ba8;
                border-width: 2px;
            }
            QGroupBox::title {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #f38ba8, stop:1 #eba0ac);
            }
        """)
        danger_layout = QVBoxLayout()
        danger_layout.setContentsMargins(15, 20, 15, 15)
        danger_layout.setSpacing(15)
        
        warning_label = QLabel("以下操作将永久删除数据，无法恢复！")
        warning_label.setStyleSheet("color: #f38ba8; font-size: 13px;")
        danger_layout.addWidget(warning_label)
        
        btn_row1 = QHBoxLayout()
        
        clear_chroma_btn = QPushButton("🔥 清空向量数据库")
        clear_chroma_btn.setProperty("class", "danger")
        clear_chroma_btn.setMinimumWidth(160)
        clear_chroma_btn.setMinimumHeight(40)
        clear_chroma_btn.clicked.connect(self.clear_chroma)
        
        reset_all_btn = QPushButton("💀 完全重置所有数据")
        reset_all_btn.setProperty("class", "danger")
        reset_all_btn.setMinimumWidth(180)
        reset_all_btn.setMinimumHeight(40)
        reset_all_btn.clicked.connect(self.reset_all_data)
        
        btn_row1.addWidget(clear_chroma_btn)
        btn_row1.addWidget(reset_all_btn)
        btn_row1.addStretch()
        
        danger_layout.addLayout(btn_row1)
        danger_group.setLayout(danger_layout)
        layout.addWidget(danger_group)
        
        layout.addStretch()
        
        scroll.setWidget(widget)
        return scroll
    
    # ==================== 数据加载 ====================
    
    def load_data(self):
        """加载所有数据"""
        self.check_connection()
        self.load_conversations()
        self.load_memories()
        self.load_stats()
    
    def check_connection(self):
        """检查数据库连接"""
        try:
            from backtend.LLM.database import get_db
            db = get_db()
            db.command('ping')
            self.mongo_status.setText("MongoDB: 已连接 ✓")
            self.mongo_status.setStyleSheet("color: #a6e3a1;")
        except Exception as e:
            self.mongo_status.setText("MongoDB: 连接失败 ✗")
            self.mongo_status.setStyleSheet("color: #f38ba8;")
    
    def load_stats(self):
        """加载统计信息"""
        try:
            from backtend.LLM.database import get_db
            db = get_db()
            
            conv_count = db.conversations.count_documents({})
            msg_count = sum(len(c.get('messages', [])) for c in db.conversations.find())
            mem_count = db.memories.count_documents({})
            
            self.stats_label.setText(
                f"📊 {conv_count} 个会话 | {msg_count} 条消息 | {mem_count} 条记忆"
            )
            
            # 详细统计表格
            stats = [
                ("对话会话数", conv_count),
                ("消息总数", msg_count),
                ("长期记忆", mem_count),
                ("知识库条目", db.knowledge_base.count_documents({})),
                ("角色设定", db.character_settings.count_documents({})),
            ]
            
            try:
                from backtend.LLM.database import get_chroma_client
                client = get_chroma_client()
                collection = client.get_or_create_collection("liying_memories")
                stats.append(("向量数据", collection.count()))
            except:
                stats.append(("向量数据", "N/A"))
            
            self.detail_stats_table.setRowCount(len(stats))
            for i, (name, count) in enumerate(stats):
                self.detail_stats_table.setItem(i, 0, QTableWidgetItem(name))
                item = QTableWidgetItem(str(count))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.detail_stats_table.setItem(i, 1, item)
                
        except Exception as e:
            self.stats_label.setText(f"统计加载失败: {e}")
    
    def load_conversations(self):
        """加载对话列表"""
        self.session_list.clear()
        self.all_sessions = []
        
        try:
            from backtend.LLM.database import get_db
            db = get_db()
            
            sessions = list(db.conversations.find().sort("updated_at", -1))
            self.all_sessions = sessions
            
            for session in sessions:
                item = QListWidgetItem()
                
                # 获取会话信息
                session_id = session.get('session_id', 'unknown')[:8]
                msg_count = len(session.get('messages', []))
                status = "🟢" if session.get('status') == 'active' else "⚪"
                
                # 获取最后一条消息预览
                messages = session.get('messages', [])
                preview = ""
                if messages:
                    last_msg = messages[-1].get('content', '')
                    preview = last_msg[:30] + "..." if len(last_msg) > 30 else last_msg
                
                # 时间
                updated = session.get('updated_at')
                time_str = updated.strftime("%m-%d %H:%M") if updated else "未知"
                
                item.setText(f"{status} {session_id}  ({msg_count}条)\n{preview}\n{time_str}")
                item.setData(Qt.ItemDataRole.UserRole, session.get('session_id'))
                item.setSizeHint(QSize(260, 80))
                
                self.session_list.addItem(item)
                
        except Exception as e:
            print(f"加载对话失败: {e}")
    
    def load_memories(self):
        """加载记忆列表"""
        self.memory_table.setRowCount(0)
        self.all_memories = []
        
        try:
            from backtend.LLM.database import get_db
            db = get_db()
            
            memories = list(db.memories.find().sort("created_at", -1).limit(100))
            self.all_memories = memories
            
            self.populate_memory_table(memories)
                
        except Exception as e:
            print(f"加载记忆失败: {e}")
    
    def populate_memory_table(self, memories):
        """填充记忆表格"""
        self.memory_table.setRowCount(len(memories))
        
        type_colors = {
            'fact': '#89b4fa',
            'preference': '#a6e3a1', 
            'event': '#f9e2af',
            'emotion': '#f38ba8',
            'summary': '#cba6f7'
        }
        
        for i, mem in enumerate(memories):
            # 类型
            mem_type = mem.get('memory_type', 'unknown')
            type_item = QTableWidgetItem(mem_type)
            color = type_colors.get(mem_type, '#cdd6f4')
            type_item.setForeground(Qt.GlobalColor.white)
            self.memory_table.setItem(i, 0, type_item)
            
            # 内容
            content = mem.get('content', '')
            content_preview = content[:50] + "..." if len(content) > 50 else content
            self.memory_table.setItem(i, 1, QTableWidgetItem(content_preview))
            
            # 重要性
            importance = mem.get('importance', 0.5)
            importance_item = QTableWidgetItem(f"{importance:.1f}")
            importance_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.memory_table.setItem(i, 2, importance_item)
            
            # 时间
            created = mem.get('created_at')
            time_str = created.strftime("%Y-%m-%d %H:%M") if created else "未知"
            self.memory_table.setItem(i, 3, QTableWidgetItem(time_str))
            
            # 删除按钮
            delete_btn = QPushButton("🗑️")
            delete_btn.setProperty("class", "icon")
            delete_btn.setToolTip("删除此记忆")
            mem_id = mem.get('memory_id')
            delete_btn.clicked.connect(lambda checked, mid=mem_id: self.delete_memory(mid))
            self.memory_table.setCellWidget(i, 4, delete_btn)
    
    # ==================== 对话操作 ====================
    
    def filter_conversations(self):
        """过滤对话"""
        keyword = self.conv_search.text().lower()
        
        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            text = item.text().lower()
            item.setHidden(keyword not in text)
    
    def on_session_selected(self, item: QListWidgetItem):
        """选中会话时显示消息"""
        session_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_session_id = session_id
        self.delete_session_btn.setEnabled(True)
        
        try:
            from backtend.LLM.database import get_db
            db = get_db()
            
            session = db.conversations.find_one({"session_id": session_id})
            if not session:
                return
            
            # 更新会话信息
            created = session.get('created_at')
            time_str = created.strftime("%Y-%m-%d %H:%M:%S") if created else "未知"
            self.session_info.setText(
                f"会话 ID: {session_id[:16]}... | 创建时间: {time_str}"
            )
            
            # 清空消息区域
            while self.message_layout.count():
                child = self.message_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # 显示消息
            messages = session.get('messages', [])
            for msg in messages:
                self.add_message_bubble(
                    msg.get('role', 'user'),
                    msg.get('content', ''),
                    msg.get('timestamp')
                )
            
            # 添加底部间距
            self.message_layout.addStretch()
            
        except Exception as e:
            print(f"加载消息失败: {e}")
    
    def add_message_bubble(self, role: str, content: str, timestamp=None):
        """添加消息气泡"""
        bubble = QFrame()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 10, 12, 10)
        bubble_layout.setSpacing(5)
        
        # 角色标签
        role_label = QLabel("👤 用户" if role == "user" else "🤖 玲")
        role_label.setStyleSheet("font-size: 12px; color: #6c7086;")
        
        # 消息内容
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        if role == "user":
            bubble.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #89b4fa, stop:1 #b4befe);
                    border-radius: 16px 16px 4px 16px;
                }
            """)
            content_label.setStyleSheet("color: #1e1e2e;")
        else:
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #313244;
                    border-radius: 16px 16px 16px 4px;
                }
            """)
            content_label.setStyleSheet("color: #cdd6f4;")
        
        bubble_layout.addWidget(role_label)
        bubble_layout.addWidget(content_label)
        
        # 时间戳
        if timestamp:
            time_label = QLabel(timestamp.strftime("%H:%M:%S") if hasattr(timestamp, 'strftime') else str(timestamp))
            time_label.setStyleSheet("font-size: 11px; color: #6c7086;")
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            bubble_layout.addWidget(time_label)
        
        # 容器布局
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        if role == "user":
            container_layout.addStretch()
            container_layout.addWidget(bubble)
            bubble.setMaximumWidth(450)
        else:
            container_layout.addWidget(bubble)
            container_layout.addStretch()
            bubble.setMaximumWidth(450)
        
        self.message_layout.addWidget(container)
    
    def delete_selected_session(self):
        """删除选中的会话"""
        if not self.current_session_id:
            return
        
        reply = QMessageBox.warning(
            self, "确认删除",
            f"确定要删除此会话吗？\n会话 ID: {self.current_session_id[:16]}...",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backtend.LLM.database import get_db
                db = get_db()
                db.conversations.delete_one({"session_id": self.current_session_id})
                
                QMessageBox.information(self, "成功", "会话已删除")
                self.current_session_id = None
                self.delete_session_btn.setEnabled(False)
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")
    
    def clear_all_conversations(self):
        """清空所有对话"""
        reply = QMessageBox.warning(
            self, "⚠️ 确认清空",
            "确定要清空所有对话记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backtend.LLM.database import get_db
                db = get_db()
                result = db.conversations.delete_many({})
                QMessageBox.information(self, "成功", f"已删除 {result.deleted_count} 个会话")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空失败: {e}")
    
    # ==================== 记忆操作 ====================
    
    def filter_memories(self):
        """过滤记忆"""
        keyword = self.memory_search.text().lower()
        type_filter = self.memory_type_filter.text().lower().strip()
        
        filtered = []
        for mem in self.all_memories:
            content = mem.get('content', '').lower()
            mem_type = mem.get('memory_type', '').lower()
            
            if keyword and keyword not in content:
                continue
            if type_filter and type_filter not in mem_type:
                continue
            filtered.append(mem)
        
        self.populate_memory_table(filtered)
    
    def delete_memory(self, memory_id: str):
        """删除单条记忆"""
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除此记忆吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backtend.LLM.database import get_db
                db = get_db()
                db.memories.delete_one({"memory_id": memory_id})
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")
    
    def delete_selected_memories(self):
        """删除选中的记忆"""
        selected_rows = set(item.row() for item in self.memory_table.selectedItems())
        
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择要删除的记忆")
            return
        
        reply = QMessageBox.warning(
            self, "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 条记忆吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backtend.LLM.database import get_db
                db = get_db()
                
                # 获取要删除的记忆 ID
                memory_ids = []
                for row in selected_rows:
                    if row < len(self.all_memories):
                        memory_ids.append(self.all_memories[row].get('memory_id'))
                
                if memory_ids:
                    db.memories.delete_many({"memory_id": {"$in": memory_ids}})
                
                QMessageBox.information(self, "成功", f"已删除 {len(memory_ids)} 条记忆")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")
    
    def clear_all_memories(self):
        """清空所有记忆"""
        reply = QMessageBox.warning(
            self, "⚠️ 确认清空",
            "确定要清空所有长期记忆吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backtend.LLM.database import get_db
                db = get_db()
                result = db.memories.delete_many({})
                QMessageBox.information(self, "成功", f"已删除 {result.deleted_count} 条记忆")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空失败: {e}")
    
    # ==================== 配置操作 ====================
    
    def test_connection(self):
        """测试数据库连接"""
        try:
            from backtend.LLM.database import get_db
            db = get_db()
            db.command('ping')
            QMessageBox.information(self, "成功", "数据库连接正常！")
            self.check_connection()
        except Exception as e:
            QMessageBox.critical(self, "失败", f"连接失败: {e}")
    
    def clear_chroma(self):
        """清空向量数据库"""
        reply = QMessageBox.warning(
            self, "⚠️ 确认清空",
            "确定要清空向量数据库吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from backtend.LLM.database import get_chroma_client
                client = get_chroma_client()
                try:
                    client.delete_collection("liying_memories")
                except:
                    pass
                QMessageBox.information(self, "成功", "向量数据库已清空")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空失败: {e}")
    
    def reset_all_data(self):
        """重置所有数据"""
        reply = QMessageBox.warning(
            self, "⚠️ 危险操作",
            "确定要重置所有数据吗？\n\n"
            "这将清空：\n"
            "• 所有对话历史\n"
            "• 所有长期记忆\n"
            "• 所有向量数据\n"
            "• 角色设定\n\n"
            "此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            confirm = QMessageBox.question(
                self, "再次确认",
                "真的要删除所有数据吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    from backtend.LLM.database import get_db, get_chroma_client
                    db = get_db()
                    
                    db.conversations.delete_many({})
                    db.memories.delete_many({})
                    db.knowledge_base.delete_many({})
                    db.character_settings.delete_many({})
                    db.user_profiles.delete_many({})
                    
                    try:
                        client = get_chroma_client()
                        client.delete_collection("liying_memories")
                    except:
                        pass
                    
                    QMessageBox.information(self, "成功", "所有数据已重置")
                    self.load_data()
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"重置失败: {e}")
