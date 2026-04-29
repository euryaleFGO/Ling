# -*- coding: utf-8 -*-
"""
测试 DiarizationEngine 的错误处理和降级策略
验证需求 8.1-8.6
"""

import numpy as np
import pytest
from unittest.mock import Mock, MagicMock
import time

from src.core.diarization_engine import DiarizationEngine, DiarizationResult


class TestDiarizationErrorHandling:
    """测试错误处理和降级策略（需求 8.1-8.6）"""
    
    def setup_method(self):
        """设置测试环境"""
        self.sv_engine = Mock()
        self.voiceprint_db = Mock()
        
        # 创建测试音频（1秒，16kHz）
        self.test_audio = np.random.randn(16000).astype(np.float32)
        self.sample_rate = 16000
    
    def test_consecutive_failure_counter(self):
        """需求 8.1: 测试连续失败计数器"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db,
            max_failures=3
        )
        
        # 模拟声纹提取失败
        self.sv_engine.embed.side_effect = Exception("Embedding failed")
        
        # 第一次失败
        result1 = engine.identify(self.test_audio, self.sample_rate)
        assert engine._consecutive_failures == 1
        assert result1.speaker_id == "unknown"
        assert "error" in result1.reason
        
        # 第二次失败
        result2 = engine.identify(self.test_audio, self.sample_rate)
        assert engine._consecutive_failures == 2
        
        # 第三次失败 - 应该触发临时禁用
        result3 = engine.identify(self.test_audio, self.sample_rate)
        assert engine._consecutive_failures == 3
        assert engine._temporarily_disabled is True
    
    def test_fallback_to_last_speaker_on_error(self):
        """需求 8.2: 测试降级到上一次识别结果"""
        # 重新创建 mocks 以避免缓存问题
        sv_engine = Mock()
        voiceprint_db = Mock()
        
        engine = DiarizationEngine(
            sv_engine=sv_engine,
            voiceprint_db=voiceprint_db
        )
        
        # 第一次成功识别
        embedding1 = np.random.randn(192).astype(np.float32)
        sv_engine.embed.return_value = embedding1
        voiceprint_db.find_best_match.return_value = ("speaker_001", 0.85)
        
        result1 = engine.identify(self.test_audio, self.sample_rate)
        assert result1.speaker_id == "speaker_001"
        assert engine._last_speaker_id == "speaker_001"
        
        # 清除缓存以确保第二次调用会触发 embed
        engine._embedding_cache.clear()
        
        # 第二次失败 - 应该返回上一次的 speaker_id
        sv_engine.embed.side_effect = Exception("Embedding failed")
        
        result2 = engine.identify(self.test_audio, self.sample_rate)
        assert result2.speaker_id == "speaker_001"  # 使用上一次的结果
        assert "error" in result2.reason
    
    def test_database_access_failure(self):
        """需求 8.3: 测试数据库访问失败"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db
        )
        
        # 声纹提取成功，但数据库访问失败
        self.sv_engine.embed.return_value = np.random.randn(192).astype(np.float32)
        self.voiceprint_db.find_best_match.side_effect = Exception("Database connection failed")
        
        result = engine.identify(self.test_audio, self.sample_rate)
        
        # 应该返回 unknown 并记录错误
        assert result.speaker_id == "unknown"
        assert "error" in result.reason
        assert engine._consecutive_failures == 1
    
    def test_timeout_control(self):
        """需求 8.4: 测试识别超时控制（默认 500ms）"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db,
            timeout_ms=100  # 设置较短的超时时间用于测试
        )
        
        # 模拟慢速识别（超过超时时间）
        def slow_embed(audio, sample_rate):
            time.sleep(0.2)  # 200ms，超过 100ms 超时
            return np.random.randn(192).astype(np.float32)
        
        self.sv_engine.embed.side_effect = slow_embed
        
        result = engine.identify(self.test_audio, self.sample_rate)
        
        # 应该超时并返回上一次结果
        assert "timeout" in result.reason
        assert engine._consecutive_failures == 1
    
    def test_error_logging(self):
        """需求 8.5: 测试错误日志记录"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db
        )
        
        # 模拟各种错误
        self.sv_engine.embed.side_effect = ValueError("Invalid audio format")
        
        result = engine.identify(self.test_audio, self.sample_rate)
        
        # 验证错误被记录在 reason 中
        assert "error:ValueError" in result.reason
        assert result.speaker_id == "unknown"
    
    def test_temporary_disable_after_max_failures(self):
        """需求 8.6: 测试连续失败后临时禁用"""
        notification_received = []
        
        def notification_callback(msg):
            notification_received.append(msg)
        
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db,
            max_failures=3
        )
        engine.set_notification_callback(notification_callback)
        
        # 模拟连续失败
        self.sv_engine.embed.side_effect = Exception("Persistent failure")
        
        # 前 3 次失败
        for i in range(3):
            result = engine.identify(self.test_audio, self.sample_rate)
            assert engine._consecutive_failures == i + 1
        
        # 验证已临时禁用
        assert engine._temporarily_disabled is True
        assert len(notification_received) == 1
        assert "临时禁用" in notification_received[0]
        
        # 第 4 次调用应该直接返回，不再尝试识别
        result4 = engine.identify(self.test_audio, self.sample_rate)
        assert result4.reason == "temporarily_disabled"
        assert engine._consecutive_failures == 3  # 不再增加
    
    def test_reset_failure_counter(self):
        """测试手动重置失败计数器"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db,
            max_failures=3
        )
        
        # 模拟失败
        self.sv_engine.embed.side_effect = Exception("Test failure")
        
        for _ in range(3):
            engine.identify(self.test_audio, self.sample_rate)
        
        assert engine._temporarily_disabled is True
        assert engine._consecutive_failures == 3
        
        # 重置
        engine.reset_failure_counter()
        
        assert engine._temporarily_disabled is False
        assert engine._consecutive_failures == 0
    
    def test_short_audio_skips_identification(self):
        """测试音频过短时跳过识别（需求 2.5）"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db,
            min_audio_sec=0.8
        )
        
        # 创建短音频（0.5秒）
        short_audio = np.random.randn(8000).astype(np.float32)
        
        result = engine.identify(short_audio, self.sample_rate)
        
        # 应该跳过识别
        assert "audio_too_short" in result.reason
        assert result.speaker_id == "unknown"
        # 不应该增加失败计数
        assert engine._consecutive_failures == 0
    
    def test_successful_identification_resets_counter(self):
        """测试成功识别后重置失败计数器"""
        engine = DiarizationEngine(
            sv_engine=self.sv_engine,
            voiceprint_db=self.voiceprint_db
        )
        
        # 先失败一次
        self.sv_engine.embed.side_effect = Exception("Temporary failure")
        engine.identify(self.test_audio, self.sample_rate)
        assert engine._consecutive_failures == 1
        
        # 然后成功
        self.sv_engine.embed.side_effect = None
        self.sv_engine.embed.return_value = np.random.randn(192).astype(np.float32)
        self.voiceprint_db.find_best_match.return_value = ("speaker_001", 0.85)
        
        result = engine.identify(self.test_audio, self.sample_rate)
        
        # 失败计数应该被重置
        assert result.speaker_id == "speaker_001"
        assert engine._consecutive_failures == 0
