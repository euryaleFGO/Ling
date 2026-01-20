"""发送用户消息到 LLM，获取 AI 回复并发送到 Live2D 窗口，自动生成语音"""
import requests
import sys
import os
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.absolute()
backtend_path = project_root / "backtend"
if str(backtend_path) not in sys.path:
    sys.path.insert(0, str(backtend_path))

from LLM.agent import Agent  # type: ignore
from LLM.database.knowledge_dao import get_knowledge_dao  # type: ignore

# TTS 模块路径
tts_module_path = project_root / "backtend" / "TTS" / "Local" / "tts"
if str(tts_module_path) not in sys.path:
    sys.path.insert(0, str(tts_module_path))

# Matcha-TTS 路径（cosyvoice 需要它）
matcha_tts_path = project_root / "backtend" / "TTS" / "Local" / "tts" / "third_party" / "Matcha-TTS"
if str(matcha_tts_path) not in sys.path:
    sys.path.insert(0, str(matcha_tts_path))

# 延迟导入 TTS（避免启动时加载模型）
_tts_engine = None

def play_audio_file(audio_file: Path):
    """播放音频文件，播放完成后删除文件"""
    try:
        # 优先使用 sounddevice 播放（如果已安装）
        try:
            import sounddevice as sd  # type: ignore
            import soundfile as sf  # type: ignore
            
            data, samplerate = sf.read(str(audio_file))
            print(f"🔊 正在播放语音...")
            sd.play(data, samplerate)
            sd.wait()  # 等待播放完成
            print(f"🔊 ✅ 播放完成")
            
            # 删除文件
            if audio_file.exists():
                audio_file.unlink()
                print(f"🗑️  已删除临时语音文件: {audio_file.name}")
            return
        except ImportError:
            pass
        
        # 如果没有 sounddevice，尝试使用 winsound (Windows 专用)
        try:
            import winsound
            print(f"🔊 正在播放语音...")
            winsound.PlaySound(str(audio_file), winsound.SND_FILENAME | winsound.SND_NOWAIT)
            
            # 计算播放时长（近似值）
            import wave
            with wave.open(str(audio_file), 'rb') as wf:
                frames = wf.getnframes()
                sample_rate = wf.getframerate()
                duration = frames / float(sample_rate)
                time.sleep(duration + 0.1)  # 稍微多等一点确保播放完成
            
            print(f"🔊 ✅ 播放完成")
            
            # 删除文件
            if audio_file.exists():
                audio_file.unlink()
                print(f"🗑️  已删除临时语音文件: {audio_file.name}")
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"🔊 ⚠️  winsound 播放失败：{e}")
        
        # 如果都不可用，使用 pygame.mixer（需要安装 pygame）
        try:
            import pygame  # type: ignore
            pygame.mixer.init()
            print(f"🔊 正在播放语音...")
            pygame.mixer.music.load(str(audio_file))
            pygame.mixer.music.play()
            
            # 等待播放完成
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            
            pygame.mixer.quit()
            print(f"🔊 ✅ 播放完成")
            
            # 删除文件
            if audio_file.exists():
                audio_file.unlink()
                print(f"🗑️  已删除临时语音文件: {audio_file.name}")
            return
        except ImportError:
            print(f"🔊 ⚠️  未找到音频播放库，请安装 sounddevice、pygame 或使用 Windows 系统")
            print(f"   推荐安装: pip install sounddevice soundfile")
            # 不删除文件，保留以便手动播放
        except Exception as e:
            print(f"🔊 ⚠️  pygame 播放失败：{e}")
            # 不删除文件，保留以便手动播放
            
    except Exception as e:
        print(f"🔊 ⚠️  播放音频失败：{e}")
        import traceback
        traceback.print_exc()
        # 不删除文件，保留以便手动播放

def play_audio_data(audio_data, sample_rate: int):
    """直接播放音频数据（numpy 数组），无需保存文件"""
    try:
        import sounddevice as sd  # type: ignore
        print(f"🔊 正在播放语音...")
        sd.play(audio_data, sample_rate)
        sd.wait()  # 等待播放完成
        print(f"🔊 ✅ 播放完成")
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"🔊 ⚠️  播放音频失败：{e}")
        return False

def get_tts_engine():
    """获取 TTS 引擎（延迟初始化）"""
    global _tts_engine
    if _tts_engine is not None:
        return _tts_engine
    
    try:
        from engine import CosyvoiceRealTimeTTS  # type: ignore
        
        # 默认模型路径
        model_path = project_root / "backtend" / "models" / "TTS" / "CosyVoice2-0.5B"
        ref_audio = project_root / "backtend" / "TTS" / "Local" / "MagicMirror" / "backend" / "audio" / "zjj.wav"
        
        # 尝试查找参考音频
        if not ref_audio.exists():
            # 尝试其他可能的位置
            possible_ref_audios = [
                project_root / "Model" / "zjj.wav",
                project_root / "audio" / "zjj.wav",
            ]
            for audio_path in possible_ref_audios:
                if audio_path.exists():
                    ref_audio = audio_path
                    break
            else:
                ref_audio = None
        
        if not model_path.exists():
            print(f"⚠️  TTS 模型路径不存在：{model_path}")
            print("   将跳过语音生成功能")
            return None
        
        print(f"[TTS] 正在初始化 TTS 引擎...")
        print(f"[TTS] 模型路径: {model_path}")
        if ref_audio and ref_audio.exists():
            print(f"[TTS] 参考音频: {ref_audio}")
        else:
            print(f"[TTS] 警告：未找到参考音频，将使用默认音色")
        
        _tts_engine = CosyvoiceRealTimeTTS(str(model_path), str(ref_audio) if ref_audio and ref_audio.exists() else None)
        print(f"[TTS] ✅ TTS 引擎初始化成功")
        return _tts_engine
    except Exception as e:
        print(f"[TTS] ⚠️  TTS 初始化失败：{e}")
        import traceback
        traceback.print_exc()
        return None

