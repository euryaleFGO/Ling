# -*- coding: utf-8 -*-
"""
TTS 处理器（Mixin）

从 conversation_manager.py 拆分而来，包含 TTS 初始化、语音合成播放、
文本清洗、RMS/Viseme 口型同步等方法。

作为 mixin 被 ConversationManager 继承。
"""

from __future__ import annotations

import logging
import re
import time
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np

from core.log import log

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 项目根目录
project_root = Path(__file__).parent.parent.parent


class TTSHandler:
    """TTS 处理 Mixin —— 提供语音合成、播放、口型同步等能力。

    被 ConversationManager 继承。子类必须提供以下属性：
      config, _tts, _tts_mode, _audio_output, _current_emotion,
      _interrupt_monitoring, _on_subtitle, _on_audio_rms, _on_viseme
    """

    # Rhubarb 口型映射: shape -> (openY, form)
    VISEME_SHAPE_MAP = {
        'X': (0.00, 0.00),   # 闭嘴（静音）
        'A': (0.05, 0.00),   # 口型很小，中性
        'B': (0.25, 0.60),   # 双唇轻合（b/m/p）
        'C': (0.50, 0.20),   # 中等开口（e/辅音）
        'D': (0.85, 0.40),   # 大张口（a）
        'E': (0.55, -0.40),  # 圆嘴（o）
        'F': (0.35, -0.70),  # 窄嘴（u/w）
        'G': (0.20, 0.30),   # 轻开口（辅音）
        'H': (0.40, 0.10),   # 中等开口（l）
    }

    # ------------------------------------------------------------------
    # TTS 初始化
    # ------------------------------------------------------------------

    def _init_tts(self):
        """初始化 TTS（支持本地和远程模式）"""
        if self._tts is not None:
            return

        # 优先使用远程 TTS
        if self.config.tts_remote_url:
            try:
                from backend.tts.remote_client import RemoteTTSClient, RemoteTTSConfig

                remote_config = RemoteTTSConfig(
                    base_url=self.config.tts_remote_url,
                    spk_id=self.config.tts_spk_id,
                )
                client = RemoteTTSClient(remote_config)

                if client.health_check():
                    self._tts = client
                    self._tts_mode = "remote"
                    log.debug(
                        f"[对话] TTS 远程服务初始化完成: "
                        f"{self.config.tts_remote_url}"
                    )
                    return
                else:
                    log.warn(f"TTS 远程服务不可用: {self.config.tts_remote_url}")
                    log.debug("尝试使用本地 TTS...")
            except Exception as e:
                log.warn(f"TTS 远程服务初始化失败: {e}")
                log.debug("尝试使用本地 TTS...")

        # 本地 TTS
        try:
            from backend.tts.engine import CosyvoiceRealTimeTTS

            model_dir = self.config.tts_model_dir
            if not model_dir:
                try:
                    from core.config_manager import get_config_manager
                    cfg = get_config_manager().config
                    if cfg.tts.model_dir:
                        model_dir = cfg.tts.model_dir
                except Exception:
                    logger.debug("Failed to load TTS model dir from ConfigManager")
                if not model_dir:
                    for p in [
                        project_root / "models" / "TTS" / "CosyVoice2-0.5B",
                    ]:
                        if p.exists():
                            model_dir = str(p)
                            break

            if model_dir and Path(model_dir).exists():
                self._tts = CosyvoiceRealTimeTTS(model_path=model_dir)
                self._tts_mode = "local"
                log.debug("[对话] TTS 本地引擎初始化完成")
            else:
                log.warn(f"TTS 模型目录不存在: {model_dir}")
                log.info("将使用文本输出代替语音")
                self._tts = None
                self._tts_mode = None
        except Exception as e:
            log.warn(f"TTS 初始化失败: {e}")
            log.info("将使用文本输出代替语音")
            self._tts = None
            self._tts_mode = None

    # ------------------------------------------------------------------
    # 文本清洗
    # ------------------------------------------------------------------

    def _text_for_tts(self, text: str) -> str:
        """清洗 AI 回复，便于 TTS 朗读：去 Markdown、颜文字、多余换行"""
        if not text:
            return ""
        s = text.strip()
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", s)
        s = re.sub(r"^\s*[-*]\s*\**(.+?)\**[：:]\s*", r"\1，", s, flags=re.MULTILINE)
        s = re.sub(r"^\s*[-*]\s+(.+)$", r"\1，", s, flags=re.MULTILINE)
        s = re.sub(r"\([^()]*[•◍ᴗ￣▽ω´`～～\s]+[^()]*\)", "", s)
        s = re.sub(r"（[^（）]*[•◍ᴗ￣▽ω´`～～\s]+[^（）]*）", "", s)
        s = re.sub(r"\n\s*\n\s*", "。", s)
        s = re.sub(r"\n\s*", "，", s)
        s = re.sub(r"[,，]+", "，", s)
        return s.strip() or text.strip()

    # ------------------------------------------------------------------
    # TTS 播放
    # ------------------------------------------------------------------

    def _speak(self, text: str):
        """TTS 播放（流式：边合成边播放，同时发送 RMS 驱动嘴型，支持打断）"""
        if not text:
            return
        text = self._text_for_tts(text)
        self._interrupted_text = text

        if self._tts:
            try:
                # 启动打断监听
                if self.config.enable_barge_in:
                    self._start_interrupt_monitoring()

                first_chunk = True
                t_tts_start = time.perf_counter()
                log.debug("正在合成语音...")

                expected_seg = 1
                played_segments = 0

                for chunk_data in self._tts.generate_audio_streaming(
                    text, use_clone=True, max_workers=2,
                ):
                    # 检查是否被打断
                    if (
                        not self._interrupt_monitoring
                        and self.config.enable_barge_in
                    ):
                        log.debug("[TTS] 播放被打断")
                        break

                    # 兼容新版（含 visemes）和旧版（3元组）
                    if len(chunk_data) == 4:
                        audio, seg_idx, total, visemes = chunk_data
                    else:
                        audio, seg_idx, total = chunk_data
                        visemes = None

                    # 段丢失检测
                    if seg_idx != expected_seg:
                        log.tts_segment(
                            f"[播放段丢失] 期望段 {expected_seg}，"
                            f"实际播放段 {seg_idx}，"
                            f"已播放 {played_segments}/"
                            f"{total if total > 0 else '?'} 段"
                        )
                    else:
                        log.tts_segment(
                            f"[播放段OK] 段 {seg_idx}/"
                            f"{total if total > 0 else '?'}，"
                            f"音频长度 {len(audio)} samples，"
                            f"采样率 {self._tts.sample_rate}"
                        )

                    expected_seg = seg_idx + 1
                    played_segments += 1

                    if first_chunk:
                        t_first_chunk = time.perf_counter() - t_tts_start
                        log.debug(
                            f"开始播放... [耗时] TTS 首包: {t_first_chunk:.2f}s"
                        )
                        first_chunk = False
                        self._send_subtitle(
                            text, is_final=True, emotion=self._current_emotion,
                        )

                    # 启动嘴型同步线程
                    if visemes and self._on_viseme:
                        lip_thread = threading.Thread(
                            target=self._send_visemes_for_chunk,
                            args=(visemes, audio, self._tts.sample_rate),
                            daemon=True,
                            name="Viseme-Sender",
                        )
                        lip_thread.start()
                    elif self._on_audio_rms:
                        rms_thread = threading.Thread(
                            target=self._send_rms_for_chunk,
                            args=(audio, self._tts.sample_rate),
                            daemon=True,
                            name="RMS-Sender",
                        )
                        rms_thread.start()

                    # 播放当前段（阻塞直到播放完）
                    self._audio_output.play_array(
                        audio,
                        self._tts.sample_rate,
                        blocking=True,
                    )

                # 停止打断监听
                if self.config.enable_barge_in:
                    self._stop_interrupt_monitoring()

                # 播放结束，重置嘴型
                if self._on_viseme:
                    self._on_viseme(0.0, 0.0)
                if self._on_audio_rms:
                    self._on_audio_rms(0.0)

                t_total = time.perf_counter() - t_tts_start
                log.tts(
                    f"[_speak] 播放完成，共 {played_segments} 段，"
                    f"总耗时 {t_total:.2f}s"
                )

                if first_chunk:
                    log.debug("TTS 未生成音频")
                return

            except Exception as e:
                log.error(f"TTS 错误: {e}")
                import traceback
                log.error(traceback.format_exc())
            finally:
                if self.config.enable_barge_in:
                    self._stop_interrupt_monitoring()

        # TTS 不可用，只显示文本
        log.debug("TTS 不可用，文本输出")
        self._send_subtitle(text, is_final=True, emotion=self._current_emotion)
        time.sleep(len(text) * 0.05)  # 模拟说话时间

    # ------------------------------------------------------------------
    # RMS / Viseme 口型同步
    # ------------------------------------------------------------------

    def _send_rms_for_chunk(self, audio, sample_rate: int):
        """在音频播放期间按 ~20fps 发送 RMS 值，驱动嘴型同步"""
        try:
            window_ms = 50
            window_samples = max(1, int(sample_rate * window_ms / 1000))

            audio_float = audio.astype(np.float32)
            max_val = np.max(np.abs(audio_float))
            if max_val > 1.0:
                audio_float = audio_float / 32768.0

            for i in range(0, len(audio_float), window_samples):
                window = audio_float[i:i + window_samples]
                rms = float(np.sqrt(np.mean(window ** 2)))
                if self._on_audio_rms:
                    self._on_audio_rms(rms)
                time.sleep(window_ms / 1000.0)
        except Exception:
            logger.debug("Audio RMS monitoring thread encountered an error")
            pass

    def _send_visemes_for_chunk(
        self, visemes: list, audio, sample_rate: int,
    ):
        """按 Rhubarb 时间线发送 viseme 口型数据，精确同步播放"""
        try:
            if not visemes:
                return
            audio_duration = len(audio) / max(1, sample_rate)
            t0 = time.perf_counter()
            interval = 1.0 / 30  # 30fps

            cue_idx = 0
            elapsed = 0.0
            while elapsed < audio_duration:
                while cue_idx < len(visemes) - 1:
                    next_start = visemes[cue_idx + 1].get('start', 999)
                    if elapsed >= next_start:
                        cue_idx += 1
                    else:
                        break
                current_shape = visemes[cue_idx].get('value', 'X')
                openY, form = self.VISEME_SHAPE_MAP.get(
                    current_shape, (0.0, 0.0),
                )

                if self._on_viseme:
                    self._on_viseme(openY, form)

                time.sleep(interval)
                elapsed = time.perf_counter() - t0

            if self._on_viseme:
                self._on_viseme(0.0, 0.0)
        except Exception:
            logger.debug("Viseme (lip-sync) thread encountered an error")
            pass
