# -*- coding: utf-8 -*-
"""
CosyVoice2 实时 TTS 音频生成模块
适配 4GB 显卡，强制关闭 JIT 和 TRT 优化

复刻自 MagicMirror/backend/TTS.py 的设计思路：
- 延迟初始化、音色缓存、并行处理
- 文本切分、音频合并、WAV 转换
- 说话人管理、显存回收优化

专注于音频生成功能，不包含前端相关代码。
"""
import os
import sys
import re
import time
import gc
import numpy as np
import torch
import wave
import io
from queue import Queue, Empty
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- 淡入淡出 ----------
def fade_in_out(audio: np.ndarray, sr: int, fade_duration: float = 0.01) -> np.ndarray:
    fade_samples = int(fade_duration * sr)
    if len(audio) <= 2 * fade_samples:
        return audio
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    audio = audio.copy()
    audio[:fade_samples] *= fade_in
    audio[-fade_samples:] *= fade_out
    return audio

# ---------- CosyVoice 路径设置 ----------
# 获取当前文件所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 向上两级目录到达 tts 根目录（engine -> tts）
TTS_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
# Matcha-TTS 路径（cosyvoice 需要它）
MATCHA_TTS_PATH = os.path.join(TTS_ROOT, "third_party", "Matcha-TTS")
# 添加到 sys.path（如果不在），这样可以直接导入 cosyvoice 和 matcha
for p in [TTS_ROOT, MATCHA_TTS_PATH]:
    if p not in sys.path:
        sys.path.insert(0, p)

# 延迟导入 CosyVoice2，避免模块加载时出错
# from cosyvoice.cli.cosyvoice import CosyVoice2
# from cosyvoice.utils.file_utils import load_wav
# ---------------------------------


