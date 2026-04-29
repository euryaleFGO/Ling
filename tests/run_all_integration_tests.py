"""
集成测试运行器

运行所有集成测试并生成测试报告
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 导入测试类
from tests.integration.test_e2e_interrupt_flow import TestE2EInterruptFlow
from tests.integration.test_performance_benchmarks import TestPerformanceBenchmarks
from tests.integration.test_error_handling import TestErrorHandling
from tests.integration.test_stress import TestStress


class IntegrationTestRunner:
    """集成测试运行器"""
    
    def __init__(self):
        self.all_results = {}
        self.start_time = None
        self.end_time = None
        
    async def run_all_tests(self):
        """运行所有集成测试"""
        print("\n" + "="*70)
        print(" " * 20 + "集成测试套件")
        print("="*70)
        print(f"\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.start_time = time.monotonic()
        
        # 1. 端到端打断流程测试
        print("\n" + "="*70)
        print("测试套件 1/4: 端到端打断流程测试")
        print("="*70)
        e2e_tester = TestE2EInterruptFlow()
        await e2e_tester.run_all_tests()
        self.all_results["e2e_interrupt_flow"] = e2e_tester.test_results
        
        # 2. 性能基准测试
        print("\n" + "="*70)
        print("测试套件 2/4: 性能基准测试")
        print("="*70)
        perf_tester = TestPerformanceBenchmarks()
        await perf_tester.run_all_tests()
        self.all_results["performance_benchmarks"] = perf_tester.test_results
        
        # 3. 错误处理和降级测试
        print("\n" + "="*70)
        print("测试套件 3/4: 错误处理和降级测试")
        print("="*70)
        error_tester = TestErrorHandling()
        await error_tester.run_all_tests()
        self.all_results["error_handling"] = error_tester.test_results
        
        # 4. 压力测试
        print("\n" + "="*70)
        print("测试套件 4/4: 压力测试")
        print("="*70)
        stress_tester = TestStress()
        await stress_tester.run_all_tests()
        self.all_results["stress"] = stress_tester.test_results
        
        self.end_time = time.monotonic()
        
        # 打印总结
        self.print_final_summary()
        
        # 生成测试报告
        self.generate_report()
    
    def print_final_summary(self):
        """打印最终测试摘要"""
        print("\n" + "="*70)
        print(" " * 20 + "最终测试摘要")
        print("="*70)
        
        total_duration = self.end_time - self.start_time
        
        # 统计所有测试结果
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        total_errors = 0
        
        for suite_name, results in self.all_results.items():
            for result in results:
                total_tests += 1
                status = result.get("status", "UNKNOWN")
                if status == "PASS":
                    total_passed += 1
                elif status == "FAIL":
                    total_failed += 1
                elif status == "SKIP":
                    total_skipped += 1
                elif status == "ERROR":
                    total_errors += 1
        
        # 打印统计
        print(f"\n总测试数: {total_tests}")
        print(f"通过: {total_passed} ({total_passed/total_tests*100:.1f}%)")
        print(f"失败: {total_failed} ({total_failed/total_tests*100:.1f}%)")
        print(f"跳过: {total_skipped} ({total_skipped/total_tests*100:.1f}%)")
        print(f"错误: {total_errors} ({total_errors/total_tests*100:.1f}%)")
        print(f"\n总耗时: {total_duration:.2f}秒")
        
        # 按测试套件打印结果
        print("\n按测试套件分类:")
        suite_names = {
            "e2e_interrupt_flow": "端到端打断流程",
            "performance_benchmarks": "性能基准测试",
            "error_handling": "错误处理和降级",
            "stress": "压力测试",
        }
        
        for suite_id, suite_name in suite_names.items():
            results = self.all_results.get(suite_id, [])
            passed = sum(1 for r in results if r.get("status") == "PASS")
            total = len(results)
            status_icon = "✅" if passed == total else "❌"
            print(f"  {status_icon} {suite_name}: {passed}/{total} 通过")
        
        # 最终结论
        if total_failed == 0 and total_errors == 0:
            print("\n" + "="*70)
            print("✅ 所有集成测试通过！系统已准备好生产部署。")
            print("="*70)
        else:
            print("\n" + "="*70)
            print(f"❌ {total_failed + total_errors} 个测试失败或出错，需要修复。")
            print("="*70)
    
    def generate_report(self):
        """生成测试报告"""
        report_dir = "tests/reports"
        os.makedirs(report_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(report_dir, f"integration_test_report_{timestamp}.json")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": self.end_time - self.start_time,
            "results": self.all_results,
            "summary": self._generate_summary_dict(),
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n测试报告已保存到: {report_file}")
    
    def _generate_summary_dict(self) -> dict:
        """生成摘要字典"""
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        total_errors = 0
        
        for results in self.all_results.values():
            for result in results:
                total_tests += 1
                status = result.get("status", "UNKNOWN")
                if status == "PASS":
                    total_passed += 1
                elif status == "FAIL":
                    total_failed += 1
                elif status == "SKIP":
                    total_skipped += 1
                elif status == "ERROR":
                    total_errors += 1
        
        return {
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "errors": total_errors,
            "pass_rate": total_passed / total_tests * 100 if total_tests > 0 else 0,
        }


async def main():
    """主函数"""
    runner = IntegrationTestRunner()
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
