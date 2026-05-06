#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：验证 ContextManager.switch_user 功能
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from backend.llm.memory.context_manager import ContextManager


def test_switch_user():
    """测试用户切换功能"""
    print("=" * 60)
    print("测试 ContextManager.switch_user 功能")
    print("=" * 60)
    
    # 1. 创建 ContextManager 实例
    print("\n1. 创建 ContextManager (user_id='user_1')")
    ctx = ContextManager(user_id="user_1")
    print(f"   当前用户: {ctx.user_id}")
    
    # 2. 启动会话
    print("\n2. 启动会话")
    session_id = ctx.start_session()
    print(f"   会话 ID: {session_id}")
    
    # 3. 添加消息
    print("\n3. 添加用户消息")
    ctx.add_user_message("你好，我是用户1")
    ctx.add_assistant_message("你好！很高兴见到你。")
    print("   消息已添加")
    
    # 4. 获取会话信息
    print("\n4. 获取会话信息")
    info = ctx.get_session_info()
    print(f"   会话状态: {info['status']}")
    print(f"   消息数量: {info['message_count']}")
    
    # 5. 切换到新用户
    print("\n5. 切换到新用户 (user_id='user_2')")
    success = ctx.switch_user("user_2")
    print(f"   切换成功: {success}")
    print(f"   当前用户: {ctx.user_id}")
    print(f"   当前会话 ID: {ctx.session_id}")
    
    # 6. 验证新会话
    print("\n6. 验证新会话")
    new_info = ctx.get_session_info()
    print(f"   会话状态: {new_info['status']}")
    print(f"   消息数量: {new_info['message_count']}")
    
    # 7. 测试相同用户切换（应该直接返回 True）
    print("\n7. 测试切换到相同用户")
    success = ctx.switch_user("user_2")
    print(f"   切换成功: {success}")
    print(f"   当前用户: {ctx.user_id}")
    
    # 8. 测试带说话人标记的消息
    print("\n8. 测试添加带说话人标记的消息")
    ctx.add_user_message_with_speaker("这是用户2的消息", "speaker_002")
    print("   消息已添加")
    
    # 9. 测试按说话人过滤历史
    print("\n9. 测试按说话人过滤历史")
    history = ctx.get_history_by_speaker("speaker_002")
    print(f"   找到 {len(history)} 条消息")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_switch_user_methods():
    """测试所有新增方法"""
    print("\n" + "=" * 60)
    print("测试所有新增方法")
    print("=" * 60)
    
    ctx = ContextManager(user_id="test_user")
    
    # 测试 switch_user
    print("\n✓ switch_user 方法存在")
    assert hasattr(ctx, 'switch_user'), "switch_user 方法不存在"
    
    # 测试 add_user_message_with_speaker
    print("✓ add_user_message_with_speaker 方法存在")
    assert hasattr(ctx, 'add_user_message_with_speaker'), "add_user_message_with_speaker 方法不存在"
    
    # 测试 get_history_by_speaker
    print("✓ get_history_by_speaker 方法存在")
    assert hasattr(ctx, 'get_history_by_speaker'), "get_history_by_speaker 方法不存在"
    
    print("\n所有方法验证通过！")


if __name__ == "__main__":
    try:
        # 先验证方法存在
        test_switch_user_methods()
        
        # 再进行功能测试
        test_switch_user()
        
        print("\n✅ 所有测试通过！")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
