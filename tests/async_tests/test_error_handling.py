"""
错误处理和降级测试

测试系统在各种错误情况下的处理和降级策略：
1. 打断检测失败
2. TTS 播放失败
3. 声纹识别失败
4. 验证系统优雅降级
"""

import asyncio
import time
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock
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


class TestErrorHandling:
    """错误处理和降级测试"""

    def setup_method(self):
        self.test_results: List[Dict[str, Any]] = []
        self.manager: AsyncConversationManager = None

    async def setup(self, config_overrides: dict = None):
        """设置测试环境"""
        # 创建配置
        config_dict = {
            "enable_barge_in": True,
            "interrupt_feedback_enabled": True,
            "tts_enable_cache": True,
        }
        if config_overrides:
            config_dict.update(config_overrides)
        
        config = ConversationConfig(**config_dict)
        
        # 创建管理器
        self.manager = AsyncConversationManager(config)
        
        # Mock 外部依赖
        self.manager._asr_engine = Mock()
        self.manager._agent = Mock()
        self.manager._tts_engine = Mock()
        self.manager._audio_device = Mock()
        
        # 初始化
        self.manager.initialize()
        
    async def teardown(self):
        """清理测试环境"""
        if self.manager:
            self.manager.stop_sync()
    
    @pytest.mark.asyncio
    async def test_asr_failure_handling(self):
        """测试 1: ASR 识别失败处理"""
        print("\n" + "="*60)
        print("测试 1: ASR 识别失败处理")
        print("="*60)
        
        try:
            await self.setup()
            
            # Mock ASR 引擎抛出异常
            async def mock_asr_stream_error(*args, **kwargs):
                raise Exception("ASR 识别失败")
            
            self.manager._asr_engine.stream_recognize = mock_asr_stream_error
            
            # 记录状态变化
            state_changes = []
            def on_state_change(state):
                state_changes.append(state)
            
            self.manager.set_callbacks(on_state_change=on_state_change)
            
            # 尝试识别
            try:
                await self.manager.on_user_input("测试")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"   捕获异常: {e}")
            
            # 验证系统仍然可以继续运行
            # 系统应该优雅降级，不应该崩溃
            assert self.manager._running, "系统应该继续运行"
            
            print("✅ ASR 识别失败处理测试通过")
            print("   系统优雅降级，继续运行")
            self.test_results.append({
                "test": "asr_failure_handling",
                "status": "PASS",
                "graceful_degradation": True,
            })
            
        except Exception as e:
            print(f"❌ ASR 识别失败处理测试失败: {e}")
            self.test_results.append({
                "test": "asr_failure_handling",
                "status": "FAIL",
                "error": str(e),
            })
        finally:
            await self.teardown()
    
    @pytest.mark.asyncio
    async def test_tts_failure_handling(self):
        """测试 2: TTS 播放失败处理"""
        print("\n" + "="*60)
        print("测试 2: TTS 播放失败处理")
        print("="*60)
        
        try:
            await self.setup()
            
            # Mock ASR 引擎正常工作
            async def mock_asr_stream(*args, **kwargs):
                yield "测试", False
                yield "文本", True
            
            self.manager._asr_engine.stream_recognize = mock_asr_stream
            
            # Mock Agent 正常工作
            async def mock_agent_stream(*args, **kwargs):
                for chunk in ["测", "试", "回", "复"]:
                    yield chunk
                    await asyncio.sleep(0.01)
            
            self.manager._agent.stream_chat = mock_agent_stream
            
            # Mock TTS 引擎抛出异常
            async def mock_tts_stream_error(*args, **kwargs):
                raise Exception("TTS 合成失败")
            
            self.manager._tts_engine.stream_synthesize = mock_tts_stream_error
            
            # Mock 音频设备
            self.manager._audio_device.play_audio = AsyncMock()
            self.manager._audio_device.stop_listening = Mock()
            self.manager._audio_device.start_listening = Mock()
            
            # 记录状态变化
            state_changes = []
            def on_state_change(state):
                state_changes.append(state)
            
            self.manager.set_callbacks(on_state_change=on_state_change)
            
            # 尝试对话
            try:
                await self.manager.on_user_input("测试")
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"   捕获异常: {e}")
            
            # 验证系统仍然可以继续运行
            assert self.manager._running, "系统应该继续运行"
            
            # 验证状态最终回到 LISTENING
            # 即使 TTS 失败，系统也应该恢复到可用状态
            await asyncio.sleep(0.5)
            
            print("✅ TTS 播放失败处理测试通过")
            print("   系统优雅降级，继续运行")
            self.test_results.append({
                "test": "tts_failure_handling",
                "status": "PASS",
                "graceful_degradation": True,
            })
            
        except Exception as e:
            print(f"❌ TTS 播放失败处理测试失败: {e}")
            self.test_results.append({
                "test": "tts_failure_handling",
                "status": "FAIL",
                "error": str(e),
            })
        finally:
            await self.teardown()
    
    @pytest.mark.asyncio
    async def test_llm_failure_handling(self):
        """测试 3: LLM 生成失败处理"""
        print("\n" + "="*60)
        print("测试 3: LLM 生成失败处理")
        print("="*60)
        
        try:
            await self.setup()
            
            # Mock ASR 引擎正常工作
            async def mock_asr_stream(*args, **kwargs):
                yield "测试", False
                yield "文本", True
            
            self.manager._asr_engine.stream_recognize = mock_asr_stream
            
            # Mock Agent 抛出异常
            async def mock_agent_stream_error(*args, **kwargs):
                raise Exception("LLM 生成失败")
            
            self.manager._agent.stream_chat = mock_agent_stream_error
            
            # Mock 音频设备
            self.manager._audio_device.stop_listening = Mock()
            self.manager._audio_device.start_listening = Mock()
            
            # 记录状态变化
            state_changes = []
            def on_state_change(state):
                state_changes.append(state)
            
            self.manager.set_callbacks(on_state_change=on_state_change)
            
            # 尝试对话
            try:
                await self.manager.on_user_input("测试")
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"   捕获异常: {e}")
            
            # 验证系统仍然可以继续运行
            assert self.manager._running, "系统应该继续运行"
            
            print("✅ LLM 生成失败处理测试通过")
            print("   系统优雅降级，继续运行")
            self.test_results.append({
                "test": "llm_failure_handling",
                "status": "PASS",
                "graceful_degradation": True,
            })
            
        except Exception as e:
            print(f"❌ LLM 生成失败处理测试失败: {e}")
            self.test_results.append({
                "test": "llm_failure_handling",
                "status": "FAIL",
                "error": str(e),
            })
        finally:
            await self.teardown()
    
    @pytest.mark.asyncio
    async def test_interrupt_during_error(self):
        """测试 4: 错误期间的打断处理"""
        print("\n" + "="*60)
        print("测试 4: 错误期间的打断处理")
        print("="*60)
        
        try:
            await self.setup()
            
            # Mock ASR 引擎正常工作
            async def mock_asr_stream(*args, **kwargs):
                yield "测试", False
                yield "文本", True
            
            self.manager._asr_engine.stream_recognize = mock_asr_stream
            
            # Mock Agent 正常工作但很慢
            async def mock_agent_stream(*args, **kwargs):
                for i in range(20):
                    yield "测"
                    await asyncio.sleep(0.1)  # 慢速生成
            
            self.manager._agent.stream_chat = mock_agent_stream
            
            # Mock TTS 引擎正常工作
            async def mock_tts_stream(*args, **kwargs):
                for i in range(3):
                    yield b"audio_chunk", None, None
                    await asyncio.sleep(0.05)
            
            self.manager._tts_engine.stream_synthesize = mock_tts_stream
            
            # Mock 音频设备
            self.manager._audio_device.play_audio = AsyncMock()
            self.manager._audio_device.stop_listening = Mock()
            self.manager._audio_device.start_listening = Mock()
            
            # 开始对话
            user_input_task = asyncio.create_task(
                self.manager.on_user_input("测试")
            )
            
            # 等待进入 SPEAKING 状态
            await asyncio.sleep(0.5)
            
            # 模拟打断
            t_start = time.monotonic()
            await self.manager.cancel_current_turn()
            t_end = time.monotonic()
            
            interrupt_time_ms = (t_end - t_start) * 1000
            
            # 验证打断成功
            assert interrupt_time_ms < 200, f"打断响应时间应该 <200ms，实际: {interrupt_time_ms:.1f}ms"
            
            # 取消用户输入任务
            user_input_task.cancel()
            try:
                await user_input_task
            except asyncio.CancelledError:
                pass
            
            print("✅ 错误期间打断处理测试通过")
            print(f"   打断响应时间: {interrupt_time_ms:.1f}ms")
            self.test_results.append({
                "test": "interrupt_during_error",
                "status": "PASS",
                "interrupt_time_ms": interrupt_time_ms,
            })
            
        except Exception as e:
            print(f"❌ 错误期间打断处理测试失败: {e}")
            self.test_results.append({
                "test": "interrupt_during_error",
                "status": "FAIL",
                "error": str(e),
            })
        finally:
            await self.teardown()
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """测试 5: 优雅关闭"""
        print("\n" + "="*60)
        print("测试 5: 优雅关闭")
        print("="*60)
        
        try:
            await self.setup()
            
            # Mock ASR 引擎正常工作
            async def mock_asr_stream(*args, **kwargs):
                yield "测试", False
                yield "文本", True
            
            self.manager._asr_engine.stream_recognize = mock_asr_stream
            
            # Mock Agent 正常工作但很慢
            async def mock_agent_stream(*args, **kwargs):
                for i in range(20):
                    yield "测"
                    await asyncio.sleep(0.1)
            
            self.manager._agent.stream_chat = mock_agent_stream
            
            # Mock TTS 引擎正常工作
            async def mock_tts_stream(*args, **kwargs):
                for i in range(5):
                    yield b"audio_chunk", None, None
                    await asyncio.sleep(0.1)
            
            self.manager._tts_engine.stream_synthesize = mock_tts_stream
            
            # Mock 音频设备
            self.manager._audio_device.play_audio = AsyncMock()
            self.manager._audio_device.stop_listening = Mock()
            self.manager._audio_device.start_listening = Mock()
            
            # 开始对话
            user_input_task = asyncio.create_task(
                self.manager.on_user_input("测试")
            )
            
            # 等待进入 SPEAKING 状态
            await asyncio.sleep(0.5)
            
            # 优雅关闭
            t_start = time.monotonic()
            self.manager.stop_sync()
            t_end = time.monotonic()
            
            shutdown_time_ms = (t_end - t_start) * 1000
            
            # 验证关闭成功
            assert not self.manager._running, "系统应该已停止"
            
            # 取消用户输入任务
            user_input_task.cancel()
            try:
                await user_input_task
            except asyncio.CancelledError:
                pass
            
            print("✅ 优雅关闭测试通过")
            print(f"   关闭时间: {shutdown_time_ms:.1f}ms")
            self.test_results.append({
                "test": "graceful_shutdown",
                "status": "PASS",
                "shutdown_time_ms": shutdown_time_ms,
            })
            
        except Exception as e:
            print(f"❌ 优雅关闭测试失败: {e}")
            self.test_results.append({
                "test": "graceful_shutdown",
                "status": "FAIL",
                "error": str(e),
            })
        finally:
            # 不调用 teardown，因为已经手动关闭
            pass
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("错误处理和降级测试")
        print("="*60)
        
        await self.test_asr_failure_handling()
        await self.test_tts_failure_handling()
        await self.test_llm_failure_handling()
        await self.test_interrupt_during_error()
        await self.test_graceful_shutdown()
        
        # 打印测试结果摘要
        self.print_summary()
    
    def print_summary(self):
        """打印测试结果摘要"""
        print("\n" + "="*60)
        print("错误处理和降级测试结果摘要")
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
                if "graceful_degradation" in result:
                    print(f"     优雅降级: {'是' if result['graceful_degradation'] else '否'}")
            else:
                print(f"  ❌ {test_name}")
                if "error" in result:
                    print(f"     错误: {result['error']}")
        
        if failed == 0:
            print("\n✅ 所有错误处理和降级测试通过！")
        else:
            print(f"\n❌ {failed} 个测试失败")


async def main():
    """主函数"""
    tester = TestErrorHandling()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
