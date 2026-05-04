# -*- coding: utf-8 -*-
"""
ConfigManager 单元测试
"""

import json
import pytest
import tempfile
from pathlib import Path

from core.config_manager import (
    SystemConfig, ConfigManager, LLMConfig, ASRConfig, TTSConfig,
    InterruptConfig, AudioConfig, _parse_sub_config,
)


class TestSystemConfigDefaults:
    """SystemConfig 默认值测试"""

    def test_version(self):
        config = SystemConfig()
        assert config.version == "2.0.0"

    def test_llm_defaults(self):
        config = SystemConfig()
        assert config.llm.temperature == 0.7
        assert config.llm.max_tokens == 2048
        assert config.llm.timeout == 120

    def test_tts_defaults(self):
        config = SystemConfig()
        assert config.tts.spk_id == "玲"
        assert config.tts.enable_cache is True
        assert config.tts.cache_size == 100
        assert config.tts.max_workers == 2

    def test_asr_defaults(self):
        config = SystemConfig()
        assert config.asr.provider == "funasr"
        assert config.asr.stream_profile == "balanced"

    def test_interrupt_defaults(self):
        config = SystemConfig()
        assert config.interrupt.enable_barge_in is True
        assert config.interrupt.vad_threshold == 0.5
        assert config.interrupt.context_mode == "reset"

    def test_audio_defaults(self):
        config = SystemConfig()
        assert config.audio.sample_rate == 16000
        assert config.audio.vad_backend == "rms"
        assert config.audio.vad_preset == "balanced"


class TestParseSubConfig:
    """_parse_sub_config 辅助函数测试"""

    def test_parse_known_fields(self):
        data = {"temperature": 0.9, "max_tokens": 4096}
        config = _parse_sub_config(data, LLMConfig)
        assert config.temperature == 0.9
        assert config.max_tokens == 4096

    def test_parse_ignores_unknown_fields(self):
        data = {"temperature": 0.5, "unknown_field": "value"}
        config = _parse_sub_config(data, LLMConfig)
        assert config.temperature == 0.5

    def test_parse_empty_dict(self):
        config = _parse_sub_config({}, LLMConfig)
        assert config.temperature == 0.7  # default


class TestConfigManager:
    """ConfigManager 功能测试"""

    def test_load_nonexistent_file(self, tmp_path):
        """加载不存在的文件应返回默认配置"""
        cm = ConfigManager(str(tmp_path / "nonexistent.json"))
        config = cm.load()
        assert config.version == "2.0.0"

    def test_load_invalid_json(self, tmp_path):
        """加载格式错误的 JSON 应返回默认配置"""
        config_file = tmp_path / "bad.json"
        config_file.write_text("not json {{{", encoding="utf-8")
        cm = ConfigManager(str(config_file))
        config = cm.load()
        assert config.version == "2.0.0"

    def test_load_valid_config(self, tmp_path):
        """加载有效配置文件"""
        config_file = tmp_path / "settings.json"
        data = {
            "version": "3.0.0",
            "llm": {"temperature": 0.9, "model": "test-model"},
            "tts": {"spk_id": "test_speaker"},
        }
        config_file.write_text(json.dumps(data), encoding="utf-8")
        cm = ConfigManager(str(config_file))
        config = cm.load()
        assert config.version == "3.0.0"
        assert config.llm.temperature == 0.9
        assert config.llm.model == "test-model"
        assert config.tts.spk_id == "test_speaker"

    def test_save_and_reload(self, tmp_path):
        """保存后重新加载应保持一致"""
        config_file = tmp_path / "settings.json"
        cm = ConfigManager(str(config_file))

        # 修改配置
        cm.config.llm.temperature = 0.3
        cm.config.tts.spk_id = "新说话人"
        cm.save()

        # 重新加载
        cm2 = ConfigManager(str(config_file))
        config = cm2.load()
        assert config.llm.temperature == 0.3
        assert config.tts.spk_id == "新说话人"

    def test_check_for_updates(self, tmp_path):
        """检测配置文件更新"""
        config_file = tmp_path / "settings.json"
        config_file.write_text('{"version": "1.0"}', encoding="utf-8")
        cm = ConfigManager(str(config_file))
        cm.load()

        assert cm.check_for_updates() is False

        # 修改文件
        import time
        time.sleep(0.1)
        config_file.write_text('{"version": "2.0"}', encoding="utf-8")
        assert cm.check_for_updates() is True

    def test_load_ignores_unknown_sections(self, tmp_path):
        """加载时忽略未知配置段"""
        config_file = tmp_path / "settings.json"
        data = {
            "version": "2.0.0",
            "unknown_section": {"key": "value"},
            "llm": {"temperature": 0.8},
        }
        config_file.write_text(json.dumps(data), encoding="utf-8")
        cm = ConfigManager(str(config_file))
        config = cm.load()
        assert config.llm.temperature == 0.8
