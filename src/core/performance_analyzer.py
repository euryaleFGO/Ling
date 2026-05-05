# -*- coding: utf-8 -*-
"""
性能分析工具

功能：
1. 识别性能瓶颈
2. 生成优化建议
3. 根据硬件推荐配置参数
4. 生成性能报告
"""

import platform
import statistics
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

from core.log import log


class BottleneckType(Enum):
    """瓶颈类型"""
    ASR = "asr"
    TTS = "tts"
    LLM = "llm"
    SPEAKER_RECOGNITION = "speaker_recognition"
    INTERRUPT = "interrupt"
    OVERALL = "overall"


class Severity(Enum):
    """严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Bottleneck:
    """性能瓶颈"""
    type: BottleneckType
    severity: Severity
    metric: str
    current_value: float
    target_value: float
    description: str
    suggestions: List[str]


@dataclass
class HardwareInfo:
    """硬件信息"""
    cpu_count: int
    has_cuda: bool
    cuda_device_count: int
    total_memory_gb: float
    platform: str


@dataclass
class PerformanceReport:
    """性能报告"""
    bottlenecks: List[Bottleneck]
    hardware_info: HardwareInfo
    recommended_config: Dict
    summary: str


class PerformanceAnalyzer:
    """性能分析器"""
    
    # 性能目标（毫秒）
    TARGETS = {
        "asr_first_chunk": 100,
        "asr_total": 500,
        "tts_first_chunk": 200,
        "tts_total": 1500,
        "llm_first_token": 1000,
        "speaker_recognition": 500,
        "interrupt_response": 200,
        "turn_total": 2000,
    }
    
    def __init__(self):
        self.hardware_info = self._detect_hardware()
    
    def _detect_hardware(self) -> HardwareInfo:
        """检测硬件信息"""
        cpu_count = 1
        has_cuda = False
        cuda_device_count = 0
        total_memory_gb = 0.0
        
        try:
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
        except Exception:
            logger.debug("Failed to detect CPU count", exc_info=True)

        try:
            import torch
            has_cuda = torch.cuda.is_available()
            if has_cuda:
                cuda_device_count = torch.cuda.device_count()
        except Exception:
            logger.debug("Failed to detect CUDA availability", exc_info=True)

        try:
            import psutil
            total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            logger.debug("Failed to detect total memory via psutil", exc_info=True)
        
        return HardwareInfo(
            cpu_count=cpu_count,
            has_cuda=has_cuda,
            cuda_device_count=cuda_device_count,
            total_memory_gb=total_memory_gb,
            platform=platform.system(),
        )
    
    def analyze(self, stats: Dict) -> PerformanceReport:
        """
        分析性能统计数据
        
        Args:
            stats: 性能统计数据（来自 PerformanceMonitor.get_summary()）
        
        Returns:
            PerformanceReport: 性能报告
        """
        bottlenecks = []
        
        # 分析 ASR 性能
        if "asr" in stats and stats["asr"]:
            asr_bottlenecks = self._analyze_asr(stats["asr"])
            bottlenecks.extend(asr_bottlenecks)
        
        # 分析 TTS 性能
        if "tts" in stats and stats["tts"]:
            tts_bottlenecks = self._analyze_tts(stats["tts"])
            bottlenecks.extend(tts_bottlenecks)
        
        # 分析 Turn 性能
        if "turn" in stats and stats["turn"]:
            turn_bottlenecks = self._analyze_turn(stats["turn"])
            bottlenecks.extend(turn_bottlenecks)
        
        # 分析打断性能
        if "interrupt" in stats and stats["interrupt"]:
            interrupt_bottlenecks = self._analyze_interrupt(stats["interrupt"])
            bottlenecks.extend(interrupt_bottlenecks)
        
        # 分析声纹识别性能
        if "speaker_recognition" in stats and stats["speaker_recognition"]:
            sr_bottlenecks = self._analyze_speaker_recognition(stats["speaker_recognition"])
            bottlenecks.extend(sr_bottlenecks)
        
        # 按严重程度排序
        bottlenecks.sort(key=lambda b: ["low", "medium", "high", "critical"].index(b.severity.value), reverse=True)
        
        # 生成推荐配置
        recommended_config = self._generate_recommended_config(bottlenecks)
        
        # 生成总结
        summary = self._generate_summary(bottlenecks, stats)
        
        return PerformanceReport(
            bottlenecks=bottlenecks,
            hardware_info=self.hardware_info,
            recommended_config=recommended_config,
            summary=summary,
        )
    
    def _analyze_asr(self, asr_stats: Dict) -> List[Bottleneck]:
        """分析 ASR 性能"""
        bottlenecks = []
        
        # 首包延迟
        if "first_chunk_latency" in asr_stats:
            avg = asr_stats["first_chunk_latency"].get("avg", 0)
            p95 = asr_stats["first_chunk_latency"].get("p95", 0)
            target = self.TARGETS["asr_first_chunk"]
            
            if p95 > target * 2:
                severity = Severity.CRITICAL
            elif p95 > target * 1.5:
                severity = Severity.HIGH
            elif avg > target:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW
            
            if severity != Severity.LOW:
                suggestions = []
                
                if not self.hardware_info.has_cuda:
                    suggestions.append("使用 CUDA 加速（当前使用 CPU）")
                
                suggestions.extend([
                    "使用 'low_latency' 流式配置档位",
                    "启用模型缓存（asr_enable_model_cache=true）",
                    "减少 chunk_size 参数",
                ])
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.ASR,
                    severity=severity,
                    metric="首包延迟",
                    current_value=p95,
                    target_value=target,
                    description=f"ASR 首包延迟过高（P95: {p95:.1f}ms，目标: <{target}ms）",
                    suggestions=suggestions,
                ))
        
        # RTF
        if "rtf" in asr_stats:
            avg_rtf = asr_stats["rtf"].get("avg", 0)
            
            if avg_rtf > 0.5:
                severity = Severity.HIGH if avg_rtf > 0.8 else Severity.MEDIUM
                
                suggestions = [
                    "使用更快的设备（CUDA）",
                    "减少模型复杂度",
                    "优化 chunk_size 参数",
                ]
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.ASR,
                    severity=severity,
                    metric="RTF",
                    current_value=avg_rtf,
                    target_value=0.3,
                    description=f"ASR RTF 过高（{avg_rtf:.3f}，目标: <0.3）",
                    suggestions=suggestions,
                ))
        
        return bottlenecks
    
    def _analyze_tts(self, tts_stats: Dict) -> List[Bottleneck]:
        """分析 TTS 性能"""
        bottlenecks = []
        
        # 首包延迟
        if "first_chunk_latency" in tts_stats:
            avg = tts_stats["first_chunk_latency"].get("avg", 0)
            p95 = tts_stats["first_chunk_latency"].get("p95", 0)
            target = self.TARGETS["tts_first_chunk"]
            
            if p95 > target * 2:
                severity = Severity.CRITICAL
            elif p95 > target * 1.5:
                severity = Severity.HIGH
            elif avg > target:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW
            
            if severity != Severity.LOW:
                suggestions = [
                    "启用 TTS 缓存（tts_enable_cache=true）",
                    "增加缓存大小（tts_cache_size=200）",
                    "添加常用短语到缓存列表",
                    "启用并行合成（tts_parallel_synthesis=true）",
                ]
                
                if not self.hardware_info.has_cuda:
                    suggestions.insert(0, "使用 CUDA 加速（当前使用 CPU）")
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.TTS,
                    severity=severity,
                    metric="首包延迟",
                    current_value=p95,
                    target_value=target,
                    description=f"TTS 首包延迟过高（P95: {p95:.1f}ms，目标: <{target}ms）",
                    suggestions=suggestions,
                ))
        
        # RTF
        if "rtf" in tts_stats:
            avg_rtf = tts_stats["rtf"].get("avg", 0)
            
            if avg_rtf > 0.6:
                severity = Severity.HIGH if avg_rtf > 1.0 else Severity.MEDIUM
                
                suggestions = [
                    "使用更快的设备（CUDA）",
                    "启用并行合成",
                    "增加 max_workers 参数",
                ]
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.TTS,
                    severity=severity,
                    metric="RTF",
                    current_value=avg_rtf,
                    target_value=0.4,
                    description=f"TTS RTF 过高（{avg_rtf:.3f}，目标: <0.4）",
                    suggestions=suggestions,
                ))
        
        return bottlenecks
    
    def _analyze_turn(self, turn_stats: Dict) -> List[Bottleneck]:
        """分析 Turn 性能"""
        bottlenecks = []
        
        # LLM 首 token 延迟
        if "llm_first_token" in turn_stats:
            avg = turn_stats["llm_first_token"].get("avg", 0)
            p95 = turn_stats["llm_first_token"].get("p95", 0)
            target = self.TARGETS["llm_first_token"]
            
            if p95 > target * 2:
                severity = Severity.HIGH
            elif avg > target:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW
            
            if severity != Severity.LOW:
                suggestions = [
                    "使用更快的 LLM 模型",
                    "优化 prompt 长度",
                    "使用本地 LLM（如果当前使用远程）",
                    "增加 LLM 并发数",
                ]
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.LLM,
                    severity=severity,
                    metric="首 token 延迟",
                    current_value=p95,
                    target_value=target,
                    description=f"LLM 首 token 延迟过高（P95: {p95:.1f}ms，目标: <{target}ms）",
                    suggestions=suggestions,
                ))
        
        # 总延迟
        if "total_latency" in turn_stats:
            avg = turn_stats["total_latency"].get("avg", 0)
            p95 = turn_stats["total_latency"].get("p95", 0)
            target = self.TARGETS["turn_total"]
            
            if p95 > target * 2:
                severity = Severity.CRITICAL
            elif p95 > target * 1.5:
                severity = Severity.HIGH
            elif avg > target:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW
            
            if severity != Severity.LOW:
                suggestions = [
                    "优化各组件性能（ASR、LLM、TTS）",
                    "启用异步处理",
                    "使用更快的硬件",
                ]
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.OVERALL,
                    severity=severity,
                    metric="总延迟",
                    current_value=p95,
                    target_value=target,
                    description=f"对话总延迟过高（P95: {p95:.1f}ms，目标: <{target}ms）",
                    suggestions=suggestions,
                ))
        
        return bottlenecks
    
    def _analyze_interrupt(self, interrupt_stats: Dict) -> List[Bottleneck]:
        """分析打断性能"""
        bottlenecks = []
        
        if "response_time" in interrupt_stats:
            avg = interrupt_stats["response_time"].get("avg", 0)
            p95 = interrupt_stats["response_time"].get("p95", 0)
            target = self.TARGETS["interrupt_response"]
            
            if p95 > target * 1.5:
                severity = Severity.HIGH
            elif avg > target:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW
            
            if severity != Severity.LOW:
                suggestions = [
                    "降低 VAD 阈值（interrupt_vad_threshold）",
                    "减少最小语音时长（interrupt_min_speech_ms）",
                    "优化 TTS 停止逻辑",
                ]
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.INTERRUPT,
                    severity=severity,
                    metric="响应时间",
                    current_value=p95,
                    target_value=target,
                    description=f"打断响应时间过长（P95: {p95:.1f}ms，目标: <{target}ms）",
                    suggestions=suggestions,
                ))
        
        return bottlenecks
    
    def _analyze_speaker_recognition(self, sr_stats: Dict) -> List[Bottleneck]:
        """分析声纹识别性能"""
        bottlenecks = []
        
        if "latency" in sr_stats:
            avg = sr_stats["latency"].get("avg", 0)
            p95 = sr_stats["latency"].get("p95", 0)
            target = self.TARGETS["speaker_recognition"]
            
            if p95 > target * 2:
                severity = Severity.HIGH
            elif avg > target:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW
            
            if severity != Severity.LOW:
                suggestions = [
                    "启用异步识别（async_recognition=true）",
                    "启用声纹缓存（enable_cache=true）",
                    "增加缓存大小（cache_size=200）",
                    "使用向量化计算加速",
                ]
                
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.SPEAKER_RECOGNITION,
                    severity=severity,
                    metric="识别延迟",
                    current_value=p95,
                    target_value=target,
                    description=f"声纹识别延迟过高（P95: {p95:.1f}ms，目标: <{target}ms）",
                    suggestions=suggestions,
                ))
        
        return bottlenecks
    
    def _generate_recommended_config(self, bottlenecks: List[Bottleneck]) -> Dict:
        """生成推荐配置"""
        config = {}
        
        # 根据硬件推荐基础配置
        if self.hardware_info.has_cuda:
            config["asr"] = {
                "device": "cuda:0",
                "stream_profile": "low_latency",
                "enable_model_cache": True,
            }
            config["tts"] = {
                "enable_cache": True,
                "cache_size": 200,
                "parallel_synthesis": True,
                "max_workers": 3,
            }
        else:
            config["asr"] = {
                "device": "cpu",
                "stream_profile": "balanced",
                "enable_model_cache": True,
            }
            config["tts"] = {
                "enable_cache": True,
                "cache_size": 100,
                "parallel_synthesis": True,
                "max_workers": 2,
            }
        
        # 根据瓶颈调整配置
        for bottleneck in bottlenecks:
            if bottleneck.type == BottleneckType.ASR:
                if bottleneck.severity in [Severity.HIGH, Severity.CRITICAL]:
                    config["asr"]["stream_profile"] = "low_latency"
            
            elif bottleneck.type == BottleneckType.TTS:
                if bottleneck.severity in [Severity.HIGH, Severity.CRITICAL]:
                    config["tts"]["cache_size"] = 200
                    if self.hardware_info.cpu_count >= 4:
                        config["tts"]["max_workers"] = 3
            
            elif bottleneck.type == BottleneckType.INTERRUPT:
                if "interrupt" not in config:
                    config["interrupt"] = {}
                config["interrupt"]["vad_threshold"] = 0.4
                config["interrupt"]["min_speech_ms"] = 250
            
            elif bottleneck.type == BottleneckType.SPEAKER_RECOGNITION:
                if "speaker_recognition" not in config:
                    config["speaker_recognition"] = {}
                config["speaker_recognition"]["async_recognition"] = True
                config["speaker_recognition"]["enable_cache"] = True
                config["speaker_recognition"]["cache_size"] = 150
        
        return config
    
    def _generate_summary(self, bottlenecks: List[Bottleneck], stats: Dict) -> str:
        """生成性能总结"""
        lines = []
        
        # 硬件信息
        lines.append("硬件信息:")
        lines.append(f"  - CPU 核心数: {self.hardware_info.cpu_count}")
        lines.append(f"  - CUDA 可用: {'是' if self.hardware_info.has_cuda else '否'}")
        if self.hardware_info.has_cuda:
            lines.append(f"  - GPU 数量: {self.hardware_info.cuda_device_count}")
        if self.hardware_info.total_memory_gb > 0:
            lines.append(f"  - 内存: {self.hardware_info.total_memory_gb:.1f} GB")
        lines.append(f"  - 平台: {self.hardware_info.platform}")
        lines.append("")
        
        # 性能概览
        lines.append("性能概览:")
        if "overall" in stats:
            overall = stats["overall"]
            lines.append(f"  - 总对话轮次: {overall.get('total_turns', 0)}")
            lines.append(f"  - 总打断次数: {overall.get('total_interrupts', 0)}")
        lines.append("")
        
        # 瓶颈分析
        if bottlenecks:
            critical = [b for b in bottlenecks if b.severity == Severity.CRITICAL]
            high = [b for b in bottlenecks if b.severity == Severity.HIGH]
            medium = [b for b in bottlenecks if b.severity == Severity.MEDIUM]
            
            lines.append("瓶颈分析:")
            if critical:
                lines.append(f"  - 严重瓶颈: {len(critical)} 个")
            if high:
                lines.append(f"  - 高优先级瓶颈: {len(high)} 个")
            if medium:
                lines.append(f"  - 中优先级瓶颈: {len(medium)} 个")
            lines.append("")
            
            # 列出前 3 个最严重的瓶颈
            lines.append("主要瓶颈:")
            for i, bottleneck in enumerate(bottlenecks[:3], 1):
                lines.append(f"  {i}. [{bottleneck.severity.value.upper()}] {bottleneck.description}")
        else:
            lines.append("✅ 未发现明显性能瓶颈")
            lines.append("")
        
        return "\n".join(lines)
    
    def print_report(self, report: PerformanceReport):
        """打印性能报告"""
        logger.info("=" * 70)
        logger.info("性能分析报告")
        logger.info("=" * 70)
        logger.info("")

        # 总结
        logger.info(report.summary)

        # 详细瓶颈
        if report.bottlenecks:
            logger.info("=" * 70)
            logger.info("详细瓶颈分析")
            logger.info("=" * 70)
            logger.info("")

            for i, bottleneck in enumerate(report.bottlenecks, 1):
                severity_icon = {
                    Severity.LOW: "ℹ️",
                    Severity.MEDIUM: "⚠️",
                    Severity.HIGH: "🔴",
                    Severity.CRITICAL: "🚨",
                }

                logger.info("%d. %s [%s] %s", i, severity_icon[bottleneck.severity], bottleneck.severity.value.upper(), bottleneck.type.value.upper())
                logger.info("   指标: %s", bottleneck.metric)
                logger.info("   当前值: %.1fms", bottleneck.current_value)
                logger.info("   目标值: %.1fms", bottleneck.target_value)
                logger.info("   描述: %s", bottleneck.description)
                logger.info("   优化建议:")
                for suggestion in bottleneck.suggestions:
                    logger.info("     - %s", suggestion)
                logger.info("")

        # 推荐配置
        if report.recommended_config:
            logger.info("=" * 70)
            logger.info("推荐配置")
            logger.info("=" * 70)
            logger.info("")

            import json
            logger.info(json.dumps(report.recommended_config, indent=2, ensure_ascii=False))
            logger.info("")

        logger.info("=" * 70)
    
    def export_report(self, report: PerformanceReport, output_path: str):
        """导出性能报告到文件"""
        import json
        from datetime import datetime
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "hardware_info": {
                "cpu_count": report.hardware_info.cpu_count,
                "has_cuda": report.hardware_info.has_cuda,
                "cuda_device_count": report.hardware_info.cuda_device_count,
                "total_memory_gb": report.hardware_info.total_memory_gb,
                "platform": report.hardware_info.platform,
            },
            "bottlenecks": [
                {
                    "type": b.type.value,
                    "severity": b.severity.value,
                    "metric": b.metric,
                    "current_value": b.current_value,
                    "target_value": b.target_value,
                    "description": b.description,
                    "suggestions": b.suggestions,
                }
                for b in report.bottlenecks
            ],
            "recommended_config": report.recommended_config,
            "summary": report.summary,
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        log.info(f"性能报告已导出到: {output_path}")