class CosyvoiceRealTimeTTS:
    # 类级别的预编译正则表达式，避免重复编译
    _sentence_pattern = re.compile(r'[^。！？!?；;]*[。！？!?；;]?')
    _word_pattern = re.compile(r'\w', flags=re.UNICODE)
    
    def __init__(self, model_path: str, reference_audio_path: str = None, max_queue: int = 10, load_jit: bool = False, load_trt: bool = False):
        """
        初始化 TTS 引擎
        
        Args:
            model_path: CosyVoice2 模型路径
            reference_audio_path: 参考音频路径（用于语音克隆），可选
            max_queue: 音频队列最大长度
            load_jit: 是否加载 JIT 模型（默认 False，4GB 显卡不支持）
            load_trt: 是否加载 TensorRT 模型（默认 False，4GB 显卡不支持）
        """
        # 延迟导入 CosyVoice2
        from cosyvoice.cli.cosyvoice import CosyVoice2
        from cosyvoice.utils.file_utils import load_wav

        # 4GB 显卡强制关闭 JIT 和 TRT
        if load_jit or load_trt:
            print(f"[WARN] 4GB 显卡不支持 JIT/TRT 优化，已强制关闭")
            load_jit = False
            load_trt = False
        
        print(f"加载模型中... (JIT: 禁用, TRT: 禁用, FP16: 启用)")
        self.cosyvoice = CosyVoice2(model_path, load_jit=False, load_trt=False, fp16=True)
        self.load_wav_func = load_wav
        self.sample_rate = self.cosyvoice.sample_rate
        self.ref_wav = None
        if reference_audio_path and os.path.isfile(reference_audio_path):
            self.ref_wav = self.load_wav_func(reference_audio_path, 16000)
            print(f"[INFO] 已加载参考音频：{reference_audio_path}")
        elif reference_audio_path:
            print(f"[WARN] 参考音频不存在：{reference_audio_path}")

        # ---- 音色缓存 ----
        # 注意：音色缓存将在第一次生成音频时自动提取（延迟初始化）
        # 这样允许用户先上传参考音频，再创建说话人
        self._prompt_semantic = None
        self._spk_emb = None
        self._cache_lock = Lock()  # 音色缓存锁
        # ------------------

        self.sample_text = "这是一段测试语音，喂喂喂，你们听得到吗？让我看看啊别急"

        self.audio_queue = Queue(maxsize=max_queue)
        self.stream = None
        self.is_playing = False
        self.playback_thread = None
        self.total_audio_dur = 0.0
        self.played_dur = 0.0
        self.fade_dur = 0.01

    # ------------ 工具：文本切分 + 空文本过滤 ------------
    def split_text_by_punctuation(self, text: str):
        text = text.strip()
        if not text:
            return []
        MAX_CHARS = 120  # 从80增加到120，减少切分段数
        # 先按句末标点优先切分，保留标点（使用预编译的正则表达式）
        raw_sentences = self._sentence_pattern.findall(text)
        sentences = []
        for sentence in raw_sentences:
            cleaned = sentence.strip()
            if cleaned:
                sentences.append(cleaned)
        if not sentences:
            sentences = [text]
        segs = []
        for sentence in sentences:
            current = sentence
            while len(current) > MAX_CHARS:
                segs.append(current[:MAX_CHARS].strip())
                current = current[MAX_CHARS:]
            if current.strip():
                segs.append(current.strip())
        # 过滤纯标点/空白（使用预编译的正则表达式）
        segs = [s for s in segs if self._word_pattern.search(s)]
        return segs

    # ------------ 保存音频工作线程 ------------
    def _save_audio_worker(self, output_file: str):
        """保存音频工作线程：从队列中获取音频数据并保存到文件"""
        audio_chunks = []
        while self.is_playing or not self.audio_queue.empty():
            try:
                data = self.audio_queue.get(timeout=1)
                if data is None:
                    self.audio_queue.task_done()
                    break
                # 如果是立体声，转换为单声道
                if len(data.shape) > 1 and data.shape[-1] == 2:
                    data = np.mean(data, axis=-1)
                elif len(data.shape) > 1 and data.shape[0] == 2:
                    data = np.mean(data, axis=0)
                audio_chunks.append(data)
                self.played_dur += len(data) / self.sample_rate
                self.audio_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                print(f"[保存音频] 错误：{e}")
                self.audio_queue.task_done()
        
        # 合并所有音频块并保存
        if audio_chunks:
            full_audio = np.concatenate(audio_chunks)
            self.audio_to_wav_file(full_audio, self.sample_rate, output_file)
            print(f"[保存音频] 已保存到: {output_file}")
        
        self._close_stream()

    def _close_stream(self):
        """关闭流（兼容性函数，现在不做任何操作）"""
        self.is_playing = False
        self.total_audio_dur = 0.0
        self.played_dur = 0.0

    # ------------ 合成线程（StopIteration 已修复） ------------
    def _synthesis_worker(self, segments, use_clone):
        for idx, seg in enumerate(segments, 1):
            print(f"【合成】{idx}/{len(segments)}：{seg[:30]}...")
            if not self._word_pattern.search(seg):
                print(f"【跳过】段 {idx} 无有效文字")
                continue

            results = None
            try:
                # 1）生成
                with self._cache_lock:
                    if use_clone and self._prompt_semantic is not None:
                        results = self.cosyvoice.inference(
                            seg, prompt_semantic=self._prompt_semantic,
                            spk_emb=self._spk_emb, stream=False)
                    else:
                        results = self.cosyvoice.inference_zero_shot(
                            seg, self.sample_text, self.ref_wav, stream=False)

                    # ✅ 关键：生成器→列表，防止二次next抛StopIteration
                    results = list(results)

                    # 2）缓存音色（第一次）
                    if use_clone and self._prompt_semantic is None:
                        first = results[0]
                        self._prompt_semantic = first.get("prompt_semantic")
                        self._spk_emb = first.get("spk_emb")

                # 3）拿音频
                audio_result = results[0]
                audio = audio_result['tts_speech'].squeeze().cpu().numpy().astype(np.float32)
                if np.max(np.abs(audio)) > 0:
                    audio /= np.max(np.abs(audio))
                audio = fade_in_out(audio, self.sample_rate, self.fade_dur)

                # 4）入队（单声道）
                dur = len(audio) / self.sample_rate
                self.total_audio_dur += dur
                print(f"【合成】片段 {idx} 完成，时长 {dur:.2f}s")
                self.audio_queue.put(audio, block=True)

            except Exception as e:
                print(f"【合成】段 {idx} 失败：{repr(e)}")
                continue

            finally:
                if results is not None:
                    del results

        # 所有片段生成完成后，统一清理显存
        gc.collect()
        torch.cuda.empty_cache()
        self.audio_queue.put(None)   # 结束哨兵

    # ------------ 对外接口：文本转语音并保存为文件 ------------
    def text_to_speech(self, text: str, use_clone=True, output_file: str = None):
        """
        文本转语音并保存为文件（不再播放）
        Args:
            text: 要合成的文本
            use_clone: 是否使用零样本克隆
            output_file: 输出文件路径，如果为None则使用默认路径
        """
        text = text.strip()
        if not text:
            print("[提示] 输入文本为空")
            return False
        if use_clone and self.ref_wav is None:
            print("[WARN] 无参考语音，自动使用默认音色")
            use_clone = False
        
        # 如果没有指定输出文件，使用默认路径
        if output_file is None:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(BASE_DIR, "audio", f"tts_output_{timestamp}.wav")
        
        try:
            segments = self.split_text_by_punctuation(text)
            if not segments:
                print("[提示] 没有有效可合成文本")
                return False
            print(f"文本已切分为 {len(segments)} 段")

            # 清空队列 & 启动保存音频线程
            self._clear_queue()
            self.is_playing = True
            self.total_audio_dur = 0.0
            self.played_dur = 0.0
            self.playback_thread = Thread(target=self._save_audio_worker, args=(output_file,), daemon=True)
            self.playback_thread.start()

            # 启动合成线程
            synth_thread = Thread(target=self._synthesis_worker,
                                args=(segments, use_clone), daemon=True)
            synth_thread.start()

            # 阻塞至保存完成
            self.audio_queue.join()
            synth_thread.join()
            self.is_playing = False
            if self.playback_thread:
                self.playback_thread.join(timeout=5)
            print(f"✅ 合成与保存完成，文件: {output_file}\n")
            return True
        except Exception as e:
            print(f"❌ 合成错误：{e}")
            self.is_playing = False
            self._close_stream()
            return False

    # ------------ 清空队列 ------------
    def _clear_queue(self):
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Empty:
                break

    # ------------ 单个音频段生成（用于并行处理）------------
    def _generate_single_segment(self, idx: int, seg: str, use_clone: bool):
        """
        生成单个文本段的音频
        返回: (idx, audio) 或 (idx, None) 如果失败
        """
        if not self._word_pattern.search(seg):
            print(f"【跳过】段 {idx} 无有效文字")
            return (idx, None)
        
        print(f"【合成】{idx}：{seg[:30]}...")
        results = None
        try:
            # 1）生成 - 需要加锁保护音色缓存访问
            with self._cache_lock:
                if use_clone and self._prompt_semantic is not None:
                    results = self.cosyvoice.inference(
                        seg, prompt_semantic=self._prompt_semantic,
                        spk_emb=self._spk_emb, stream=False)
                else:
                    results = self.cosyvoice.inference_zero_shot(
                        seg, self.sample_text, self.ref_wav, stream=False)
                
                # ✅ 关键：生成器→列表，防止二次next抛StopIteration
                results = list(results)
                
                # 2）缓存音色（第一次，需要线程安全）
                if use_clone and self._prompt_semantic is None:
                    first = results[0]
                    self._prompt_semantic = first.get("prompt_semantic")
                    self._spk_emb = first.get("spk_emb")
            
            # 3）拿音频（在锁外处理，避免长时间持锁）
            audio_result = results[0]
            audio = audio_result['tts_speech'].squeeze().cpu().numpy().astype(np.float32)
            if np.max(np.abs(audio)) > 0:
                audio /= np.max(np.abs(audio))
            audio = fade_in_out(audio, self.sample_rate, self.fade_dur)
            
            dur = len(audio) / self.sample_rate
            print(f"【合成】片段 {idx} 完成，时长 {dur:.2f}s")
            return (idx, audio)
            
        except Exception as e:
            print(f"【合成】段 {idx} 失败：{repr(e)}")
            return (idx, None)
        finally:
            if results is not None:
                del results

    # ------------ 生成音频数据（不播放，并行处理）------------
    def generate_audio(self, text: str, use_clone=True, max_workers=None):
        """
        生成音频数据并返回为numpy数组（单声道）
        使用并行处理加速生成，但保持输出顺序
        返回: (audio_data, sample_rate) 或 None
        """
        text = text.strip()
        if not text:
            print("[提示] 输入文本为空")
            return None
        if use_clone and self.ref_wav is None:
            print("[WARN] 无参考语音，自动使用默认音色")
            use_clone = False
        try:
            segments = self.split_text_by_punctuation(text)
            if not segments:
                print("[提示] 没有有效可合成文本")
                return None
            print(f"文本已切分为 {len(segments)} 段，开始并行生成...")

            # 如果没有指定工作线程数，使用段数和CPU核心数的较小值
            if max_workers is None:
                max_workers = min(len(segments), os.cpu_count() or 2, 4)  # 最多4个线程，避免显存溢出
            
            # 使用线程池并行处理
            audio_results = {}  # 用字典存储结果，key为索引
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_idx = {
                    executor.submit(self._generate_single_segment, idx, seg, use_clone): idx
                    for idx, seg in enumerate(segments, 1)
                }
                
                # 收集结果（按完成顺序，但用索引保持顺序）
                for future in as_completed(future_to_idx):
                    idx, audio = future.result()
                    if audio is not None:
                        audio_results[idx] = audio
            
            # 按索引顺序合并音频段（保证顺序）
            if not audio_results:
                print("[提示] 没有生成任何音频")
                return None
            
            # 按索引排序后合并
            sorted_indices = sorted(audio_results.keys())
            audio_segments = [audio_results[idx] for idx in sorted_indices]
            
            # 合并所有音频段
            full_audio = np.concatenate(audio_segments)
            
            # 最后统一清理显存（减少清理频率）
            gc.collect()
            torch.cuda.empty_cache()
            
            print(f"✅ 音频生成完成，总时长 {len(full_audio) / self.sample_rate:.2f}s\n")
            return (full_audio, self.sample_rate)
            
        except Exception as e:
            print(f"❌ 生成错误：{e}")
            import traceback
            traceback.print_exc()
            return None

    # ------------ 使用已保存的说话人生成音频（更快）------------
    def generate_audio_with_speaker(self, text: str, spk_id: str, max_workers=None):
        """
        使用已保存的说话人生成音频数据
        返回: (audio_data, sample_rate) 或 None
        """
        text = text.strip()
        if not text:
            print("[提示] 输入文本为空")
            return None
        
        try:
            segments = self.split_text_by_punctuation(text)
            if not segments:
                print("[提示] 没有有效可合成文本")
                return None
            print(f"使用说话人 {spk_id} 生成音频，文本已切分为 {len(segments)} 段...")
            
            # 如果没有指定工作线程数，使用段数和CPU核心数的较小值
            if max_workers is None:
                max_workers = min(len(segments), os.cpu_count() or 2, 4)
            
            # 使用线程池并行处理
            audio_results = {}
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_idx = {
                    executor.submit(self._generate_single_segment_with_speaker, idx, seg, spk_id): idx
                    for idx, seg in enumerate(segments, 1)
                }
                
                for future in as_completed(future_to_idx):
                    idx, audio = future.result()
                    if audio is not None:
                        audio_results[idx] = audio
            
            if not audio_results:
                print("[提示] 没有生成任何音频")
                return None
            
            sorted_indices = sorted(audio_results.keys())
            audio_segments = [audio_results[idx] for idx in sorted_indices]
            full_audio = np.concatenate(audio_segments)
            
            gc.collect()
            torch.cuda.empty_cache()
            
            print(f"✅ 音频生成完成，总时长 {len(full_audio) / self.sample_rate:.2f}s\n")
            return (full_audio, self.sample_rate)
            
        except Exception as e:
            print(f"❌ 生成错误：{e}")
            import traceback
            traceback.print_exc()
            return None
    
    # ------------ 使用说话人生成单个音频段 ------------
    def _generate_single_segment_with_speaker(self, idx: int, seg: str, spk_id: str):
        """
        使用已保存的说话人生成单个文本段的音频
        返回: (idx, audio) 或 (idx, None) 如果失败
        """
        if not self._word_pattern.search(seg):
            print(f"【跳过】段 {idx} 无有效文字")
            return (idx, None)
        
        print(f"【合成】{idx}：{seg[:30]}...")
        results = None
        try:
            # 使用已保存的说话人（通过zero_shot_spk_id参数）
            results = self.cosyvoice.inference_zero_shot(
                seg, '', None, zero_shot_spk_id=spk_id, stream=False)
            
            results = list(results)
            
            audio_result = results[0]
            audio = audio_result['tts_speech'].squeeze().cpu().numpy().astype(np.float32)
            if np.max(np.abs(audio)) > 0:
                audio /= np.max(np.abs(audio))
            audio = fade_in_out(audio, self.sample_rate, self.fade_dur)
            
            dur = len(audio) / self.sample_rate
            print(f"【合成】片段 {idx} 完成，时长 {dur:.2f}s")
            return (idx, audio)
            
        except Exception as e:
            print(f"【合成】段 {idx} 失败：{repr(e)}")
            return (idx, None)
        finally:
            if results is not None:
                del results

    # ------------ 将numpy音频转换为WAV字节流 ------------
    def audio_to_wav_bytes(self, audio_data: np.ndarray, sample_rate: int):
        """
        将numpy音频数组转换为WAV格式的字节流
        """
        # 确保音频是单声道
        if len(audio_data.shape) > 1:
            audio_data = audio_data[:, 0] if audio_data.shape[1] > 0 else audio_data
        
        # 归一化到-1到1范围
        if np.max(np.abs(audio_data)) > 0:
            audio_data = audio_data / np.max(np.abs(audio_data))
        
        # 转换为16位整数
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # 创建WAV文件
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16位 = 2字节
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
        
        wav_buffer.seek(0)
        return wav_buffer.read()
    
    def audio_to_wav_file(self, audio_data: np.ndarray, sample_rate: int, output_file: str):
        """
        将numpy音频数组保存为WAV文件
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 确保音频是单声道
        if len(audio_data.shape) > 1:
            if audio_data.shape[0] == 2:
                audio_data = np.mean(audio_data, axis=0)
            elif len(audio_data.shape) > 1 and audio_data.shape[-1] == 2:
                audio_data = np.mean(audio_data, axis=-1)
            else:
                audio_data = audio_data.squeeze()
        
        # 归一化到 [-1, 1]
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val
        
        # 转换为16位整数
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # 保存为WAV文件
        with wave.open(output_file, 'wb') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16位 = 2字节
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())


# -------------------- CLI --------------------
if __name__ == "__main__":
    # 示例使用
    import sys
    from pathlib import Path
    
    # 假设模型在项目根目录的 Model 文件夹下
    project_root = Path(__file__).parent.parent.parent.parent.parent
    model_path = project_root / "Model" / "CosyVoice2-0.5B"
    ref_audio = project_root / "Model" / "zjj.wav"  # 示例路径
    
    if not model_path.exists():
        print(f"错误：模型路径不存在：{model_path}")
        sys.exit(1)
    
    try:
        tts = CosyvoiceRealTimeTTS(str(model_path), str(ref_audio) if ref_audio.exists() else None)
        print("=== 实时语音助手（输入 q 退出）===")
        while True:
            txt = input("请输入要转换的文本：")
            if txt.lower() == 'q':
                break
            # 生成音频并返回 numpy 数组
            result = tts.generate_audio(txt)
            if result:
                audio_data, sr = result
                print(f"✅ 生成成功，时长 {len(audio_data) / sr:.2f}s")
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"初始化失败：{e}")
        import traceback
        traceback.print_exc()
    finally:
        print("程序已退出")
