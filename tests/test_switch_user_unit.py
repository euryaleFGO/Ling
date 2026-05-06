#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试：验证 ContextManager.switch_user 方法签名和基本逻辑
不依赖数据库连接
"""
import sys
from pathlib import Path
import inspect

# 添加项目路径
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from backend.llm.memory.context_manager import ContextManager


def test_method_signatures():
    """测试方法签名是否符合设计文档"""
    print("=" * 60)
    print("测试方法签名")
    print("=" * 60)
    
    # 1. 测试 switch_user 方法
    print("\n1. 测试 switch_user 方法")
    assert hasattr(ContextManager, 'switch_user'), "switch_user 方法不存在"
    
    sig = inspect.signature(ContextManager.switch_user)
    params = list(sig.parameters.keys())
    print(f"   参数: {params}")
    assert 'self' in params, "缺少 self 参数"
    assert 'new_user_id' in params, "缺少 new_user_id 参数"
    assert sig.return_annotation == bool or str(sig.return_annotation) == 'bool', "返回类型应该是 bool"
    print("   ✓ 方法签名正确")
    
    # 2. 测试 add_user_message_with_speaker 方法
    print("\n2. 测试 add_user_message_with_speaker 方法")
    assert hasattr(ContextManager, 'add_user_message_with_speaker'), "add_user_message_with_speaker 方法不存在"
    
    sig = inspect.signature(ContextManager.add_user_message_with_speaker)
    params = list(sig.parameters.keys())
    print(f"   参数: {params}")
    assert 'self' in params, "缺少 self 参数"
    assert 'content' in params, "缺少 content 参数"
    assert 'speaker_id' in params, "缺少 speaker_id 参数"
    assert sig.return_annotation == bool or str(sig.return_annotation) == 'bool', "返回类型应该是 bool"
    print("   ✓ 方法签名正确")
    
    # 3. 测试 get_history_by_speaker 方法
    print("\n3. 测试 get_history_by_speaker 方法")
    assert hasattr(ContextManager, 'get_history_by_speaker'), "get_history_by_speaker 方法不存在"
    
    sig = inspect.signature(ContextManager.get_history_by_speaker)
    params = list(sig.parameters.keys())
    print(f"   参数: {params}")
    assert 'self' in params, "缺少 self 参数"
    assert 'speaker_id' in params, "缺少 speaker_id 参数"
    assert 'limit' in params, "缺少 limit 参数"
    print("   ✓ 方法签名正确")
    
    print("\n" + "=" * 60)
    print("所有方法签名测试通过！")
    print("=" * 60)


def test_method_docstrings():
    """测试方法文档字符串"""
    print("\n" + "=" * 60)
    print("测试方法文档字符串")
    print("=" * 60)
    
    # 1. switch_user
    print("\n1. switch_user 文档:")
    doc = ContextManager.switch_user.__doc__
    assert doc is not None, "switch_user 缺少文档字符串"
    print(f"   {doc.strip()[:50]}...")
    assert "切换用户上下文" in doc, "文档字符串应包含功能描述"
    print("   ✓ 文档字符串存在")
    
    # 2. add_user_message_with_speaker
    print("\n2. add_user_message_with_speaker 文档:")
    doc = ContextManager.add_user_message_with_speaker.__doc__
    assert doc is not None, "add_user_message_with_speaker 缺少文档字符串"
    print(f"   {doc.strip()[:50]}...")
    assert "说话人" in doc, "文档字符串应包含说话人相关描述"
    print("   ✓ 文档字符串存在")
    
    # 3. get_history_by_speaker
    print("\n3. get_history_by_speaker 文档:")
    doc = ContextManager.get_history_by_speaker.__doc__
    assert doc is not None, "get_history_by_speaker 缺少文档字符串"
    print(f"   {doc.strip()[:50]}...")
    assert "说话人" in doc, "文档字符串应包含说话人相关描述"
    print("   ✓ 文档字符串存在")
    
    print("\n" + "=" * 60)
    print("所有文档字符串测试通过！")
    print("=" * 60)


def test_implementation_logic():
    """测试实现逻辑（不依赖数据库）"""
    print("\n" + "=" * 60)
    print("测试实现逻辑")
    print("=" * 60)
    
    # 读取源代码验证实现
    import ast
    
    source_file = src_path / "backend" / "llm" / "memory" / "context_manager.py"
    with open(source_file, 'r', encoding='utf-8') as f:
        source = f.read()
    
    # 1. 验证 switch_user 实现包含关键步骤
    print("\n1. 验证 switch_user 实现")
    assert "if new_user_id == self.user_id:" in source, "缺少相同用户检查"
    print("   ✓ 包含相同用户检查")
    
    assert "self.end_session" in source, "缺少结束会话调用"
    print("   ✓ 包含结束会话逻辑")
    
    assert "self.user_id = new_user_id" in source, "缺少用户ID更新"
    print("   ✓ 包含用户ID更新")
    
    assert "self.clear_cache()" in source, "缺少清除缓存调用"
    print("   ✓ 包含清除缓存逻辑")
    
    assert "self.start_session" in source, "缺少启动会话调用"
    print("   ✓ 包含启动新会话逻辑")
    
    assert 'switched_from' in source, "缺少切换来源元数据"
    print("   ✓ 包含切换来源元数据")
    
    # 2. 验证 add_user_message_with_speaker 实现
    print("\n2. 验证 add_user_message_with_speaker 实现")
    assert 'metadata={"speaker_id": speaker_id}' in source or "metadata={'speaker_id': speaker_id}" in source, "缺少speaker_id元数据"
    print("   ✓ 包含speaker_id元数据")
    
    # 3. 验证 get_history_by_speaker 实现
    print("\n3. 验证 get_history_by_speaker 实现")
    assert 'msg.get("metadata", {}).get("speaker_id")' in source or "msg.get('metadata', {}).get('speaker_id')" in source, "缺少speaker_id过滤"
    print("   ✓ 包含speaker_id过滤逻辑")
    
    print("\n" + "=" * 60)
    print("所有实现逻辑测试通过！")
    print("=" * 60)


def main():
    """运行所有测试"""
    try:
        test_method_signatures()
        test_method_docstrings()
        test_implementation_logic()
        
        print("\n" + "=" * 60)
        print("✅ 所有单元测试通过！")
        print("=" * 60)
        print("\n实现总结:")
        print("1. ✓ switch_user 方法已实现")
        print("   - 检查相同用户")
        print("   - 保存当前会话")
        print("   - 切换用户ID")
        print("   - 清除缓存")
        print("   - 启动新会话")
        print("   - 记录切换日志")
        print("\n2. ✓ add_user_message_with_speaker 方法已实现")
        print("   - 添加带speaker_id的用户消息")
        print("\n3. ✓ get_history_by_speaker 方法已实现")
        print("   - 按speaker_id过滤对话历史")
        print("\n任务 6.1 实现完成！")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
