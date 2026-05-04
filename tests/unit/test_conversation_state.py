# -*- coding: utf-8 -*-
"""
ConversationState / ConversationConfig / TurnMetrics 单元测试
"""

import pytest
from core.conversation.state import (
    ConversationState, ConversationConfig, TurnMetrics,
)


class TestConversationState:
    """ConversationState 枚举测试"""

    def test_all_states_exist(self):
        states = [s.value for s in ConversationState]
        assert "idle" in states
        assert "listening" in states
        assert "processing" in states
        assert "speaking" in states
        assert "paused" in states

    def test_state_count(self):
        assert len(ConversationState) == 5

    def test_state_values_are_strings(self):
        for state in ConversationState:
            assert isinstance(state.value, str)


class TestConversationConfig:
    """ConversationConfig 默认值测试"""

    def test_asr_defaults(self):
        config = ConversationConfig()
        assert config.asr_device == "auto"
        assert config.asr_stream_profile == "balanced"

    def test_tts_defaults(self):
        config = ConversationConfig()
        assert config.tts_mode == "remote"
        assert config.tts_remote_url == "http://localhost:5001"
        assert config.tts_spk_id == "玲"

    def test_audio_defaults(self):
        config = ConversationConfig()
        assert config.sample_rate == 16000
        assert config.use_text_input is False

    def test_interrupt_defaults(self):
        config = ConversationConfig()
        assert config.enable_barge_in is True
        assert config.vad_threshold == 0.5

    def test_ser_defaults(self):
        config = ConversationConfig()
        assert config.enable_ser is True
        assert config.ser_device == "auto"

    def test_custom_values(self):
        config = ConversationConfig(
            tts_mode="local",
            tts_spk_id="custom",
            sample_rate=44100,
            enable_barge_in=False,
        )
        assert config.tts_mode == "local"
        assert config.tts_spk_id == "custom"
        assert config.sample_rate == 44100
        assert config.enable_barge_in is False


class TestTurnMetrics:
    """TurnMetrics 性能指标测试"""

    def test_defaults(self):
        metrics = TurnMetrics()
        assert metrics.turn_id == ""
        assert metrics.user_text == ""
        assert metrics.ai_text == ""
        assert metrics.llm_first_token_ms == 0.0
        assert metrics.llm_total_ms == 0.0
        assert metrics.tts_first_chunk_ms == 0.0
        assert metrics.total_latency_ms == 0.0
        assert metrics.interrupted is False

    def test_custom_values(self):
        metrics = TurnMetrics(
            turn_id="turn-001",
            user_text="你好",
            ai_text="你好呀",
            llm_first_token_ms=150.0,
            llm_total_ms=2000.0,
            total_latency_ms=2500.0,
            interrupted=True,
        )
        assert metrics.turn_id == "turn-001"
        assert metrics.user_text == "你好"
        assert metrics.ai_text == "你好呀"
        assert metrics.llm_first_token_ms == 150.0
        assert metrics.interrupted is True
