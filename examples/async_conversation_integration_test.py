#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
异步对话管理器集成测试

测试完整的对话流程，包括 ASR、Agent、TTS 和打断功能

使用方式:
    python examples/async_conversation_integration_test.py
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core.conversation_manager_async import (
    AsyncConversationManager,
    ConversationConfig,
    ConversationState
)
from core.log import log


async def test_text_mode():
    """测试文本输入模式（不需要 ASR/TTS/Agent）"""
    print("\n" + "=" * 60)
    print("测试 1: 文本输入模式")
    print("=" * 60)
    
    config = ConversationConfig(
        use_text_input=True,
        enable_barge_in=True,
        interrupt_feedback_enabled=True,
    )
    
    manager = AsyncConversationManager(config)
    
    # 设置回调
    states = []
    subtitles = []
    
    def on_state_change(state: ConversationState):
        states.append(state)
        print(f"[状态] {state.value}")
    
    def on_subtitle(text: str, is_final: bool, emotion: str):
        subtitles.append((text, is_final, emotion))
        print(f"[字幕] {text} (final={is_final}, emotion={emotion})")
    
    manager.set_callbacks(
        on_state_change=on_state_change,
        on_subtitle=on_subtitle,
    )
    
    # 初始化（跳过 ASR/TTS/Agent）
    manager._init_audio()
    
    # 模拟对话
    print("\n模拟用户输入...")
    manager.run_turn("你好")
    
    # 等待一会儿
    await asyncio.sleep(0.5)
    
    # 打断
    print("\n模拟打断...")
    await manager.cancel_current_turn()
    
    # 新的输入
    print("\n模拟新输入...")
    manager.run_turn("再见")
    
    await asyncio.sleep(0.5)
    
    print(f"\n✅ 测试完成")
    print(f"   - 状态变化: {len(states)} 次")
    print(f"   - 字幕更新: {len(subtitles)} 次")
    print(f"   - 打断次数: {manager._interrupt_count}")


async def test_with_tts():
    """测试带 TTS 的对话（需要 TTS 服务）"""
    print("\n" + "=" * 60)
    print("测试 2: TTS 集成测试")
    print("=" * 60)
    
    # 检查 TTS 服务是否可用
    try:
        from backend.tts.remote_client import RemoteTTSClient, RemoteTTSConfig
        
        remote_config = RemoteTTSConfig(
            base_url="http://localhost:9880",
            spk_id="中文女",
        )
        client = RemoteTTSClient(remote_config)
        
        if not client.health_check():
            print("⚠️  TTS 服务不可用，跳过测试")
            return
        
        print("✅ TTS 服务可用")
        
    except Exception as e:
        print(f"⚠️  TTS 服务检查失败: {e}")
        return
    
    # 创建配置
    config = ConversationConfig(
        use_text_input=True,
        tts_remote_url="http://localhost:9880",
        tts_spk_id="中文女",
        enable_barge_in=True,
    )
    
    manager = AsyncConversationManager(config)
    
    # 设置回调
    def on_subtitle(text: str, is_final: bool, emotion: str):
        print(f"[字幕] {text}")
    
    def on_viseme(openY: float, form: float):
        print(f"[嘴型] openY={openY:.2f}, form={form:.2f}")
    
    manager.set_callbacks(
        on_subtitle=on_subtitle,
        on_viseme=on_viseme,
    )
    
    # 初始化
    manager.initialize()
    
    # 模拟对话
    print("\n开始对话...")
    manager.run_turn("你好，今天天气真好！")
    
    # 等待 TTS 播放
    if manager._current_turn:
        try:
            await asyncio.wait_for(manager._current_turn, timeout=10.0)
        except asyncio.TimeoutError:
            print("⚠️  TTS 播放超时")
    
    print("\n✅ TTS 测试完成")


async def test_interrupt_timing():
    """测试打断响应时间"""
    print("\n" + "=" * 60)
    print("测试 3: 打断响应时间")
    print("=" * 60)
    
    config = ConversationConfig(
        use_text_input=True,
        enable_barge_in=True,
    )
    
    manager = AsyncConversationManager(config)
    manager._init_audio()
    
    # 启动 turn
    import time
    manager.run_turn("这是一段很长的文本，用来测试打断功能的响应时间")
    
    # 等待一会儿
    await asyncio.sleep(0.1)
    
    # 测量打断时间
    t0 = time.monotonic()
    await manager.cancel_current_turn()
    t1 = time.monotonic()
    
    interrupt_time_ms = (t1 - t0) * 1000
    
    print(f"\n✅ 打断响应时间: {interrupt_time_ms:.2f}ms")
    
    if interrupt_time_ms < 200:
        print("   ✅ 满足 <200ms 要求")
    else:
        print("   ⚠️  超过 200ms 要求")


async def test_sentence_splitting_performance():
    """测试句子切分性能"""
    print("\n" + "=" * 60)
    print("测试 4: 句子切分性能")
    print("=" * 60)
    
    from core.conversation_manager_async import _pop_sentence
    import time
    
    # 测试文本
    test_text = """
    你好！今天天气真好。我们来聊聊天吧，看看这个句子切分功能是否工作正常。
    这是一个很长的句子，超过了十八个字符，应该在逗号处进行软切分，这样可以提高响应速度。
    短句。另一个短句！还有一个？最后一句。
    """
    
    # 测试切分
    buf = test_text.strip()
    sentences = []
    
    t0 = time.monotonic()
    while buf:
        sentence, buf = _pop_sentence(buf)
        if sentence:
            sentences.append(sentence)
        else:
            if buf:
                sentences.append(buf)
            break
    t1 = time.monotonic()
    
    print(f"\n切分结果:")
    for i, s in enumerate(sentences, 1):
        print(f"  {i}. {s[:50]}...")
    
    print(f"\n✅ 切分性能:")
    print(f"   - 句子数量: {len(sentences)}")
    print(f"   - 切分时间: {(t1-t0)*1000:.2f}ms")
    print(f"   - 平均每句: {(t1-t0)*1000/len(sentences):.2f}ms")


async def test_dedup_performance():
    """测试去重性能"""
    print("\n" + "=" * 60)
    print("测试 5: 去重性能")
    print("=" * 60)
    
    config = ConversationConfig(use_text_input=True)
    manager = AsyncConversationManager(config)
    
    import time
    
    # 测试去重
    test_texts = ["你好"] * 100
    
    t0 = time.monotonic()
    accepted = 0
    for text in test_texts:
        if manager._should_submit(text):
            accepted += 1
    t1 = time.monotonic()
    
    print(f"\n✅ 去重性能:")
    print(f"   - 总请求: {len(test_texts)}")
    print(f"   - 接受: {accepted}")
    print(f"   - 拒绝: {len(test_texts) - accepted}")
    print(f"   - 总时间: {(t1-t0)*1000:.2f}ms")
    print(f"   - 平均每次: {(t1-t0)*1000/len(test_texts):.3f}ms")


async def main():
    """运行所有集成测试"""
    print("\n" + "=" * 60)
    print("异步对话管理器集成测试套件")
    print("=" * 60)
    
    try:
        # 基础测试
        await test_text_mode()
        
        # 性能测试
        await test_interrupt_timing()
        await test_sentence_splitting_performance()
        await test_dedup_performance()
        
        # TTS 集成测试（可选）
        await test_with_tts()
        
        print("\n" + "=" * 60)
        print("✅ 所有集成测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
