"""
压力测试

测试系统在高负载情况下的稳定性和性能：
1. 连续打断测试
2. 高频对话测试
3. 资源占用测试
4. 验证系统稳定性
"""

import asyncio
import time
import psutil
import os
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.conversation_manager_async import (
    AsyncConversationManager,
    ConversationConfig,
    ConversationState,
)


class TestStress:
    """压力测试"""
    
    def __init__(self):
        self.test_results: List[Dict[str, Any]] = []
        self.manager: AsyncConversationManager = None
        self.process = psutil.Process(os.getpid())
        
    async def setup(self):
        """设置测试环境"""
        # 创建配置
        config = ConversationConfig(
            enable_barge_in=True,
            interrupt_feedback_enabled=True,
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
        
        # Mock ASR 引擎
        async def mock_asr_stream(*args, **kwargs):
            await asyncio.sleep(0.05)
            yield "测试", False
            yield "文本", True
        
        self.manager._asr_engine.stream_recognize = mock_asr_stream
        
        # Mock Agent
        async def mock_agent_stream(*args, **kwargs):
            await asyncio.sleep(0.1)
            for chunk in ["这", "是", "一", "个", "测", "试", "回", "复", "。"]:
                yield chunk
                await asyncio.sleep(0.02)
        
        self.manager._agent.stream_chat = mock_agent_stream
        
        # Mock TTS 引擎
        async def mock_tts_stream(*args, **kwargs):
            await asyncio.sleep(0.1)
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
    
    def get_memory_usage_mb(self) -> float:
        """获取当前内存使用量（MB）"""
        return self.process.memory_info().rss / 1024 / 1024
    
    def get_cpu_percent(self) -> float:
        """获取当前 CPU 使用率"""
        return self.process.cpu_percent(interval=0.1)
    
    async def test_continuous_interrupts(self):
        """测试 1: 连续打断测试"""
        print("\n" + "="*60)
        print("测试 1: 连续打断测试")
        print("="*60)
        
        try:
            # 记录初始资源使用
            initial_memory = self.get_memory_usage_mb()
            
            # 进行 50 次连续打断
            interrupt_count = 50
            interrupt_times = []
            
            for i in range(interrupt_count):
                # 开始对话
                user_input_task = asyncio.create_task(
                    self.manager.on_user_input(f"测试 {i+1}")
                )
                
                # 等待进入 SPEAKING 状态
                await asyncio.sleep(0.2)
                
                # 打断
                t_start = time.monotonic()
                await self.manager.cancel_current_turn()
                t_end = time.monotonic()
                
                interrupt_time_ms = (t_end - t_start) * 1000
                interrupt_times.append(interrupt_time_ms)
                
                # 取消用户输入任务
                user_input_task.cancel()
                try:
                    await user_input_task
                except asyncio.CancelledError:
                    pass
                
                # 短暂等待
                await asyncio.sleep(0.1)
            
            # 记录最终资源使用
            final_memory = self.get_memory_usage_mb()
            memory_increase = final_memory - initial_memory
            
            # 计算统计
            avg_interrupt_time = sum(interrupt_times) / len(interrupt_times)
            max_interrupt_time = max(interrupt_times)
            
            # 验证性能
            assert avg_interrupt_time < 200, f"平均打断时间应该 <200ms，实际: {avg_interrupt_time:.1f}ms"
            assert memory_increase < 100, f"内存增长应该 <100MB，实际: {memory_increase:.1f}MB"
            
            print(f"✅ 连续打断测试通过")
            print(f"   打断次数: {interrupt_count}")
            print(f"   平均打断时间: {avg_interrupt_time:.1f}ms")
            print(f"   最大打断时间: {max_interrupt_time:.1f}ms")
            print(f"   内存增长: {memory_increase:.1f}MB")
            
            self.test_results.append({
                "test": "continuous_interrupts",
                "status": "PASS",
                "interrupt_count": interrupt_count,
                "avg_interrupt_time_ms": avg_interrupt_time,
                "max_interrupt_time_ms": max_interrupt_time,
                "memory_increase_mb": memory_increase,
            })
            
        except Exception as e:
            print(f"❌ 连续打断测试失败: {e}")
            self.test_results.append({
                "test": "continuous_interrupts",
                "status": "FAIL",
                "error": str(e),
            })
    
    async def test_high_frequency_conversations(self):
        """测试 2: 高频对话测试"""
        print("\n" + "="*60)
        print("测试 2: 高频对话测试")
        print("="*60)
        
        try:
            # 记录初始资源使用
            initial_memory = self.get_memory_usage_mb()
            
            # 进行 100 次快速对话
            conversation_count = 100
            latencies = []
            
            for i in range(conversation_count):
                t_start = time.monotonic()
                
                # 模拟用户输入
                await self.manager.on_user_input(f"测试 {i+1}")
                
                # 等待处理完成
                await asyncio.sleep(0.5)
                
                t_end = time.monotonic()
                latency_ms = (t_end - t_start) * 1000
                latencies.append(latency_ms)
            
            # 记录最终资源使用
            final_memory = self.get_memory_usage_mb()
            memory_increase = final_memory - initial_memory
            
            # 计算统计
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            
            # 验证性能
            assert avg_latency < 2000, f"平均延迟应该 <2000ms，实际: {avg_latency:.1f}ms"
            assert memory_increase < 200, f"内存增长应该 <200MB，实际: {memory_increase:.1f}MB"
            
            print(f"✅ 高频对话测试通过")
            print(f"   对话次数: {conversation_count}")
            print(f"   平均延迟: {avg_latency:.1f}ms")
            print(f"   最大延迟: {max_latency:.1f}ms")
            print(f"   内存增长: {memory_increase:.1f}MB")
            
            self.test_results.append({
                "test": "high_frequency_conversations",
                "status": "PASS",
                "conversation_count": conversation_count,
                "avg_latency_ms": avg_latency,
                "max_latency_ms": max_latency,
                "memory_increase_mb": memory_increase,
            })
            
        except Exception as e:
            print(f"❌ 高频对话测试失败: {e}")
            self.test_results.append({
                "test": "high_frequency_conversations",
                "status": "FAIL",
                "error": str(e),
            })
    
    async def test_resource_usage(self):
        """测试 3: 资源占用测试"""
        print("\n" + "="*60)
        print("测试 3: 资源占用测试")
        print("="*60)
        
        try:
            # 记录初始资源使用
            initial_memory = self.get_memory_usage_mb()
            
            # 进行 30 次对话，监控资源使用
            memory_samples = []
            cpu_samples = []
            
            for i in range(30):
                # 模拟用户输入
                await self.manager.on_user_input(f"测试 {i+1}")
                
                # 等待处理完成
                await asyncio.sleep(0.5)
                
                # 记录资源使用
                memory_samples.append(self.get_memory_usage_mb())
                cpu_samples.append(self.get_cpu_percent())
            
            # 计算统计
            avg_memory = sum(memory_samples) / len(memory_samples)
            max_memory = max(memory_samples)
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
            
            memory_increase = max_memory - initial_memory
            
            # 验证资源使用
            assert memory_increase < 300, f"内存增长应该 <300MB，实际: {memory_increase:.1f}MB"
            assert avg_cpu < 80, f"平均 CPU 使用率应该 <80%，实际: {avg_cpu:.1f}%"
            
            print(f"✅ 资源占用测试通过")
            print(f"   平均内存: {avg_memory:.1f}MB")
            print(f"   最大内存: {max_memory:.1f}MB")
            print(f"   内存增长: {memory_increase:.1f}MB")
            print(f"   平均 CPU: {avg_cpu:.1f}%")
            print(f"   最大 CPU: {max_cpu:.1f}%")
            
            self.test_results.append({
                "test": "resource_usage",
                "status": "PASS",
                "avg_memory_mb": avg_memory,
                "max_memory_mb": max_memory,
                "memory_increase_mb": memory_increase,
                "avg_cpu_percent": avg_cpu,
                "max_cpu_percent": max_cpu,
            })
            
        except Exception as e:
            print(f"❌ 资源占用测试失败: {e}")
            self.test_results.append({
                "test": "resource_usage",
                "status": "FAIL",
                "error": str(e),
            })
    
    async def test_long_running_stability(self):
        """测试 4: 长时间运行稳定性"""
        print("\n" + "="*60)
        print("测试 4: 长时间运行稳定性")
        print("="*60)
        
        try:
            # 记录初始资源使用
            initial_memory = self.get_memory_usage_mb()
            
            # 运行 5 分钟（简化为 30 秒用于测试）
            duration_seconds = 30
            start_time = time.monotonic()
            conversation_count = 0
            error_count = 0
            
            while time.monotonic() - start_time < duration_seconds:
                try:
                    # 模拟用户输入
                    await self.manager.on_user_input(f"测试 {conversation_count+1}")
                    
                    # 等待处理完成
                    await asyncio.sleep(0.5)
                    
                    conversation_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"   错误 {error_count}: {e}")
            
            # 记录最终资源使用
            final_memory = self.get_memory_usage_mb()
            memory_increase = final_memory - initial_memory
            
            # 计算错误率
            error_rate = error_count / conversation_count * 100 if conversation_count > 0 else 0
            
            # 验证稳定性
            assert error_rate < 5, f"错误率应该 <5%，实际: {error_rate:.1f}%"
            assert memory_increase < 500, f"内存增长应该 <500MB，实际: {memory_increase:.1f}MB"
            
            print(f"✅ 长时间运行稳定性测试通过")
            print(f"   运行时间: {duration_seconds}秒")
            print(f"   对话次数: {conversation_count}")
            print(f"   错误次数: {error_count}")
            print(f"   错误率: {error_rate:.1f}%")
            print(f"   内存增长: {memory_increase:.1f}MB")
            
            self.test_results.append({
                "test": "long_running_stability",
                "status": "PASS",
                "duration_seconds": duration_seconds,
                "conversation_count": conversation_count,
                "error_count": error_count,
                "error_rate_percent": error_rate,
                "memory_increase_mb": memory_increase,
            })
            
        except Exception as e:
            print(f"❌ 长时间运行稳定性测试失败: {e}")
            self.test_results.append({
                "test": "long_running_stability",
                "status": "FAIL",
                "error": str(e),
            })
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("压力测试")
        print("="*60)
        
        await self.setup()
        
        try:
            await self.test_continuous_interrupts()
            await self.test_high_frequency_conversations()
            await self.test_resource_usage()
            await self.test_long_running_stability()
        finally:
            await self.teardown()
        
        # 打印测试结果摘要
        self.print_summary()
    
    def print_summary(self):
        """打印测试结果摘要"""
        print("\n" + "="*60)
        print("压力测试结果摘要")
        print("="*60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = total - passed
        
        print(f"\n总测试数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        
        # 打印详细结果
        print("\n详细结果:")
        for result in self.test_results:
            test_name = result["test"]
            status = result["status"]
            
            if status == "PASS":
                print(f"  ✅ {test_name}")
                if "memory_increase_mb" in result:
                    print(f"     内存增长: {result['memory_increase_mb']:.1f}MB")
            else:
                print(f"  ❌ {test_name}")
                if "error" in result:
                    print(f"     错误: {result['error']}")
        
        if failed == 0:
            print("\n✅ 所有压力测试通过！")
            print("   系统在高负载下稳定运行")
        else:
            print(f"\n❌ {failed} 个测试失败")


async def main():
    """主函数"""
    tester = TestStress()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
