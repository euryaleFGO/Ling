# -*- coding: utf-8 -*-
"""
音频处理器（Mixin）

从 conversation_manager.py 拆分而来，包含音频设备初始化、
流式打断（Barge-in）监听等方法。

作为 mixin 被 ConversationManager 继承。
"""

from __future__ import annotations

import logging
import time
import threading
from typing import TYPE_CHECKING, Optional

from core.audio_io import AudioInput, AudioOutput, AudioConfig
from core.vad import VADConfig, create_vad
from core.log import log

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AudioHandler:
    """音频处理 Mixin —— 提供音频设备管理、打断监听等能力。

    被 ConversationManager 继承。子类必须提供以下属性：
      config, _asr, _audio_input, _audio_output,
      _interrupt_monitoring, _interrupt_thread, _interrupt_vad,
      _interrupt_audio_input, _interrupt_count, _interrupted_text,
      _on_subtitle
    """

    # ------------------------------------------------------------------
    # 音频设备初始化
    # ------------------------------------------------------------------

    def _init_audio(self):
        """初始化音频设备（chunk_size 从 ASR 获取，VAD 可配置）"""
        self._init_asr()

        chunk_size = 5760  # 默认 360ms
        if self._asr and hasattr(self._asr, "get_chunk_stride"):
            chunk_size = self._asr.get_chunk_stride()
            log.debug(
                f"[AudioIO] chunk_stride: {chunk_size} "
                f"({chunk_size / self.config.sample_rate * 1000:.0f}ms)"
            )

        vad_config = VADConfig.preset(self.config.vad_preset)
        vad_config.backend = self.config.vad_backend
        vad_config.silence_duration = self.config.silence_duration
        vad_config.min_speech_chunks = max(2, vad_config.min_speech_chunks)
        vad_config.hangover_chunks = max(1, vad_config.hangover_chunks)
        vad_config.pre_buffer_chunks = max(2, vad_config.pre_buffer_chunks)

        audio_config = AudioConfig(
            sample_rate=self.config.sample_rate,
            dtype="float32",
            chunk_size=chunk_size,
            vad_config=vad_config,
            vad_backend=self.config.vad_backend,
        )
        self._audio_input = AudioInput(audio_config)
        self._audio_output = AudioOutput()
        log.debug("[对话] 音频设备初始化完成")

    # ------------------------------------------------------------------
    # 流式打断（Barge-in）
    # ------------------------------------------------------------------

    def _start_interrupt_monitoring(self):
        """启动打断监听（后台线程）"""
        if not self.config.enable_barge_in or self._interrupt_monitoring:
            return

        self._interrupt_monitoring = True
        self._interrupt_thread = threading.Thread(
            target=self._interrupt_monitor_loop,
            daemon=True,
            name="InterruptMonitor",
        )
        self._interrupt_thread.start()
        log.debug("[打断] 开始监听")

    def _stop_interrupt_monitoring(self):
        """停止打断监听"""
        if not self._interrupt_monitoring:
            return

        self._interrupt_monitoring = False

        if self._interrupt_audio_input:
            try:
                self._interrupt_audio_input.stop_listening()
            except Exception:
                logger.debug("Failed to stop interrupt audio input listener")
                pass

        if self._interrupt_thread and self._interrupt_thread.is_alive():
            self._interrupt_thread.join(timeout=0.5)

        log.debug("[打断] 停止监听")

    def _interrupt_monitor_loop(self):
        """打断监听循环（后台线程）"""
        try:
            vad_config = VADConfig.preset("aggressive")
            vad_config.silence_threshold = self.config.interrupt_vad_threshold
            self._interrupt_vad = create_vad(vad_config)

            chunk_size = int(self.config.sample_rate * 0.02)  # 20ms
            audio_config = AudioConfig(
                sample_rate=self.config.sample_rate,
                chunk_size=chunk_size,
                dtype="float32",
                vad_config=vad_config,
            )
            self._interrupt_audio_input = AudioInput(audio_config)
            self._interrupt_audio_input.start_listening()

            speech_start_time = None
            speech_frames = 0
            min_speech_frames = int(self.config.interrupt_min_speech_ms / 20)

            while self._interrupt_monitoring:
                try:
                    chunk = self._interrupt_audio_input.read_chunk()
                    if chunk is None or len(chunk) == 0:
                        time.sleep(0.01)
                        continue

                    is_speech = self._interrupt_vad.detect_speech(
                        chunk, self.config.sample_rate,
                    )

                    if is_speech:
                        if speech_start_time is None:
                            speech_start_time = time.time()
                            speech_frames = 1
                        else:
                            speech_frames += 1

                            if speech_frames >= min_speech_frames:
                                log.info(
                                    f"[打断] 检测到语音活动 "
                                    f"(时长: {speech_frames * 20}ms)"
                                )
                                self._interrupt_count += 1

                                if self._audio_output:
                                    self._audio_output.stop()

                                if self.config.interrupt_feedback_enabled:
                                    self._send_subtitle(
                                        "已打断", is_final=True, emotion="neutral",
                                    )

                                log.info(
                                    f"[打断统计] 总打断次数: "
                                    f"{self._interrupt_count}"
                                )

                                self._interrupt_monitoring = False
                                break
                    else:
                        speech_start_time = None
                        speech_frames = 0

                    time.sleep(0.01)

                except Exception as e:
                    log.error(f"[打断] 监听循环错误: {e}")
                    break

        except Exception as e:
            log.error(f"[打断] 监听线程崩溃: {e}")
        finally:
            if self._interrupt_audio_input:
                try:
                    self._interrupt_audio_input.stop_listening()
                except Exception:
                    logger.debug(
                        "Failed to stop interrupt audio input "
                        "in monitor finally block"
                    )
                    pass
