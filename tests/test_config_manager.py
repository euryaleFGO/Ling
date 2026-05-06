"""
测试配置管理器

验证：
1. 配置文件加载
2. 配置参数验证
3. 配置保存
4. 配置热更新检测
"""

import sys
import time
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core.config_manager import ConfigManager, SystemConfig


def test_load_config():
    """测试配置加载"""
    print("\n" + "=" * 60)
    print("测试 1: 配置文件加载")
    print("=" * 60)
    
    try:
        manager = ConfigManager()
        config = manager.load()
        
        print(f"  ✓ 配置版本: {config.version}")
        print(f"  ✓ ASR 配置: provider={config.asr.provider}, profile={config.asr.stream_profile}")
        print(f"  ✓ TTS 配置: cache={config.tts.enable_cache}, size={config.tts.cache_size}")
        print(f"  ✓ 打断配置: enabled={config.interrupt.enable_barge_in}, mode={config.interrupt.context_mode}")
        print(f"  ✓ 音频配置: vad={config.audio.vad_backend}, preset={config.audio.vad_preset}")
        
        print("\n  ✅ 测试通过：配置文件加载成功")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_validate_config():
    """测试配置验证"""
    print("\n" + "=" * 60)
    print("测试 2: 配置参数验证")
    print("=" * 60)
    
    try:
        manager = ConfigManager()
        config = manager.load()
        
        # 测试有效配置
        print("  ✓ 有效配置验证通过")
        
        # 测试无效配置
        config.asr.stream_profile = "invalid"
        try:
            manager._validate_config()
            print("  ✗ 应该抛出验证错误")
            return False
        except ValueError as e:
            print(f"  ✓ 正确捕获无效配置: {str(e)[:50]}...")
        
        # 恢复有效配置
        config.asr.stream_profile = "balanced"
        manager._validate_config()
        print("  ✓ 恢复有效配置成功")
        
        print("\n  ✅ 测试通过：配置验证正常工作")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_save_config():
    """测试配置保存"""
    print("\n" + "=" * 60)
    print("测试 3: 配置保存")
    print("=" * 60)
    
    try:
        # 创建临时配置文件
        temp_config_path = project_root / "config" / "test_config.json"
        
        manager = ConfigManager(str(temp_config_path))
        config = manager.load()
        
        # 修改配置
        config.asr.stream_profile = "low_latency"
        config.tts.cache_size = 200
        config.interrupt.context_mode = "continue"
        
        # 保存配置
        manager.save(config)
        print("  ✓ 配置保存成功")
        
        # 重新加载验证
        manager2 = ConfigManager(str(temp_config_path))
        config2 = manager2.load()
        
        assert config2.asr.stream_profile == "low_latency", "ASR profile 不匹配"
        assert config2.tts.cache_size == 200, "TTS cache size 不匹配"
        assert config2.interrupt.context_mode == "continue", "Interrupt mode 不匹配"
        
        print("  ✓ 配置重新加载验证成功")
        
        # 清理临时文件
        temp_config_path.unlink()
        print("  ✓ 临时文件清理完成")
        
        print("\n  ✅ 测试通过：配置保存和加载正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_hot_reload():
    """测试配置热更新检测"""
    print("\n" + "=" * 60)
    print("测试 4: 配置热更新检测")
    print("=" * 60)
    
    try:
        # 创建临时配置文件
        temp_config_path = project_root / "config" / "test_hot_reload.json"
        
        manager = ConfigManager(str(temp_config_path))
        config = manager.load()
        manager.save(config)
        
        print("  ✓ 初始配置已保存")
        
        # 检查更新（应该没有）
        has_update = manager.check_for_updates()
        assert not has_update, "不应该检测到更新"
        print("  ✓ 未检测到更新（正确）")
        
        # 等待一秒后修改文件
        time.sleep(1.1)
        
        # 修改配置文件
        with open(temp_config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        data['asr']['stream_profile'] = 'accuracy'
        
        with open(temp_config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        print("  ✓ 配置文件已修改")
        
        # 检查更新（应该有）
        has_update = manager.check_for_updates()
        assert has_update, "应该检测到更新"
        print("  ✓ 检测到更新（正确）")
        
        # 重新加载
        reloaded = manager.reload_if_changed()
        assert reloaded, "应该重新加载配置"
        assert manager.config.asr.stream_profile == "accuracy", "配置未更新"
        print("  ✓ 配置已重新加载")
        
        # 清理临时文件
        temp_config_path.unlink()
        print("  ✓ 临时文件清理完成")
        
        print("\n  ✅ 测试通过：配置热更新检测正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_default_config():
    """测试默认配置"""
    print("\n" + "=" * 60)
    print("测试 5: 默认配置")
    print("=" * 60)
    
    try:
        # 使用不存在的配置文件
        manager = ConfigManager("/nonexistent/config.json")
        config = manager.load()
        
        # 验证默认值
        assert config.version == "1.0.0", "默认版本不正确"
        assert config.asr.provider == "funasr", "默认 ASR provider 不正确"
        assert config.tts.enable_cache == True, "默认 TTS cache 不正确"
        assert config.interrupt.enable_barge_in == True, "默认打断配置不正确"
        
        print("  ✓ 默认配置值正确")
        print("\n  ✅ 测试通过：默认配置正常")
        return True
    except Exception as e:
        print(f"\n  ❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("配置管理器测试")
    print("=" * 60)
    
    results = []
    
    # 测试 1
    try:
        results.append(("配置文件加载", test_load_config()))
    except Exception as e:
        print(f"\n测试 1 异常: {e}")
        results.append(("配置文件加载", False))
    
    # 测试 2
    try:
        results.append(("配置参数验证", test_validate_config()))
    except Exception as e:
        print(f"\n测试 2 异常: {e}")
        results.append(("配置参数验证", False))
    
    # 测试 3
    try:
        results.append(("配置保存", test_save_config()))
    except Exception as e:
        print(f"\n测试 3 异常: {e}")
        results.append(("配置保存", False))
    
    # 测试 4
    try:
        results.append(("配置热更新检测", test_hot_reload()))
    except Exception as e:
        print(f"\n测试 4 异常: {e}")
        results.append(("配置热更新检测", False))
    
    # 测试 5
    try:
        results.append(("默认配置", test_default_config()))
    except Exception as e:
        print(f"\n测试 5 异常: {e}")
        results.append(("默认配置", False))
    
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