def send_user_message(message):
    """直接调用 Agent.chat()，然后把 AI 回复发送到 message_server 并生成语音"""
    try:
        print(f"📤 用户消息: {message}")
        
        # 初始化 Agent（如果需要）
        knowledge_dao = get_knowledge_dao()
        character = knowledge_dao.get_active_character()
        if not character:
            # 创建默认角色
            knowledge_dao.create_character(
                name="玲",
                personality={"traits": ["温柔", "活泼"]},
                background="玲是一个虚拟助手",
                system_prompt="你是玲，一个温柔活泼的虚拟助手。称呼用户为'主人'。",
                greeting="主人，你回来啦~"
            )
            knowledge_dao.create_user_profile(user_id="default_user", nickname="主人")
        
        agent = Agent(user_id="default_user", enable_tools=True)
        if not agent._context_manager.session_id:
            agent.start_chat()
        
        # 直接调用 Agent.chat()，等待完整回复后一次性发送
        print(f"🤖 正在生成 AI 回复...")
        
        # 清空气泡框
        requests.post(
            'http://localhost:8765/api/message',
            json={'text': '', 'new': True},
            timeout=1
        )
        
        # 非流式获取完整回复
        full_response = []
        for chunk in agent.chat(message, stream=True):
            if chunk:
                full_response.append(chunk)
        
        # 完整回复生成后，一次性发送
        complete_text = ''.join(full_response)
        print(f"🤖 AI 回复: {complete_text}")
        
        if complete_text:
            # 发送到 Live2D 窗口
            requests.post(
                'http://localhost:8765/api/message',
                json={'text': complete_text, 'new': True},
                timeout=5
            )
            print(f"✅ AI 回复已发送到 Live2D 窗口（共 {len(complete_text)} 字符）")
            
            # 自动生成语音
            tts = get_tts_engine()
            if tts:
                try:
                    print(f"🎤 正在生成语音...")
                    # 生成音频并保存
                    audio_dir = project_root / "audio_output"
                    audio_dir.mkdir(exist_ok=True)
                    
                    result = tts.generate_audio(complete_text, use_clone=True)
                    if result:
                        audio_data, sample_rate = result
                        
                        # 尝试直接播放音频数据（无需保存文件）
                        if play_audio_data(audio_data, sample_rate):
                            print(f"🎤 ✅ 语音已生成并播放完成")
                        else:
                            # 如果直接播放失败，保存文件然后播放并删除
                            import datetime
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            audio_file = audio_dir / f"tts_{timestamp}.wav"
                            tts.audio_to_wav_file(audio_data, sample_rate, str(audio_file))
                            print(f"🎤 ✅ 语音已生成: {audio_file.name}")
                            
                            # 播放并删除文件
                            play_audio_file(audio_file)
                    else:
                        print(f"🎤 ⚠️  语音生成失败")
                except Exception as e:
                    print(f"🎤 ⚠️  语音生成出错：{e}")
            else:
                print(f"🎤 ⚠️  TTS 引擎未初始化，跳过语音生成")
        else:
            print("⚠️  AI 回复为空")
        
    except requests.exceptions.ConnectionError:
        print("❌ 错误: 无法连接到消息服务器")
        print("   请确保 message_server.py 正在运行")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # 如果有命令行参数，执行一次后退出（单次模式）
    if len(sys.argv) > 1:
        message = ' '.join(sys.argv[1:])
        send_user_message(message)
    else:
        # 循环模式：持续接收用户输入
        print("=" * 60)
        print("💬 对话模式已启动")
        print("=" * 60)
        print("提示：")
        print("  - 直接输入消息并回车发送")
        print("  - 输入 'exit' 或 'quit' 退出")
        print("  - 输入 Ctrl+C 也可以退出")
        print("=" * 60)
        print()
        
        # 预初始化 Agent 和 TTS（可选，用于优化）
        _agent = None
        _knowledge_dao = None
        
        try:
            while True:
                try:
                    # 获取用户输入
                    message = input("\n💬 你: ").strip()
                    
                    # 检查退出命令
                    if not message:
                        continue
                    
                    if message.lower() in ['exit', 'quit', '退出', 'q']:
                        print("👋 再见！")
                        break
                    
                    # 发送消息
                    send_user_message(message)
                    
                except KeyboardInterrupt:
                    # 处理 Ctrl+C
                    print("\n\n👋 再见！")
                    break
                except EOFError:
                    # 处理 EOF（文件结束）
                    print("\n👋 再见！")
                    break
                    
        except KeyboardInterrupt:
            print("\n\n👋 再见！")

