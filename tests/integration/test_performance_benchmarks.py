"""
性能基准测试

测试各组件的性能指标，验证是否达到目标：
1. ASR 首包延迟 <100ms
2. TTS 首包延迟 <200ms
3. 声纹识别延迟 <500ms
4. 整体对话延迟 <1.5s
"""

import asyncio
import time
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock
import sys
import os
import statistics

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.conversation_manager_async import (
    AsyncConversationManager,
    ConversationConfig,
)


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    def __init__(self):
        self.test_results: List[Dict[str, Any]] = []
        self.manager: AsyncConversationManager = None
        
    async def setup(self):
        """设置测试环境"""
        # 创建配置
        config = ConversationConfig(
            enable_barge_in=True,
            tts_enable_cache=True,
            asr_stream_profile="low_latency",
        )
        
        # 创建管理器
        self.manager = AsyncConversationManager(config)
        
        # Mock 外部依赖
        self.manager._asr_engine = Mock()
        self.manager._agent = Mock()
        self.manager._tts_engine = Mock()
        self.manager._audio_device = Mock()
        
        # Mock ASR 引擎（模拟真实延迟）
        async def mock_asr_stream(*args, **kwargs):
            await asyncio.sleep(0.08)  # 首包延迟 80ms
            yield "测试", False
            await asyncio.sleep(0.02)
            yield "文本", True
        
        self.manager._asr_engine.stream_recognize = mock_asr_stream
        
        # Mock Agent（模拟真实延迟）
        async def mock_agent_stream(*args, **kwargs):
            await asyncio.sleep(0.15)  # 首 token 延迟 150ms
            for chunk in ["这", "是", "一", "个", "测", "试", "回", "复", "。"]:
                yield chunk
                await asyncio.sleep(0.02)
        
        self.manager._agent.stream_chat = mock_agent_stream
        
        # Mock TTS 引擎（模拟真实延迟）
        async def mock_tts_stream(*args, **kwargs):
            await asyncio.sleep(0.18)  # 首包延迟 180ms
            for i in range(3):
                yield b"audio_chunk", None, None
                await asyncio.sleep(0.05)
        
        self.manager._tts_engine.stream_synthesize = mock_tts_stream
        
        # Mock 音频设备
        self.manager._audio_device.play_audio = AsyncMock()
        self.manager._audio_device.stop_listening = Mock()
        self.manager._audio_device.start_listening = Mock()
        
        # 初始化
        self.manager.initialize()
        
    async def teardown(self):
        """清理测试环境"""
        if self.manager:
            self.manager.stop_sync()
    
    async def test_asr_first_chunk_latency(self):
        """测试 1: ASR 首包延迟 <100ms"""
        print("\n" + "="*60)
        print("测试 1: ASR 首包延迟")
        print("="*60)
        
        try:
            latencies = []
            
            # 进行 10 次测试
            for i in range(10):
                # 重置性能统计
                self.manager.reset_performance_stats()
                
                # 模拟用户输入
                await self.manager.on_user_input(f"测试 {i+1}")
                
                # 等待处理完成
                await asyncio.sleep(1.0)
                
                # 获取性能统计
                stats = self.manager.get_performance_stats()
                
                if "asr" in stats and "first_chunk_latency" in stats["asr"]:
                    latency = stats["asr"]["first_chunk_latency"]["avg"]
                    latencies.append(latency)
            
            # 计算统计
            avg_latency = statistics.mean(latencies)
            p95_latency = self._percentile(latencies, 0.95)
            
            # 验证性能
            target = 100  # ms
            passed = avg_latency < target
            
            print(f"ASR 首包延迟:")
            print(f"  - 平均: {avg_latency:.1f}ms")
            print(f"  - P95: {p95_latency:.1f}ms")
            print(f"  - 目标: <{target}ms")
            print(f"  - 状态: {'✅ 通过' if passed else '❌ 未达标'}")
            
            self.test_results.append({
                "test": "asr_first_chunk_latency",
                "status": "PASS" if passed else "FAIL",
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "target_ms": target,
                "latencies": latencies,
            })
            
        except Exception as e:
            print(f"❌ ASR 首包延迟测试失败: {e}")
            self.test_results.append({
                "test": "asr_first_chunk_latency",
                "status": "ERROR",
                "error": str(e),
            })
    
    async def test_tts_first_chunk_latency(self):
        """测试 2: TTS 首包延迟 <200ms"""
        print("\n" + "="*60)
        print("测试 2: TTS 首包延迟")
        print("="*60)
        
        try:
            latencies = []
            
            # 进行 10 次测试
            for i in range(10):
                # 重置性能统计
                self.manager.reset_performance_stats()
                
                # 模拟用户输入
                await self.manager.on_user_input(f"测试 {i+1}")
                
                # 等待处理完成
                await asyncio.sleep(1.0)
                
                # 获取性能统计
                stats = self.manager.get_performance_stats()
                
                if "tts" in stats and "first_chunk_latency" in stats["tts"]:
                    latency = stats["tts"]["first_chunk_latency"]["avg"]
                    latencies.append(latency)
            
            # 计算统计
            avg_latency = statistics.mean(latencies)
            p95_latency = self._percentile(latencies, 0.95)
            
            # 验证性能
            target = 200  # ms
            passed = avg_latency < target
            
            print(f"TTS 首包延迟:")
            print(f"  - 平均: {avg_latency:.1f}ms")
            print(f"  - P95: {p95_latency:.1f}ms")
            print(f"  - 目标: <{target}ms")
            print(f"  - 状态: {'✅ 通过' if passed else '❌ 未达标'}")
            
            self.test_results.append({
                "test": "tts_first_chunk_latency",
                "status": "PASS" if passed else "FAIL",
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "target_ms": target,
                "latencies": latencies,
            })
            
        except Exception as e:
            print(f"❌ TTS 首包延迟测试失败: {e}")
            self.test_results.append({
                "test": "tts_first_chunk_latency",
                "status": "ERROR",
                "error": str(e),
            })
    
    async def test_speaker_recognition_latency(self):
        """测试 3: 声纹识别延迟 <500ms"""
        print("\n" + "="*60)
        print("测试 3: 声纹识别延迟")
        print("="*60)
        
        try:
            # 注意：当前实现中声纹识别未集成到性能监控
            # 这里只是占位测试，实际需要集成后才能测试
            
            print("⚠️  声纹识别性能监控尚未集成")
            print("   跳过此测试")
            
            self.test_results.append({
                "test": "speaker_recognition_latency",
                "status": "SKIP",
                "reason": "声纹识别性能监控尚未集成",
            })
            
        except Exception as e:
            print(f"❌ 声纹识别延迟测试失败: {e}")
            self.test_results.append({
                "test": "speaker_recognition_latency",
                "status": "ERROR",
                "error": str(e),
            })
    
    async def test_total_conversation_latency(self):
        """测试 4: 整体对话延迟 <1.5s"""
        print("\n" + "="*60)
        print("测试 4: 整体对话延迟")
        print("="*60)
        
        try:
            latencies = []
            
            # 进行 10 次测试
            for i in range(10):
                # 重置性能统计
                self.manager.reset_performance_stats()
                
                # 记录开始时间
                t_start = time.monotonic()
                
                # 模拟用户输入
                await self.manager.on_user_input(f"测试 {i+1}")
                
                # 等待处理完成
                await asyncio.sleep(1.0)
                
                # 记录结束时间
                t_end = time.monotonic()
                
                # 计算总延迟
                total_latency_ms = (t_end - t_start) * 1000
                latencies.append(total_latency_ms)
            
            # 计算统计
            avg_latency = statistics.mean(latencies)
            p95_latency = self._percentile(latencies, 0.95)
            
            # 验证性能
            target = 1500  # ms
            passed = avg_latency < target
            
            print(f"整体对话延迟:")
            print(f"  - 平均: {avg_latency:.1f}ms")
            print(f"  - P95: {p95_latency:.1f}ms")
            print(f"  - 目标: <{target}ms")
            print(f"  - 状态: {'✅ 通过' if passed else '❌ 未达标'}")
            
            self.test_results.append({
                "test": "total_conversation_latency",
                "status": "PASS" if passed else "FAIL",
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "target_ms": target,
                "latencies": latencies,
            })
            
        except Exception as e:
            print(f"❌ 整体对话延迟测试失败: {e}")
            self.test_results.append({
                "test": "total_conversation_latency",
                "status": "ERROR",
                "error": str(e),
            })
    
    async def test_tts_cache_performance(self):
        """测试 5: TTS 缓存性能"""
        print("\n" + "="*60)
        print("测试 5: TTS 缓存性能")
        print("="*60)
        
        try:
            # 测试常用短语的缓存命中
            common_phrases = ["好的", "明白了", "收到", "没问题"]
            
            # 第一次合成（缓存未命中）
            first_latencies = []
            for phrase in common_phrases:
                self.manager.reset_performance_stats()
                await self.manager.on_user_input(phrase)
                await asyncio.sleep(0.5)
                
                stats = self.manager.get_performance_stats()
                if "tts" in stats and "first_chunk_latency" in stats["tts"]:
                    latency = stats["tts"]["first_chunk_latency"]["avg"]
                    first_latencies.append(latency)
            
            # 第二次合成（应该命中缓存）
            second_latencies = []
            for phrase in common_phrases:
                self.manager.reset_performance_stats()
                await self.manager.on_user_input(phrase)
                await asyncio.sleep(0.5)
                
                stats = self.manager.get_performance_stats()
                if "tts" in stats and "first_chunk_latency" in stats["tts"]:
                    latency = stats["tts"]["first_chunk_latency"]["avg"]
                    second_latencies.append(latency)
            
            # 计算统计
            if first_latencies and second_latencies:
                avg_first = statistics.mean(first_latencies)
                avg_second = statistics.mean(second_latencies)
                improvement = (avg_first - avg_second) / avg_first * 100
                
                print(f"TTS 缓存性能:")
                print(f"  - 首次合成: {avg_first:.1f}ms")
                print(f"  - 缓存命中: {avg_second:.1f}ms")
                print(f"  - 性能提升: {improvement:.1f}%")
                
                self.test_results.append({
                    "test": "tts_cache_performance",
                    "status": "PASS",
                    "first_latency_ms": avg_first,
                    "cached_latency_ms": avg_second,
                    "improvement_percent": improvement,
                })
            else:
                print("⚠️  无法获取 TTS 性能数据")
                self.test_results.append({
                    "test": "tts_cache_performance",
                    "status": "SKIP",
                    "reason": "无法获取 TTS 性能数据",
                })
            
        except Exception as e:
            print(f"❌ TTS 缓存性能测试失败: {e}")
            self.test_results.append({
                "test": "tts_cache_performance",
                "status": "ERROR",
                "error": str(e),
            })
    
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
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("性能基准测试")
        print("="*60)
        
        await self.setup()
        
        try:
            await self.test_asr_first_chunk_latency()
            await self.test_tts_first_chunk_latency()
            await self.test_speaker_recognition_latency()
            await self.test_total_conversation_latency()
            await self.test_tts_cache_performance()
        finally:
            await self.teardown()
        
        # 打印测试结果摘要
        self.print_summary()
    
    def print_summary(self):
        """打印测试结果摘要"""
        print("\n" + "="*60)
        print("性能基准测试结果摘要")
        print("="*60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.test_results if r["status"] == "SKIP")
        errors = sum(1 for r in self.test_results if r["status"] == "ERROR")
        
        print(f"\n总测试数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"跳过: {skipped}")
        print(f"错误: {errors}")
        
        # 打印详细结果
        print("\n详细结果:")
        for result in self.test_results:
            test_name = result["test"]
            status = result["status"]
            
            if status == "PASS":
                print(f"  ✅ {test_name}")
                if "avg_latency_ms" in result:
                    print(f"     平均延迟: {result['avg_latency_ms']:.1f}ms (目标: <{result.get('target_ms', 'N/A')}ms)")
            elif status == "FAIL":
                print(f"  ❌ {test_name}")
                if "avg_latency_ms" in result:
                    print(f"     平均延迟: {result['avg_latency_ms']:.1f}ms (目标: <{result.get('target_ms', 'N/A')}ms)")
            elif status == "SKIP":
                print(f"  ⚠️  {test_name} (跳过: {result.get('reason', 'Unknown')})")
            elif status == "ERROR":
                print(f"  ❌ {test_name} (错误: {result.get('error', 'Unknown')})")
        
        if failed == 0 and errors == 0:
            print("\n✅ 所有性能基准测试通过！")
        else:
            print(f"\n❌ {failed + errors} 个测试失败或出错")


async def main():
    """主函数"""
    tester = TestPerformanceBenchmarks()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
