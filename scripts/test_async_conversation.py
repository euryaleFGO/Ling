#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试异步对话管理器

使用方式:
    python scripts/test_async_conversation.py
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core.conversation_manager_async import AsyncConversationManager, ConversationConfig, ConversationState


def test_basic():
    """基础测试：初始化和配置"""
    print("=" * 60)
    print("测试 1: 基础初始化")
    print("=" * 60)
    
    config = ConversationConfig(
        use_text_input=True,  # 使用文本输入模式
        enable_barge_in=True,
        interrupt_feedback_enabled=True,
    )
    
    manager = AsyncConversationManager(config)
    
    # 设置回调
    def on_state_change(state: ConversationState):
        print(f"[回调] 状态变化: {state.value}")
    
    def on_user_text(text: str):
        print(f"[回调] 用户文本: {text}")
    
    def on_ai_text(text: str):
        print(f"[回调] AI 文本: {text}")
    
    def on_subtitle(text: str, is_final: bool, emotion: str):
        print(f"[回调] 字幕: {text} (final={is_final}, emotion={emotion})")
    
    manager.set_callbacks(
        on_state_change=on_state_change,
        on_user_text=on_user_text,
        on_ai_text=on_ai_text,
        on_subtitle=on_subtitle,
    )
    
    print("✅ 初始化成功")
    print(f"   - 配置: {config}")
    print(f"   - 状态: {manager.state}")
    print()


async def test_turn_management():
    """测试 Turn 管理"""
    print("=" * 60)
    print("测试 2: Turn 管理")
    print("=" * 60)
    
    config = ConversationConfig(use_text_input=True)
    manager = AsyncConversationManager(config)
    
    # 模拟启动 turn
    print("启动 turn...")
    manager.run_turn("你好")
    
    # 等待一小段时间
    await asyncio.sleep(0.1)
    
    # 检查 turn 是否在运行
    if manager._current_turn and not manager._current_turn.done():
        print("✅ Turn 正在运行")
        
        # 取消 turn
        print("取消 turn...")
        await manager.cancel_current_turn()
        print("✅ Turn 已取消")
    else:
        print("⚠️  Turn 未启动或已完成")
    
    print()


async def test_sentence_splitting():
    """测试句子切分"""
    print("=" * 60)
    print("测试 3: 句子切分")
    print("=" * 60)
    
    from core.conversation_manager_async import _pop_sentence
    
    test_cases = [
        ("你好。世界", "你好。", "世界"),
        ("这是一个很长的句子，超过了十八个字符，应该在逗号处切分", "这是一个很长的句子，", "超过了十八个字符，应该在逗号处切分"),
        ("短句", None, "短句"),
        ("你好！", "你好！", ""),
    ]
    
    for buf, expected_sentence, expected_remaining in test_cases:
        sentence, remaining = _pop_sentence(buf)
        if sentence == expected_sentence and remaining == expected_remaining:
            print(f"✅ '{buf[:20]}...' → '{sentence}' | '{remaining[:20]}...'")
        else:
            print(f"❌ '{buf[:20]}...'")
            print(f"   期望: '{expected_sentence}' | '{expected_remaining}'")
            print(f"   实际: '{sentence}' | '{remaining}'")
    
    print()


async def test_dedup():
    """测试去重机制"""
    print("=" * 60)
    print("测试 4: 去重机制")
    print("=" * 60)
    
    config = ConversationConfig(use_text_input=True)
    manager = AsyncConversationManager(config)
    
    # 第一次提交
    text = "测试文本"
    result1 = manager._should_submit(text)
    print(f"第一次提交 '{text}': {result1}")
    
    # 立即重复提交（应该被拒绝）
    result2 = manager._should_submit(text)
    print(f"立即重复提交 '{text}': {result2}")
    
    # 等待超过去重窗口
    print("等待 2.1 秒...")
    await asyncio.sleep(2.1)
    
    # 再次提交（应该被接受）
    result3 = manager._should_submit(text)
    print(f"2秒后再次提交 '{text}': {result3}")
    
    if result1 and not result2 and result3:
        print("✅ 去重机制工作正常")
    else:
        print("❌ 去重机制异常")
    
    print()


async def test_emotion_parsing():
    """测试情绪解析"""
    print("=" * 60)
    print("测试 5: 情绪解析")
    print("=" * 60)
    
    config = ConversationConfig(use_text_input=True)
    manager = AsyncConversationManager(config)
    
    test_cases = [
        ("[joy]你好！", "你好！", "joy"),
        ("我很开心[joy]今天天气真好", "我很开心今天天气真好", "joy"),
        ("普通文本", "普通文本", None),
        ("[anger]我很生气[joy]但是现在开心了", "我很生气但是现在开心了", "anger"),  # 取第一个
    ]
    
    for text, expected_clean, expected_emotion in test_cases:
        clean, emotion = manager._strip_emotion_tags(text)
        if clean == expected_clean and (expected_emotion is None or emotion == expected_emotion):
            print(f"✅ '{text[:30]}...' → '{clean[:30]}...' ({emotion})")
        else:
            print(f"❌ '{text[:30]}...'")
            print(f"   期望: '{expected_clean}' ({expected_emotion})")
            print(f"   实际: '{clean}' ({emotion})")
    
    print()


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("异步对话管理器测试套件")
    print("=" * 60 + "\n")
    
    try:
        # 基础测试
        test_basic()
        
        # 异步测试
        await test_turn_management()
        await test_sentence_splitting()
        await test_dedup()
        await test_emotion_parsing()
        
        print("=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
