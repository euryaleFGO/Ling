#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试性能监控功能

使用方式:
    python scripts/test_performance_monitoring.py
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
)


async def test_performance_monitoring():
    """测试性能监控"""
    print("\n" + "=" * 60)
    print("测试性能监控功能")
    print("=" * 60)
    
    config = ConversationConfig(
        use_text_input=True,
        enable_barge_in=True,
    )
    
    manager = AsyncConversationManager(config)
    manager._init_audio()
    
    # 模拟多次对话
    print("\n模拟 5 次对话...")
    for i in range(5):
        print(f"\n--- Turn {i+1} ---")
        manager.run_turn(f"测试消息 {i+1}")
        
        # 等待一会儿
        await asyncio.sleep(0.2)
        
        # 随机打断一些
        if i % 2 == 0:
            print("  [打断]")
            await manager.cancel_current_turn()
        else:
            # 等待完成
            if manager._current_turn:
                try:
                    await asyncio.wait_for(manager._current_turn, timeout=1.0)
                except asyncio.TimeoutError:
                    pass
    
    # 打印性能统计
    print("\n" + "=" * 60)
    print("性能统计结果")
    print("=" * 60)
    
    manager.print_performance_stats()
    
    # 获取详细统计
    stats = manager.get_performance_stats()
    
    print("\n详细统计:")
    print(f"  - 总对话轮次: {stats['total_turns']}")
    print(f"  - 总打断次数: {stats['total_interrupts']}")
    
    if stats.get('turn'):
        turn_stats = stats['turn']
        print(f"\nTurn 性能:")
        print(f"  - 平均总延迟: {turn_stats['total_latency']['avg']:.1f}ms")
        print(f"  - P95 总延迟: {turn_stats['total_latency']['p95']:.1f}ms")
        print(f"  - 打断率: {turn_stats['interrupt_rate']*100:.1f}%")
    
    if stats.get('interrupt'):
        interrupt_stats = stats['interrupt']
        print(f"\n打断性能:")
        print(f"  - 平均响应时间: {interrupt_stats['response_time']['avg']:.1f}ms")
        print(f"  - P95 响应时间: {interrupt_stats['response_time']['p95']:.1f}ms")
    
    print("\n✅ 性能监控测试完成")


async def test_performance_reset():
    """测试性能统计重置"""
    print("\n" + "=" * 60)
    print("测试性能统计重置")
    print("=" * 60)
    
    config = ConversationConfig(use_text_input=True)
    manager = AsyncConversationManager(config)
    manager._init_audio()
    
    # 模拟一些对话
    print("\n模拟 3 次对话...")
    for i in range(3):
        manager.run_turn(f"测试 {i+1}")
        await asyncio.sleep(0.1)
        if manager._current_turn:
            try:
                await asyncio.wait_for(manager._current_turn, timeout=0.5)
            except asyncio.TimeoutError:
                pass
    
    stats_before = manager.get_performance_stats()
    print(f"\n重置前: {stats_before['total_turns']} 轮对话")
    
    # 重置统计
    manager.reset_performance_stats()
    
    stats_after = manager.get_performance_stats()
    print(f"重置后: {stats_after['total_turns']} 轮对话")
    
    if stats_after['total_turns'] == 0:
        print("\n✅ 性能统计重置成功")
    else:
        print("\n❌ 性能统计重置失败")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("性能监控测试套件")
    print("=" * 60)
    
    try:
        await test_performance_monitoring()
        await test_performance_reset()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
