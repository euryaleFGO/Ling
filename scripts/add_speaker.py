# -*- coding: utf-8 -*-
"""
TTS 说话人管理脚本

使用方法:
    python scripts/add_speaker.py list              # 列出所有说话人
    python scripts/add_speaker.py clear             # 清空所有说话人
    python scripts/add_speaker.py add -a 音频 -t 文字 -n 名称   # 添加说话人

示例:
    python scripts/add_speaker.py add --audio E:/voices/sample.wav --text "你好，我是小明" --name 小明
"""

import sys
import os
import argparse
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


def get_tts_engine():
    """获取 TTS 引擎"""
    from backend.tts.engine import CosyvoiceRealTimeTTS
    
    # 找到 TTS 模型目录
    model_paths = [
        project_root / "models" / "TTS" / "CosyVoice2-0.5B",
        Path("E:/Avalon/Chaldea/Liying/models/TTS/CosyVoice2-0.5B"),
    ]
    
    model_path = None
    for p in model_paths:
        if p.exists():
            model_path = str(p)
            break
    
    if not model_path:
        print("❌ 未找到 TTS 模型目录")
        return None
    
    print(f"🔄 正在加载 TTS 引擎...")
    tts = CosyvoiceRealTimeTTS(model_path=model_path)
    return tts


def clear_speakers():
    """清空所有已注册的说话人"""
    print("=" * 50)
    print("清空所有说话人")
    print("=" * 50)
    
    try:
        tts = get_tts_engine()
        if not tts:
            return False
        
        # 获取当前说话人列表
        current_speakers = tts.cosyvoice.list_available_spks()
        print(f"\n📋 当前说话人 ({len(current_speakers)} 个):")
        for spk in current_speakers:
            print(f"   - {spk}")
        
        if not current_speakers:
            print("\n✅ 说话人列表已经为空")
            return True
        
        # 确认清空
        confirm = input(f"\n⚠️ 确定要清空所有 {len(current_speakers)} 个说话人吗？(y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ 已取消")
            return False
        
        # 清空说话人
        tts.cosyvoice.frontend.spk2info = {}
        
        # 保存空的说话人信息
        tts.cosyvoice.save_spkinfo()
        
        print(f"\n✅ 已清空所有说话人！")
        print(f"   spk2info.pt 已保存到: {tts.cosyvoice.model_dir}")
        return True
        
    except Exception as e:
        print(f"❌ 清空失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def add_speaker(audio_path: str, prompt_text: str, speaker_name: str):
    """添加说话人到 TTS 引擎"""
    print("=" * 50)
    print("添加新说话人")
    print("=" * 50)
    
    # 检查音频文件
    if not os.path.exists(audio_path):
        print(f"❌ 音频文件不存在: {audio_path}")
        return False
    
    # 检查文件格式
    valid_formats = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
    ext = Path(audio_path).suffix.lower()
    if ext not in valid_formats:
        print(f"❌ 不支持的音频格式: {ext}")
        print(f"   支持的格式: {', '.join(valid_formats)}")
        return False
    
    print(f"\n📁 音频文件: {audio_path}")
    print(f"📝 提示文本: {prompt_text}")
    print(f"👤 说话人名称: {speaker_name}")
    print()
    
    try:
        tts = get_tts_engine()
        if not tts:
            return False
        
        # 加载参考音频
        print(f"🔄 正在处理参考音频...")
        prompt_speech_16k = tts.load_wav_func(audio_path, 16000)
        
        # 添加说话人
        print(f"🔄 正在添加说话人...")
        success = tts.cosyvoice.add_zero_shot_spk(
            prompt_text=prompt_text,
            prompt_speech_16k=prompt_speech_16k,
            zero_shot_spk_id=speaker_name
        )
        
        if success:
            # 保存说话人信息
            tts.cosyvoice.save_spkinfo()
            print(f"\n✅ 说话人 '{speaker_name}' 添加成功！")
            print(f"   spk2info.pt 已保存到: {tts.cosyvoice.model_dir}")
            
            # 列出所有说话人
            speakers = tts.cosyvoice.list_available_spks()
            print(f"\n📋 当前所有说话人 ({len(speakers)} 个):")
            for spk in speakers:
                print(f"   - {spk}")
            return True
        else:
            print("❌ 添加说话人失败")
            return False
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def list_speakers():
    """列出所有已注册的说话人"""
    print("=" * 50)
    print("已注册的说话人")
    print("=" * 50)
    
    try:
        tts = get_tts_engine()
        if not tts:
            return []
        
        speakers = tts.cosyvoice.list_available_spks()
        
        if speakers:
            print(f"\n📋 说话人列表 ({len(speakers)} 个):")
            for i, spk in enumerate(speakers, 1):
                print(f"   {i}. {spk}")
        else:
            print("\n⚠️ 没有已注册的说话人")
            print("   使用 'add' 命令添加新说话人")
        
        return speakers
        
    except Exception as e:
        print(f"❌ 读取说话人信息失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    parser = argparse.ArgumentParser(description="TTS 说话人管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # add 命令
    add_parser = subparsers.add_parser("add", help="添加新说话人")
    add_parser.add_argument("--audio", "-a", required=True, help="参考音频文件路径")
    add_parser.add_argument("--text", "-t", required=True, help="参考音频中说的文字")
    add_parser.add_argument("--name", "-n", required=True, help="说话人名称/ID")
    
    # list 命令
    subparsers.add_parser("list", help="列出所有说话人")
    
    # clear 命令
    subparsers.add_parser("clear", help="清空所有说话人")
    
    args = parser.parse_args()
    
    if args.command == "add":
        add_speaker(args.audio, args.text, args.name)
    elif args.command == "list":
        list_speakers()
    elif args.command == "clear":
        clear_speakers()
    else:
        parser.print_help()
        print("\n" + "=" * 50)
        print("示例:")
        print("=" * 50)
        print("  列出说话人:  python scripts/add_speaker.py list")
        print("  清空说话人:  python scripts/add_speaker.py clear")
        print("  添加说话人:  python scripts/add_speaker.py add --audio 音频.wav --text \"文字\" --name 名称")


if __name__ == "__main__":
    main()
