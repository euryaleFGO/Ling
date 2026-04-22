"""
说话人管理页面

功能：
- 读取/展示 spk2info.pt 中的说话人列表
- 上传音频 + 提示文本，登记（零样本克隆）说话人
- 删除说话人
- 重命名说话人（本质是 key 改名）

说明：
- 这里直接调用本地 CosyVoice 模型进行 add_zero_shot_spk，因此需要本机已配置好 TTS 依赖与模型文件。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QFormLayout,
)


class SpeakerPage(QWidget):
    """说话人管理页面"""

    def __init__(self):
        super().__init__()
        self.project_root = Path(__file__).parent.parent.parent.parent  # .../Liying
        self.src_path = self.project_root / "src"
        if str(self.src_path) not in sys.path:
            sys.path.insert(0, str(self.src_path))

        # TTS 根目录（让 from engine import ... 可用）
        self.tts_root = self.project_root / "src" / "backend" / "tts"
        if str(self.tts_root) not in sys.path:
            sys.path.insert(0, str(self.tts_root))

        # Matcha-TTS（cosyvoice 依赖）
        self.matcha_path = self.tts_root / "third_party" / "Matcha-TTS"
        if str(self.matcha_path) not in sys.path:
            sys.path.insert(0, str(self.matcha_path))

        try:
            from core.settings import AppSettings
            s = AppSettings.load()
            self.model_dir = s.tts_model_dir
        except Exception:
            self.model_dir = self.project_root / "models" / "TTS" / "CosyVoice2-0.5B"
        self.spk2info_path = self.model_dir / "spk2info.pt"

        self._tts = None
        self.init_ui()
        self.refresh_speakers()

    # ---------------- UI ----------------
    def init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("说话人管理")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1b5e20;")
        layout.addWidget(title)

        # --- 列表组 ---
        list_group = QGroupBox("说话人列表")
        list_layout = QVBoxLayout()
        list_layout.setSpacing(10)

        self.speaker_list = QListWidget()
        self.speaker_list.setMinimumHeight(220)
        list_layout.addWidget(self.speaker_list)

        list_btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setProperty("class", "secondary")
        self.refresh_btn.clicked.connect(self.refresh_speakers)

        self.rename_btn = QPushButton("重命名")
        self.rename_btn.setProperty("class", "secondary")
        self.rename_btn.clicked.connect(self.rename_selected)

        self.delete_btn = QPushButton("删除")
        self.delete_btn.setProperty("class", "secondary")
        self.delete_btn.clicked.connect(self.delete_selected)

        list_btn_row.addWidget(self.refresh_btn)
        list_btn_row.addStretch()
        list_btn_row.addWidget(self.rename_btn)
        list_btn_row.addWidget(self.delete_btn)
        list_layout.addLayout(list_btn_row)

        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        # --- 登记组 ---
        reg_group = QGroupBox("声音克隆登记说话人（零样本）")
        reg_form = QFormLayout()
        reg_form.setSpacing(12)

        self.new_spk_name = QLineEdit()
        self.new_spk_name.setPlaceholderText("例如：小明 / 明前奶绿（将作为说话人ID）")
        reg_form.addRow("说话人名称(ID):", self.new_spk_name)

        audio_row = QHBoxLayout()
        self.audio_path_edit = QLineEdit()
        self.audio_path_edit.setPlaceholderText("选择一段你说话的 wav 文件（建议 16k/mono，非必须）")
        self.browse_audio_btn = QPushButton("选择文件")
        self.browse_audio_btn.setProperty("class", "secondary")
        self.browse_audio_btn.clicked.connect(self.pick_audio)
        audio_row.addWidget(self.audio_path_edit, 1)
        audio_row.addWidget(self.browse_audio_btn)
        reg_form.addRow("参考音频:", audio_row)

        self.prompt_text = QTextEdit()
        self.prompt_text.setPlaceholderText("填写这段参考音频里你说的内容（越准确越好）")
        self.prompt_text.setMinimumHeight(90)
        reg_form.addRow("对应文本:", self.prompt_text)

        reg_btn_row = QHBoxLayout()
        reg_btn_row.addStretch()
        self.register_btn = QPushButton("登记说话人")
        self.register_btn.clicked.connect(self.register_speaker)
        reg_btn_row.addWidget(self.register_btn)
        reg_form.addRow("", reg_btn_row)

        reg_group.setLayout(reg_form)
        layout.addWidget(reg_group)

        layout.addStretch()
        scroll.setWidget(content)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(scroll)

    # ---------------- TTS/Spk helpers ----------------
    def _ensure_tts(self):
        if self._tts is not None:
            return self._tts

        if not self.model_dir.exists():
            raise FileNotFoundError(f"模型目录不存在：{self.model_dir}")

        from engine import CosyvoiceRealTimeTTS  # type: ignore

        # 这里 reference_audio_path 仅用于“对话时克隆”，登记说话人时我们会单独加载用户上传的 wav
        self._tts = CosyvoiceRealTimeTTS(str(self.model_dir), reference_audio_path=None, load_jit=False, load_trt=False)
        return self._tts

    def _load_spk2info(self) -> dict:
        import torch

        if not self.spk2info_path.exists():
            return {}
        return torch.load(str(self.spk2info_path), map_location="cpu") or {}

    def _save_spk2info(self, spk2info: dict):
        import torch

        self.spk2info_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(spk2info, str(self.spk2info_path))

        # 同步到当前 TTS 实例（如果已经初始化）
        if self._tts is not None and hasattr(self._tts, "cosyvoice") and hasattr(self._tts.cosyvoice, "frontend"):
            self._tts.cosyvoice.frontend.spk2info = spk2info

    # ---------------- actions ----------------
    def refresh_speakers(self):
        try:
            spk2info = self._load_spk2info()
            self.speaker_list.clear()
            for spk_id in sorted(spk2info.keys()):
                self.speaker_list.addItem(QListWidgetItem(spk_id))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"刷新失败：{e}")

    def pick_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择参考音频",
            str(self.project_root),
            "Audio Files (*.wav *.mp3 *.flac *.m4a);;All Files (*)",
        )
        if path:
            self.audio_path_edit.setText(path)

    def _get_selected_spk(self) -> str | None:
        item = self.speaker_list.currentItem()
        return item.text().strip() if item else None

    def delete_selected(self):
        spk_id = self._get_selected_spk()
        if not spk_id:
            QMessageBox.information(self, "提示", "请先选择一个说话人。")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除说话人：{spk_id} ？\n（会从 spk2info.pt 中移除）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            spk2info = self._load_spk2info()
            if spk_id not in spk2info:
                QMessageBox.warning(self, "提示", "该说话人不存在或已被删除。")
                self.refresh_speakers()
                return
            del spk2info[spk_id]
            self._save_spk2info(spk2info)
            self.refresh_speakers()
            QMessageBox.information(self, "成功", f"已删除：{spk_id}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除失败：{e}")

    def rename_selected(self):
        spk_id = self._get_selected_spk()
        if not spk_id:
            QMessageBox.information(self, "提示", "请先选择一个说话人。")
            return

        new_name = self.new_spk_name.text().strip()
        if not new_name:
            QMessageBox.information(self, "提示", "请在“说话人名称(ID)”里输入新名字，再点重命名。")
            return
        if new_name == spk_id:
            return

        try:
            spk2info = self._load_spk2info()
            if spk_id not in spk2info:
                QMessageBox.warning(self, "提示", "该说话人不存在。")
                self.refresh_speakers()
                return
            if new_name in spk2info:
                QMessageBox.warning(self, "提示", "新名字已存在，请换一个。")
                return

            spk2info[new_name] = spk2info.pop(spk_id)
            self._save_spk2info(spk2info)
            self.refresh_speakers()
            QMessageBox.information(self, "成功", f"已重命名：{spk_id} → {new_name}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重命名失败：{e}")

    def register_speaker(self):
        spk_id = self.new_spk_name.text().strip()
        audio_path = self.audio_path_edit.text().strip()
        prompt_text = self.prompt_text.toPlainText().strip()

        if not spk_id:
            QMessageBox.information(self, "提示", "请填写“说话人名称(ID)”。")
            return
        if not audio_path or not Path(audio_path).exists():
            QMessageBox.information(self, "提示", "请先选择有效的参考音频文件。")
            return
        if not prompt_text:
            QMessageBox.information(self, "提示", "请填写参考音频对应的文本。")
            return

        try:
            tts = self._ensure_tts()

            # 统一加载为 16k（cosyvoice 要求）
            prompt_speech_16k = tts.load_wav_func(audio_path, 16000)

            spk2info = self._load_spk2info()
            if spk_id in spk2info:
                reply = QMessageBox.question(
                    self,
                    "覆盖确认",
                    f"说话人 {spk_id} 已存在，是否覆盖？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            self.register_btn.setEnabled(False)
            self.register_btn.setText("登记中...")
            QApplication = None
            try:
                # 这里避免 UI 卡死：简单处理一次事件循环
                from PyQt6.QtWidgets import QApplication as _QApp
                QApplication = _QApp
                QApplication.processEvents()
            except Exception:
                pass

            ok = tts.cosyvoice.add_zero_shot_spk(
                prompt_text=prompt_text,
                prompt_speech_16k=prompt_speech_16k,
                zero_shot_spk_id=spk_id,
            )
            if not ok:
                raise RuntimeError("add_zero_shot_spk 返回失败")

            # 保存到 spk2info.pt（官方方法）
            tts.cosyvoice.save_spkinfo()

            # 重新加载并刷新（确保 UI 与磁盘一致）
            self.refresh_speakers()
            QMessageBox.information(self, "成功", f"登记完成：{spk_id}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"登记失败：{e}")
        finally:
            self.register_btn.setEnabled(True)
            self.register_btn.setText("登记说话人")

