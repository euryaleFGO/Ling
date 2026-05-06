"""
测试性能分析工具

验证：
1. 硬件检测
2. 瓶颈识别
3. 推荐配置生成
4. 性能报告生成
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core.performance_analyzer import PerformanceAnalyzer, Severity


def test_hardware_detection():
    """测试硬件检测"""
    print("\n" + "=" * 60)
    print("测试 1: 硬件检测")
    print("=" * 60)
    
    try:
        analyzer = PerformanceAnalyzer()
        hw = analyzer.hardware_info
        
        print(f"  ✓ CPU 核心数: {hw.cpu_count}")
        print(f"  ✓ CUDA 可用: {hw.has_cuda}")
        print(f"  ✓ GPU 数量: {hw.cuda_device_count}")
        print(f"  ✓ 内存: {hw.total_memory_gb:.1f} GB")
        print(f"  ✓ 平台: {hw.platform}")
        
        print("\n  ✅ 测试通过：硬件检测成功")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_bottleneck_detection():
    """测试瓶颈识别"""
    print("\n" + "=" * 60)
    print("测试 2: 瓶颈识别")
    print("=" * 60)
    
    try:
        analyzer = PerformanceAnalyzer()
        
        # 模拟性能数据（有瓶颈）
        stats = {
            "overall": {
                "total_turns": 10,
                "total_interrupts": 3,
            },
            "asr": {
                "first_chunk_latency": {
                    "avg": 150.0,
                    "p95": 200.0,
                },
                "rtf": {
                    "avg": 0.6,
                },
            },
            "tts": {
                "first_chunk_latency": {
                    "avg": 400.0,
                    "p95": 600.0,
                },
                "rtf": {
                    "avg": 0.8,
                },
            },
            "turn": {
                "llm_first_token": {
                    "avg": 1200.0,
                    "p95": 1500.0,
                },
                "total_latency": {
                    "avg": 2500.0,
                    "p95": 3000.0,
                },
            },
            "interrupt": {
                "response_time": {
                    "avg": 150.0,
                    "p95": 250.0,
                },
            },
        }
        
        report = analyzer.analyze(stats)
        
        print(f"  ✓ 检测到 {len(report.bottlenecks)} 个瓶颈")
        
        # 验证瓶颈类型
        bottleneck_types = set(b.type.value for b in report.bottlenecks)
        print(f"  ✓ 瓶颈类型: {', '.join(bottleneck_types)}")
        
        # 验证严重程度
        critical = sum(1 for b in report.bottlenecks if b.severity == Severity.CRITICAL)
        high = sum(1 for b in report.bottlenecks if b.severity == Severity.HIGH)
        medium = sum(1 for b in report.bottlenecks if b.severity == Severity.MEDIUM)
        
        print(f"  ✓ 严重瓶颈: {critical} 个")
        print(f"  ✓ 高优先级: {high} 个")
        print(f"  ✓ 中优先级: {medium} 个")
        
        # 验证建议
        total_suggestions = sum(len(b.suggestions) for b in report.bottlenecks)
        print(f"  ✓ 优化建议: {total_suggestions} 条")
        
        print("\n  ✅ 测试通过：瓶颈识别正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_recommended_config():
    """测试推荐配置生成"""
    print("\n" + "=" * 60)
    print("测试 3: 推荐配置生成")
    print("=" * 60)
    
    try:
        analyzer = PerformanceAnalyzer()
        
        # 模拟性能数据
        stats = {
            "asr": {
                "first_chunk_latency": {
                    "avg": 150.0,
                    "p95": 200.0,
                },
            },
            "tts": {
                "first_chunk_latency": {
                    "avg": 400.0,
                    "p95": 600.0,
                },
            },
        }
        
        report = analyzer.analyze(stats)
        
        print(f"  ✓ 生成推荐配置")
        
        # 验证配置结构
        assert "asr" in report.recommended_config, "缺少 ASR 配置"
        assert "tts" in report.recommended_config, "缺少 TTS 配置"
        
        print(f"  ✓ ASR 配置: {report.recommended_config['asr']}")
        print(f"  ✓ TTS 配置: {report.recommended_config['tts']}")
        
        # 验证配置合理性
        asr_config = report.recommended_config["asr"]
        assert "device" in asr_config, "缺少 device 配置"
        assert "stream_profile" in asr_config, "缺少 stream_profile 配置"
        
        tts_config = report.recommended_config["tts"]
        assert "enable_cache" in tts_config, "缺少 enable_cache 配置"
        assert "cache_size" in tts_config, "缺少 cache_size 配置"
        
        print("\n  ✅ 测试通过：推荐配置生成正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_report_generation():
    """测试性能报告生成"""
    print("\n" + "=" * 60)
    print("测试 4: 性能报告生成")
    print("=" * 60)
    
    try:
        analyzer = PerformanceAnalyzer()
        
        # 模拟性能数据
        stats = {
            "overall": {
                "total_turns": 10,
                "total_interrupts": 3,
            },
            "asr": {
                "first_chunk_latency": {
                    "avg": 150.0,
                    "p95": 200.0,
                },
            },
            "tts": {
                "first_chunk_latency": {
                    "avg": 400.0,
                    "p95": 600.0,
                },
            },
        }
        
        report = analyzer.analyze(stats)
        
        # 验证报告内容
        assert report.summary, "缺少总结"
        assert report.hardware_info, "缺少硬件信息"
        assert report.recommended_config, "缺少推荐配置"
        
        print("  ✓ 报告总结:")
        for line in report.summary.split('\n')[:5]:
            print(f"    {line}")
        print("    ...")
        
        # 打印完整报告
        print("\n  ✓ 完整报告:")
        analyzer.print_report(report)
        
        # 导出报告
        output_path = project_root / "test_performance_report.json"
        analyzer.export_report(report, str(output_path))
        print(f"  ✓ 报告已导出到: {output_path}")
        
        # 清理
        output_path.unlink()
        print("  ✓ 临时文件已清理")
        
        print("\n  ✅ 测试通过：性能报告生成正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_no_bottlenecks():
    """测试无瓶颈场景"""
    print("\n" + "=" * 60)
    print("测试 5: 无瓶颈场景")
    print("=" * 60)
    
    try:
        analyzer = PerformanceAnalyzer()
        
        # 模拟良好的性能数据
        stats = {
            "overall": {
                "total_turns": 10,
                "total_interrupts": 2,
            },
            "asr": {
                "first_chunk_latency": {
                    "avg": 50.0,
                    "p95": 80.0,
                },
                "rtf": {
                    "avg": 0.2,
                },
            },
            "tts": {
                "first_chunk_latency": {
                    "avg": 150.0,
                    "p95": 180.0,
                },
                "rtf": {
                    "avg": 0.3,
                },
            },
            "turn": {
                "llm_first_token": {
                    "avg": 800.0,
                    "p95": 950.0,
                },
                "total_latency": {
                    "avg": 1500.0,
                    "p95": 1800.0,
                },
            },
            "interrupt": {
                "response_time": {
                    "avg": 50.0,
                    "p95": 80.0,
                },
            },
        }
        
        report = analyzer.analyze(stats)
        
        # 验证无严重瓶颈
        critical = sum(1 for b in report.bottlenecks if b.severity == Severity.CRITICAL)
        high = sum(1 for b in report.bottlenecks if b.severity == Severity.HIGH)
        
        print(f"  ✓ 严重瓶颈: {critical} 个")
        print(f"  ✓ 高优先级瓶颈: {high} 个")
        print(f"  ✓ 总瓶颈数: {len(report.bottlenecks)} 个")
        
        if critical == 0 and high == 0:
            print("  ✓ 性能良好，无严重瓶颈")
        
        print("\n  ✅ 测试通过：无瓶颈场景正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("性能分析工具测试")
    print("=" * 60)
    
    results = []
    
    # 测试 1
    try:
        results.append(("硬件检测", test_hardware_detection()))
    except Exception as e:
        print(f"\n测试 1 异常: {e}")
        results.append(("硬件检测", False))
    
    # 测试 2
    try:
        results.append(("瓶颈识别", test_bottleneck_detection()))
    except Exception as e:
        print(f"\n测试 2 异常: {e}")
        results.append(("瓶颈识别", False))
    
    # 测试 3
    try:
        results.append(("推荐配置生成", test_recommended_config()))
    except Exception as e:
        print(f"\n测试 3 异常: {e}")
        results.append(("推荐配置生成", False))
    
    # 测试 4
    try:
        results.append(("性能报告生成", test_report_generation()))
    except Exception as e:
        print(f"\n测试 4 异常: {e}")
        results.append(("性能报告生成", False))
    
    # 测试 5
    try:
        results.append(("无瓶颈场景", test_no_bottlenecks()))
    except Exception as e:
        print(f"\n测试 5 异常: {e}")
        results.append(("无瓶颈场景", False))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n✅ 所有测试通过！")
    else:
        print("\n❌ 部分测试失败")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
