#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 TTS 缓存功能

使用方式:
    python scripts/test_tts_cache.py
"""

import sys
import time
from pathlib import Path
import numpy as np

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core.tts_cache import TTSCache


def test_basic_cache():
    """测试基础缓存功能"""
    print("\n" + "=" * 60)
    print("测试 1: 基础缓存功能")
    print("=" * 60)
    
    cache = TTSCache(max_size=10)
    
    # 模拟音频数据
    audio1 = np.random.randn(16000).astype(np.float32)
    audio2 = np.random.randn(16000).astype(np.float32)
    
    # 测试 put 和 get
    cache.put("你好", audio1, 16000)
    cache.put("再见", audio2, 16000)
    
    # 测试命中
    result1 = cache.get("你好")
    if result1 is not None:
        print("✅ 缓存命中: 你好")
    else:
        print("❌ 缓存未命中: 你好")
    
    # 测试未命中
    result3 = cache.get("不存在的文本")
    if result3 is None:
        print("✅ 缓存正确未命中: 不存在的文本")
    else:
        print("❌ 缓存错误命中: 不存在的文本")
    
    # 打印统计
    cache.print_stats()


def test_lru_eviction():
    """测试 LRU 淘汰策略"""
    print("\n" + "=" * 60)
    print("测试 2: LRU 淘汰策略")
    print("=" * 60)
    
    cache = TTSCache(max_size=3)
    
    # 添加 4 个项目
    for i in range(4):
        audio = np.random.randn(16000).astype(np.float32)
        cache.put(f"文本{i}", audio, 16000)
        print(f"添加: 文本{i}")
    
    # 检查最旧的项目是否被淘汰
    result0 = cache.get("文本0")
    if result0 is None:
        print("✅ LRU 淘汰正确: 文本0 已被淘汰")
    else:
        print("❌ LRU 淘汰错误: 文本0 仍在缓存中")
    
    # 检查其他项目是否还在
    for i in range(1, 4):
        result = cache.get(f"文本{i}")
        if result is not None:
            print(f"✅ 文本{i} 仍在缓存中")
        else:
            print(f"❌ 文本{i} 不在缓存中")
    
    cache.print_stats()


def test_cache_hit_rate():
    """测试缓存命中率"""
    print("\n" + "=" * 60)
    print("测试 3: 缓存命中率")
    print("=" * 60)
    
    cache = TTSCache(max_size=5)
    
    # 添加一些常用短语
    common_phrases = ["好的", "明白了", "收到", "没问题", "可以"]
    for phrase in common_phrases:
        audio = np.random.randn(8000).astype(np.float32)
        cache.put(phrase, audio, 16000)
    
    # 模拟多次请求
    requests = ["好的"] * 10 + ["明白了"] * 8 + ["收到"] * 6 + ["新短语"] * 5
    
    print(f"\n模拟 {len(requests)} 次请求...")
    for phrase in requests:
        cache.get(phrase)
    
    # 打印统计
    stats = cache.get_stats()
    print(f"\n统计结果:")
    print(f"  - 总请求: {stats['total_requests']}")
    print(f"  - 命中: {stats['hits']}")
    print(f"  - 未命中: {stats['misses']}")
    print(f"  - 命中率: {stats['hit_rate']*100:.1f}%")
    
    if stats['hit_rate'] > 0.8:
        print("\n✅ 缓存命中率良好 (>80%)")
    else:
        print(f"\n⚠️  缓存命中率较低 ({stats['hit_rate']*100:.1f}%)")


def test_cache_with_spk_id():
    """测试带说话人 ID 的缓存"""
    print("\n" + "=" * 60)
    print("测试 4: 带说话人 ID 的缓存")
    print("=" * 60)
    
    cache = TTSCache(max_size=10)
    
    # 同一文本，不同说话人
    audio1 = np.random.randn(16000).astype(np.float32)
    audio2 = np.random.randn(16000).astype(np.float32)
    
    cache.put("你好", audio1, 16000, spk_id="speaker1")
    cache.put("你好", audio2, 16000, spk_id="speaker2")
    
    # 测试不同说话人的缓存
    result1 = cache.get("你好", spk_id="speaker1")
    result2 = cache.get("你好", spk_id="speaker2")
    
    if result1 is not None and result2 is not None:
        print("✅ 不同说话人的缓存正确分离")
        # 验证音频数据不同
        if not np.array_equal(result1[0], result2[0]):
            print("✅ 不同说话人的音频数据不同")
        else:
            print("❌ 不同说话人的音频数据相同")
    else:
        print("❌ 缓存未正确分离不同说话人")
    
    cache.print_stats()


def test_cache_performance():
    """测试缓存性能"""
    print("\n" + "=" * 60)
    print("测试 5: 缓存性能")
    print("=" * 60)
    
    cache = TTSCache(max_size=100)
    
    # 添加 100 个项目
    print("\n添加 100 个项目...")
    t0 = time.monotonic()
    for i in range(100):
        audio = np.random.randn(16000).astype(np.float32)
        cache.put(f"文本{i}", audio, 16000)
    t1 = time.monotonic()
    
    add_time = (t1 - t0) * 1000
    print(f"  - 总时间: {add_time:.2f}ms")
    print(f"  - 平均每项: {add_time/100:.3f}ms")
    
    # 测试查询性能
    print("\n查询 1000 次...")
    t0 = time.monotonic()
    for i in range(1000):
        cache.get(f"文本{i % 100}")
    t1 = time.monotonic()
    
    query_time = (t1 - t0) * 1000
    print(f"  - 总时间: {query_time:.2f}ms")
    print(f"  - 平均每次: {query_time/1000:.3f}ms")
    
    if query_time / 1000 < 0.1:
        print("\n✅ 查询性能良好 (<0.1ms/次)")
    else:
        print(f"\n⚠️  查询性能较慢 ({query_time/1000:.3f}ms/次)")
    
    cache.print_stats()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("TTS 缓存测试套件")
    print("=" * 60)
    
    try:
        test_basic_cache()
        test_lru_eviction()
        test_cache_hit_rate()
        test_cache_with_spk_id()
        test_cache_performance()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
