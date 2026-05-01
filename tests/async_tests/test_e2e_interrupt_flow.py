"""
端到端打断流程集成测试

测试完整的打断流程，包括：
1. 正常对话流程
2. 打断流程
3. 打断后的对话恢复
4. 打断响应时间验证
"""

import asyncio
import time
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch
import sys
import os
import pytest

# 添加项目根目录和 src 目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'src'))

from src.core.conversation_manager_async import (
    AsyncConversationManager,
    ConversationConfig,
    ConversationState,
)


class TestE2EInterruptFlow:
    """端到端打断流程测试"""

    def setup_method(self):
        self.test_results: List[Dict[str, Any]] = []
        self.manager: AsyncConversationManager = None

    async def setup(self):
        """设置测试环境"""
        # 创建配置
        config = ConversationConfig(
            enable_barge_in=True,
            interrupt_feedback_enabled=True,
            interrupt_feedback_text="已打断",
            interrupt_context_mode="reset",
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
            yield "测试", False
            yield "文本", True
        
        self.manager._asr_engine.stream_recognize = mock_asr_stream
        
        # Mock Agent
        async def mock_agent_stream(*args, **kwargs):
            for chunk in ["这", "是", "一", "个", "很", "长", "的", "回", "复", "。"]:
                yield chunk
                await asyncio.sleep(0.05)  # 模拟流式生成
        
        self.manager._agent.stream_chat = mock_agent_stream
        
        # Mock TTS 引擎
        async def mock_tts_stream(*args, **kwargs):
            for i in range(5):
                yield b"audio_chunk", None, None
                await asyncio.sleep(0.1)  # 模拟合成延迟
        
        self.manager._tts_engine.stream_synthesize = mock_tts_stream
        
        # Mock 音频设备
        self.manager._audio_device.play_audio = AsyncMock()
        self.manager._audio_device.stop_listening = Mock()
        self.manager._audio_device.start_listening = Mock()
        
        # 设置回调
        self.state_changes = []
        self.subtitles = []
        
        def on_state_change(state):
            self.state_changes.append((time.monotonic(), state))
        
        def on_subtitle(text, is_final, emotion):
            self.subtitles.append((time.monotonic(), text, is_final))
        
        self.manager.set_callbacks(
            on_state_change=on_state_change,
            on_subtitle=on_subtitle,
        )
        
        # 初始化
        self.manager.initialize()
        
    async def teardown(self):
        """清理测试环境"""
        if self.manager:
            self.manager.stop_sync()
    
    @pytest.mark.asyncio
    async def test_normal_conversation_flow(self):
        """测试 1: 正常对话流程"""
        print("\n" + "="*60)
        print("测试 1: 正常对话流程")
        print("="*60)
        
        try:
            # 清空记录
            self.state_changes.clear()
            self.subtitles.clear()
            
            # 模拟用户输入
            await self.manager.on_user_input("你好")
            
            # 等待处理完成
            await asyncio.sleep(1.0)
            
            # 验证状态变化
            states = [s for _, s in self.state_changes]
            assert ConversationState.LISTENING in states, "应该进入 LISTENING 状态"
            assert ConversationState.THINKING in states, "应该进入 THINKING 状态"
            assert ConversationState.SPEAKING in states, "应该进入 SPEAKING 状态"
            
            # 验证字幕
            assert len(self.subtitles) > 0, "应该有字幕输出"
            
            print("✅ 正常对话流程测试通过")
            self.test_results.append({
                "test": "normal_conversation_flow",
                "status": "PASS",
                "states": len(states),
                "subtitles": len(self.subtitles),
            })
            
        except Exception as e:
            print(f"❌ 正常对话流程测试失败: {e}")
            self.test_results.append({
                "test": "normal_conversation_flow",
                "status": "FAIL",
                "error": str(e),
            })
    
    @pytest.mark.asyncio
    async def test_interrupt_flow(self):
        """测试 2: 打断流程"""
        print("\n" + "="*60)
        print("测试 2: 打断流程")
        print("="*60)
        
        try:
            # 清空记录
            self.state_changes.clear()
            self.subtitles.clear()
            
            # 模拟用户输入
            user_input_task = asyncio.create_task(
                self.manager.on_user_input("讲一个长故事")
            )
            
            # 等待进入 SPEAKING 状态
            await asyncio.sleep(0.3)
            
            # 记录打断前的状态
            states_before = [s for _, s in self.state_changes]
            assert ConversationState.SPEAKING in states_before, "应该进入 SPEAKING 状态"
            
            # 模拟打断
            t_interrupt_start = time.monotonic()
            await self.manager.cancel_current_turn()
            t_interrupt_end = time.monotonic()
            
            # 计算打断响应时间
            interrupt_response_time_ms = (t_interrupt_end - t_interrupt_start) * 1000
            
            # 等待打断完成
            await asyncio.sleep(0.2)
            
            # 验证状态变化
            states_after = [s for _, s in self.state_changes]
            assert ConversationState.LISTENING in states_after, "打断后应该回到 LISTENING 状态"
            
            # 验证打断响应时间
            assert interrupt_response_time_ms < 200, f"打断响应时间应该 <200ms，实际: {interrupt_response_time_ms:.1f}ms"
            
            print(f"✅ 打断流程测试通过")
            print(f"   打断响应时间: {interrupt_response_time_ms:.1f}ms")
            self.test_results.append({
                "test": "interrupt_flow",
                "status": "PASS",
                "interrupt_response_time_ms": interrupt_response_time_ms,
            })
            
            # 取消用户输入任务
            user_input_task.cancel()
            try:
                await user_input_task
            except asyncio.CancelledError:
                pass
            
        except Exception as e:
            print(f"❌ 打断流程测试失败: {e}")
            self.test_results.append({
                "test": "interrupt_flow",
                "status": "FAIL",
                "error": str(e),
            })
    
    @pytest.mark.asyncio
    async def test_conversation_recovery_after_interrupt(self):
        """测试 3: 打断后的对话恢复"""
        print("\n" + "="*60)
        print("测试 3: 打断后的对话恢复")
        print("="*60)
        
        try:
            # 清空记录
            self.state_changes.clear()
            self.subtitles.clear()
            
            # 第一轮对话
            user_input_task = asyncio.create_task(
                self.manager.on_user_input("第一轮对话")
            )
            
            # 等待进入 SPEAKING 状态
            await asyncio.sleep(0.3)
            
            # 打断
            await self.manager.cancel_current_turn()
            await asyncio.sleep(0.2)
            
            # 取消第一轮任务
            user_input_task.cancel()
            try:
                await user_input_task
            except asyncio.CancelledError:
                pass
            
            # 清空记录
            self.state_changes.clear()
            self.subtitles.clear()
            
            # 第二轮对话（打断后恢复）
            await self.manager.on_user_input("第二轮对话")
            
            # 等待处理完成
            await asyncio.sleep(1.0)
            
            # 验证状态变化
            states = [s for _, s in self.state_changes]
            assert ConversationState.LISTENING in states, "应该进入 LISTENING 状态"
            assert ConversationState.THINKING in states, "应该进入 THINKING 状态"
            assert ConversationState.SPEAKING in states, "应该进入 SPEAKING 状态"
            
            # 验证字幕
            assert len(self.subtitles) > 0, "应该有字幕输出"
            
            print("✅ 打断后对话恢复测试通过")
            self.test_results.append({
                "test": "conversation_recovery_after_interrupt",
                "status": "PASS",
                "states": len(states),
                "subtitles": len(self.subtitles),
            })
            
        except Exception as e:
            print(f"❌ 打断后对话恢复测试失败: {e}")
            self.test_results.append({
                "test": "conversation_recovery_after_interrupt",
                "status": "FAIL",
                "error": str(e),
            })
    
    @pytest.mark.asyncio
    async def test_interrupt_response_time(self):
        """测试 4: 打断响应时间验证"""
        print("\n" + "="*60)
        print("测试 4: 打断响应时间验证")
        print("="*60)
        
        try:
            response_times = []
            
            # 进行 5 次打断测试
            for i in range(5):
                # 清空记录
                self.state_changes.clear()
                
                # 模拟用户输入
                user_input_task = asyncio.create_task(
                    self.manager.on_user_input(f"测试 {i+1}")
                )
                
                # 等待进入 SPEAKING 状态
                await asyncio.sleep(0.3)
                
                # 模拟打断
                t_start = time.monotonic()
                await self.manager.cancel_current_turn()
                t_end = time.monotonic()
                
                response_time_ms = (t_end - t_start) * 1000
                response_times.append(response_time_ms)
                
                # 等待打断完成
                await asyncio.sleep(0.2)
                
                # 取消用户输入任务
                user_input_task.cancel()
                try:
                    await user_input_task
                except asyncio.CancelledError:
                    pass
            
            # 计算统计
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            
            # 验证响应时间
            assert avg_response_time < 200, f"平均打断响应时间应该 <200ms，实际: {avg_response_time:.1f}ms"
            assert max_response_time < 200, f"最大打断响应时间应该 <200ms，实际: {max_response_time:.1f}ms"
            
            print(f"✅ 打断响应时间验证通过")
            print(f"   平均响应时间: {avg_response_time:.1f}ms")
            print(f"   最大响应时间: {max_response_time:.1f}ms")
            self.test_results.append({
                "test": "interrupt_response_time",
                "status": "PASS",
                "avg_response_time_ms": avg_response_time,
                "max_response_time_ms": max_response_time,
                "response_times": response_times,
            })
            
        except Exception as e:
            print(f"❌ 打断响应时间验证失败: {e}")
            self.test_results.append({
                "test": "interrupt_response_time",
                "status": "FAIL",
                "error": str(e),
            })
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("端到端打断流程集成测试")
        print("="*60)
        
        await self.setup()
        
        try:
            await self.test_normal_conversation_flow()
            await self.test_interrupt_flow()
            await self.test_conversation_recovery_after_interrupt()
            await self.test_interrupt_response_time()
        finally:
            await self.teardown()
        
        # 打印测试结果摘要
        self.print_summary()
    
    def print_summary(self):
        """打印测试结果摘要"""
        print("\n" + "="*60)
        print("测试结果摘要")
        print("="*60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = total - passed
        
        print(f"\n总测试数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        
        if failed == 0:
            print("\n✅ 所有端到端打断流程测试通过！")
        else:
            print(f"\n❌ {failed} 个测试失败")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"   - {result['test']}: {result.get('error', 'Unknown error')}")


async def main():
    """主函数"""
    tester = TestE2EInterruptFlow()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
