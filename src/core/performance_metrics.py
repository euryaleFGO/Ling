# -*- coding: utf-8 -*-
"""
性能监控模块

用于记录和分析对话系统各组件的性能指标
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List
from collections import deque
import statistics


@dataclass
class ASRMetrics:
    """ASR 性能指标"""
    first_chunk_latency_ms: float = 0.0  # 首包延迟
    total_latency_ms: float = 0.0  # 总延迟
    rtf: float = 0.0  # Real-Time Factor (处理时间/音频时长)
    audio_duration_ms: float = 0.0  # 音频时长
    text_length: int = 0  # 识别文本长度
    timestamp: float = field(default_factory=time.time)


@dataclass
class TTSMetrics:
    """TTS 性能指标"""
    first_chunk_latency_ms: float = 0.0  # 首包延迟
    total_latency_ms: float = 0.0  # 总延迟
    rtf: float = 0.0  # Real-Time Factor
    audio_duration_ms: float = 0.0  # 音频时长
    text_length: int = 0  # 合成文本长度
    chunk_count: int = 0  # 音频块数量
    timestamp: float = field(default_factory=time.time)


@dataclass
class SpeakerRecognitionMetrics:
    """声纹识别性能指标"""
    latency_ms: float = 0.0  # 识别延迟
    cache_hit: bool = False  # 是否命中缓存
    audio_duration_ms: float = 0.0  # 音频时长
    confidence: float = 0.0  # 识别置信度
    timestamp: float = field(default_factory=time.time)


@dataclass
class InterruptMetrics:
    """打断性能指标"""
    response_time_ms: float = 0.0  # 打断响应时间
    detection_latency_ms: float = 0.0  # 检测延迟
    stop_latency_ms: float = 0.0  # 停止延迟
    interrupted_at_ms: float = 0.0  # 打断时间点
    total_duration_ms: float = 0.0  # 总播放时长
    timestamp: float = field(default_factory=time.time)


@dataclass
class TurnMetrics:
    """单次对话 Turn 性能指标"""
    turn_id: str = ""
    user_text: str = ""
    ai_text: str = ""
    
    # 各阶段延迟
    asr_latency_ms: float = 0.0
    llm_first_token_ms: float = 0.0
    llm_total_ms: float = 0.0
    tts_first_chunk_ms: float = 0.0
    tts_total_ms: float = 0.0
    
    # 总延迟
    total_latency_ms: float = 0.0
    
    # 是否被打断
    interrupted: bool = False
    
    timestamp: float = field(default_factory=time.time)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 100):
        """
        初始化性能监控器
        
        Args:
            max_history: 保留的历史记录数量
        """
        self.max_history = max_history
        
        # 各组件的性能历史
        self.asr_history: deque[ASRMetrics] = deque(maxlen=max_history)
        self.tts_history: deque[TTSMetrics] = deque(maxlen=max_history)
        self.speaker_history: deque[SpeakerRecognitionMetrics] = deque(maxlen=max_history)
        self.interrupt_history: deque[InterruptMetrics] = deque(maxlen=max_history)
        self.turn_history: deque[TurnMetrics] = deque(maxlen=max_history)
        
        # 统计计数
        self.total_turns: int = 0
        self.total_interrupts: int = 0
        self.total_asr_calls: int = 0
        self.total_tts_calls: int = 0
        self.total_speaker_calls: int = 0
    
    # ============================================================
    #  记录方法
    # ============================================================
    
    def record_asr(self, metrics: ASRMetrics):
        """记录 ASR 性能"""
        self.asr_history.append(metrics)
        self.total_asr_calls += 1
    
    def record_tts(self, metrics: TTSMetrics):
        """记录 TTS 性能"""
        self.tts_history.append(metrics)
        self.total_tts_calls += 1
    
    def record_speaker(self, metrics: SpeakerRecognitionMetrics):
        """记录声纹识别性能"""
        self.speaker_history.append(metrics)
        self.total_speaker_calls += 1
    
    def record_interrupt(self, metrics: InterruptMetrics):
        """记录打断性能"""
        self.interrupt_history.append(metrics)
        self.total_interrupts += 1
    
    def record_turn(self, metrics: TurnMetrics):
        """记录 Turn 性能"""
        self.turn_history.append(metrics)
        self.total_turns += 1
    
    # ============================================================
    #  统计方法
    # ============================================================
    
    def get_asr_stats(self) -> dict:
        """获取 ASR 统计信息"""
        if not self.asr_history:
            return {}
        
        first_chunk_latencies = [m.first_chunk_latency_ms for m in self.asr_history]
        total_latencies = [m.total_latency_ms for m in self.asr_history]
        rtfs = [m.rtf for m in self.asr_history]
        
        return {
            "count": len(self.asr_history),
            "first_chunk_latency": {
                "avg": statistics.mean(first_chunk_latencies),
                "min": min(first_chunk_latencies),
                "max": max(first_chunk_latencies),
                "p50": statistics.median(first_chunk_latencies),
                "p95": self._percentile(first_chunk_latencies, 0.95),
            },
            "total_latency": {
                "avg": statistics.mean(total_latencies),
                "min": min(total_latencies),
                "max": max(total_latencies),
                "p50": statistics.median(total_latencies),
                "p95": self._percentile(total_latencies, 0.95),
            },
            "rtf": {
                "avg": statistics.mean(rtfs),
                "min": min(rtfs),
                "max": max(rtfs),
            },
        }
    
    def get_tts_stats(self) -> dict:
        """获取 TTS 统计信息"""
        if not self.tts_history:
            return {}
        
        first_chunk_latencies = [m.first_chunk_latency_ms for m in self.tts_history]
        total_latencies = [m.total_latency_ms for m in self.tts_history]
        rtfs = [m.rtf for m in self.tts_history]
        
        return {
            "count": len(self.tts_history),
            "first_chunk_latency": {
                "avg": statistics.mean(first_chunk_latencies),
                "min": min(first_chunk_latencies),
                "max": max(first_chunk_latencies),
                "p50": statistics.median(first_chunk_latencies),
                "p95": self._percentile(first_chunk_latencies, 0.95),
            },
            "total_latency": {
                "avg": statistics.mean(total_latencies),
                "min": min(total_latencies),
                "max": max(total_latencies),
                "p50": statistics.median(total_latencies),
                "p95": self._percentile(total_latencies, 0.95),
            },
            "rtf": {
                "avg": statistics.mean(rtfs),
                "min": min(rtfs),
                "max": max(rtfs),
            },
        }
    
    def get_speaker_stats(self) -> dict:
        """获取声纹识别统计信息"""
        if not self.speaker_history:
            return {}
        
        latencies = [m.latency_ms for m in self.speaker_history]
        cache_hits = sum(1 for m in self.speaker_history if m.cache_hit)
        
        return {
            "count": len(self.speaker_history),
            "latency": {
                "avg": statistics.mean(latencies),
                "min": min(latencies),
                "max": max(latencies),
                "p50": statistics.median(latencies),
                "p95": self._percentile(latencies, 0.95),
            },
            "cache_hit_rate": cache_hits / len(self.speaker_history) if self.speaker_history else 0.0,
        }
    
    def get_interrupt_stats(self) -> dict:
        """获取打断统计信息"""
        if not self.interrupt_history:
            return {}
        
        response_times = [m.response_time_ms for m in self.interrupt_history]
        detection_latencies = [m.detection_latency_ms for m in self.interrupt_history]
        
        return {
            "count": len(self.interrupt_history),
            "response_time": {
                "avg": statistics.mean(response_times),
                "min": min(response_times),
                "max": max(response_times),
                "p50": statistics.median(response_times),
                "p95": self._percentile(response_times, 0.95),
            },
            "detection_latency": {
                "avg": statistics.mean(detection_latencies),
                "min": min(detection_latencies),
                "max": max(detection_latencies),
            },
        }
    
    def get_turn_stats(self) -> dict:
        """获取 Turn 统计信息"""
        if not self.turn_history:
            return {}
        
        total_latencies = [m.total_latency_ms for m in self.turn_history]
        asr_latencies = [m.asr_latency_ms for m in self.turn_history if m.asr_latency_ms > 0]
        llm_first_tokens = [m.llm_first_token_ms for m in self.turn_history if m.llm_first_token_ms > 0]
        tts_first_chunks = [m.tts_first_chunk_ms for m in self.turn_history if m.tts_first_chunk_ms > 0]
        interrupted_count = sum(1 for m in self.turn_history if m.interrupted)
        
        return {
            "count": len(self.turn_history),
            "total_latency": {
                "avg": statistics.mean(total_latencies),
                "min": min(total_latencies),
                "max": max(total_latencies),
                "p50": statistics.median(total_latencies),
                "p95": self._percentile(total_latencies, 0.95),
            },
            "asr_latency": {
                "avg": statistics.mean(asr_latencies) if asr_latencies else 0.0,
                "p95": self._percentile(asr_latencies, 0.95) if asr_latencies else 0.0,
            },
            "llm_first_token": {
                "avg": statistics.mean(llm_first_tokens) if llm_first_tokens else 0.0,
                "p95": self._percentile(llm_first_tokens, 0.95) if llm_first_tokens else 0.0,
            },
            "tts_first_chunk": {
                "avg": statistics.mean(tts_first_chunks) if tts_first_chunks else 0.0,
                "p95": self._percentile(tts_first_chunks, 0.95) if tts_first_chunks else 0.0,
            },
            "interrupt_rate": interrupted_count / len(self.turn_history) if self.turn_history else 0.0,
        }
    
    def get_summary(self) -> dict:
        """获取性能摘要"""
        return {
            "total_turns": self.total_turns,
            "total_interrupts": self.total_interrupts,
            "total_asr_calls": self.total_asr_calls,
            "total_tts_calls": self.total_tts_calls,
            "total_speaker_calls": self.total_speaker_calls,
            "asr": self.get_asr_stats(),
            "tts": self.get_tts_stats(),
            "speaker": self.get_speaker_stats(),
            "interrupt": self.get_interrupt_stats(),
            "turn": self.get_turn_stats(),
        }
    
    def print_summary(self):
        """打印性能摘要"""
        summary = self.get_summary()
        
        print("\n" + "=" * 60)
        print("性能监控摘要")
        print("=" * 60)
        
        print(f"\n总体统计:")
        print(f"  - 总对话轮次: {summary['total_turns']}")
        print(f"  - 总打断次数: {summary['total_interrupts']}")
        print(f"  - ASR 调用: {summary['total_asr_calls']}")
        print(f"  - TTS 调用: {summary['total_tts_calls']}")
        print(f"  - 声纹识别: {summary['total_speaker_calls']}")
        
        if summary.get('asr'):
            asr = summary['asr']
            print(f"\nASR 性能:")
            print(f"  - 首包延迟: {asr['first_chunk_latency']['avg']:.1f}ms (P95: {asr['first_chunk_latency']['p95']:.1f}ms)")
            print(f"  - 总延迟: {asr['total_latency']['avg']:.1f}ms (P95: {asr['total_latency']['p95']:.1f}ms)")
            print(f"  - RTF: {asr['rtf']['avg']:.3f}")
        
        if summary.get('tts'):
            tts = summary['tts']
            print(f"\nTTS 性能:")
            print(f"  - 首包延迟: {tts['first_chunk_latency']['avg']:.1f}ms (P95: {tts['first_chunk_latency']['p95']:.1f}ms)")
            print(f"  - 总延迟: {tts['total_latency']['avg']:.1f}ms (P95: {tts['total_latency']['p95']:.1f}ms)")
            print(f"  - RTF: {tts['rtf']['avg']:.3f}")
        
        if summary.get('speaker'):
            speaker = summary['speaker']
            print(f"\n声纹识别性能:")
            print(f"  - 延迟: {speaker['latency']['avg']:.1f}ms (P95: {speaker['latency']['p95']:.1f}ms)")
            print(f"  - 缓存命中率: {speaker['cache_hit_rate']*100:.1f}%")
        
        if summary.get('interrupt'):
            interrupt = summary['interrupt']
            print(f"\n打断性能:")
            print(f"  - 响应时间: {interrupt['response_time']['avg']:.1f}ms (P95: {interrupt['response_time']['p95']:.1f}ms)")
            print(f"  - 检测延迟: {interrupt['detection_latency']['avg']:.1f}ms")
        
        if summary.get('turn'):
            turn = summary['turn']
            print(f"\nTurn 性能:")
            print(f"  - 总延迟: {turn['total_latency']['avg']:.1f}ms (P95: {turn['total_latency']['p95']:.1f}ms)")
            print(f"  - ASR 延迟: {turn['asr_latency']['avg']:.1f}ms")
            print(f"  - LLM 首 token: {turn['llm_first_token']['avg']:.1f}ms")
            print(f"  - TTS 首包: {turn['tts_first_chunk']['avg']:.1f}ms")
            print(f"  - 打断率: {turn['interrupt_rate']*100:.1f}%")
        
        print("\n" + "=" * 60)
    
    @staticmethod
    def _percentile(data: List[float], p: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * p
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_data):
            return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
        return sorted_data[f]
    
    def export_to_dict(self) -> dict:
        """导出为字典（用于 JSON 序列化）"""
        return self.get_summary()
    
    def reset(self):
        """重置所有统计"""
        self.asr_history.clear()
        self.tts_history.clear()
        self.speaker_history.clear()
        self.interrupt_history.clear()
        self.turn_history.clear()
        
        self.total_turns = 0
        self.total_interrupts = 0
        self.total_asr_calls = 0
        self.total_tts_calls = 0
        self.total_speaker_calls = 0


# 全局性能监控器实例
_global_monitor: Optional[PerformanceMonitor] = None


def get_global_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


def reset_global_monitor():
    """重置全局性能监控器"""
    global _global_monitor
    _global_monitor = None
