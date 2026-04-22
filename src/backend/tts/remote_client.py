# -*- coding: utf-8 -*-
"""
远程 TTS 客户端
通过 HTTP API 调用远程/云端 TTS 服务
"""

import requests
import base64
import numpy as np
import io
import wave
import time
from typing import Optional, Tuple, Generator
from dataclasses import dataclass

try:
    from core.log import log
except ImportError:
    # 独立运行时的回退
    class _Fallback:
        @staticmethod
        def debug(msg): pass
        @staticmethod
        def info(msg): print(msg)
        @staticmethod
        def warn(msg): print(msg)
        @staticmethod
        def error(msg): print(msg)
        @staticmethod
        def tts(msg): print(msg)
        @staticmethod
        def tts_debug(msg): pass
        @staticmethod
        def tts_segment(msg): print(msg)
    log = _Fallback()


@dataclass
class RemoteTTSConfig:
    """远程 TTS 配置"""
    base_url: str = ""  # TTS 服务地址（默认从环境变量 REMOTE_TTS_URL 读取）
    timeout: int = 60  # 请求超时（秒）
    use_clone: bool = True  # 使用语音克隆
    spk_id: Optional[str] = None  # 说话人 ID


class RemoteTTSClient:
    """
    远程 TTS 客户端
    
    支持两种模式：
    1. 同步模式：一次性生成全部音频
    2. 流式模式：分段生成，边收边播
    """
    
    def __init__(self, config: RemoteTTSConfig = None):
        if config is None:
            try:
                from core.settings import AppSettings
                s = AppSettings.load()
                config = RemoteTTSConfig(base_url=s.remote_tts_url)
            except Exception:
                config = RemoteTTSConfig(base_url="http://localhost:5001")
        elif not config.base_url:
            try:
                from core.settings import AppSettings
                s = AppSettings.load()
                config.base_url = s.remote_tts_url  # type: ignore[misc]
            except Exception:
                config.base_url = "http://localhost:5001"  # type: ignore[misc]
        self.config = config
        self.sample_rate = 22050  # 默认采样率，会从服务端获取
        self._session = requests.Session()
    
    @property
    def base_url(self) -> str:
        return self.config.base_url.rstrip('/')
    
    def health_check(self) -> bool:
        """检查 TTS 服务是否可用"""
        try:
            resp = self._session.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return resp.status_code == 200
        except:
            return False
    
    def generate_audio(self, text: str) -> Optional[Tuple[np.ndarray, int]]:
        """
        同步生成音频
        
        Args:
            text: 要合成的文本
            
        Returns:
            (audio_data, sample_rate) 或 None
        """
        try:
            resp = self._session.post(
                f"{self.base_url}/tts/generate",
                json={
                    "text": text,
                    "use_clone": self.config.use_clone,
                    "spk_id": self.config.spk_id,
                },
                timeout=self.config.timeout
            )
            
            if resp.status_code != 200:
                log.error(f"[远程TTS] 请求失败: {resp.status_code} - {resp.text}")
                return None
            
            data = resp.json()
            if data.get("status") != "success":
                log.error(f"[远程TTS] 生成失败: {data.get('error')}")
                return None
            
            # 解码 base64 音频
            audio_b64 = data.get("audio")
            sample_rate = data.get("sample_rate", 22050)
            self.sample_rate = sample_rate
            
            wav_bytes = base64.b64decode(audio_b64)
            audio = self._wav_bytes_to_array(wav_bytes)
            
            return (audio, sample_rate)
            
        except requests.Timeout:
            log.error("[远程TTS] 请求超时")
            return None
        except Exception as e:
            log.error(f"[远程TTS] 错误: {e}")
            return None
    
    def generate_audio_streaming(
        self,
        text: str,
        use_clone: bool = True,
        max_workers: int = 2,
        **kwargs
    ) -> Generator[Tuple[np.ndarray, int, int], None, None]:
        """
        流式生成音频（使用 enqueue/dequeue API）

        Args:
            text: 要合成的文本
            use_clone: 是否使用语音克隆（与本地 TTS 接口兼容）
            max_workers: 忽略（服务端控制）

        Yields:
            (audio_data, segment_idx, total_segments, visemes) 元组
        """
        t_start = time.time()
        text_preview = text[:50] + "..." if len(text) > 50 else text

        try:
            # 1. 入队任务
            resp = self._session.post(
                f"{self.base_url}/tts/enqueue",
                json={
                    "text": text,
                    "use_clone": use_clone,
                    "spk_id": self.config.spk_id,
                },
                timeout=10
            )

            if resp.status_code != 200:
                log.error(f"[远程TTS] 入队失败: {resp.status_code}")
                return

            data = resp.json()
            job_id = data.get("job_id")
            if not job_id:
                log.error("[远程TTS] 未获取到 job_id")
                return

            log.tts(f"[远程TTS] 任务已提交: {job_id[:8]}... 文本: {text_preview}")

            # 2. 循环获取音频段
            # 服务端语义：200=音频段, 202=暂无数据仍在合成, 204=任务结束, 409=失败
            segment_idx = 0
            poll_count = 0
            first_chunk_deadline = time.time() + 120  # 首段最多等 120 秒
            dequeue_timeout = 10  # 单次轮询等待（秒），避免长时间无提示
            expected_next = 1  # 期望收到的下一个段编号
            received_count = 0
            last_log_time = time.time()

            while True:
                try:
                    if segment_idx == 0 and time.time() > first_chunk_deadline:
                        log.error("[远程TTS] 首段音频等待超时（120s），请检查服务端负载或网络")
                        break

                    # 每 3 秒打印一次等待状态
                    if time.time() - last_log_time > 3:
                        log.tts(f"[远程TTS] 等待中... 已收 {received_count} 段，期望下一段 {expected_next}，已等待 {time.time() - t_start:.1f}s")
                        last_log_time = time.time()

                    resp = self._session.get(
                        f"{self.base_url}/tts/dequeue",
                        params={"job_id": job_id, "timeout": dequeue_timeout},
                        timeout=dequeue_timeout + 5
                    )

                    if resp.status_code == 202:
                        # 暂无新段，任务仍在进行，继续轮询
                        poll_count += 1
                        continue
                    elif resp.status_code == 204:
                        # 任务已完成且队列已空
                        log.tts(f"[远程TTS] 服务端返回 204（完成），received={received_count}")
                        break
                    elif resp.status_code == 409:
                        # 任务出错
                        err_msg = resp.json().get("error") if resp.content else "unknown"
                        log.error(f"[远程TTS] 任务出错: {err_msg}")
                        break
                    elif resp.status_code != 200:
                        log.error(f"[远程TTS] 获取音频失败: {resp.status_code}")
                        break

                    # 解析服务端返回的段编号
                    raw_seg = resp.headers.get("X-Segment-Idx", "0")
                    try:
                        seg_from_header = int(raw_seg)
                    except ValueError:
                        seg_from_header = segment_idx + 1

                    sample_rate = int(resp.headers.get("X-Sample-Rate", 22050))
                    self.sample_rate = sample_rate
                    total_segments = int(resp.headers.get("X-Segment-Total", -1))

                    audio_len = len(resp.content)

                    # 段丢失检测
                    if seg_from_header != expected_next:
                        log.tts_segment(
                            f"[TTS段丢失] 期望段 {expected_next}，实际收到段 {seg_from_header}，"
                            f"已收 {received_count}/{total_segments}，丢失段可能是 {expected_next}"
                        )
                        # 不跳段，继续处理（段可能在缓冲区里后面补上）
                    else:
                        log.tts_segment(
                            f"[TTS段OK] 段 {seg_from_header}/{total_segments}，音频 {audio_len} bytes，"
                            f"耗时 {time.time() - t_start:.2f}s"
                        )

                    segment_idx = seg_from_header
                    expected_next = segment_idx + 1
                    received_count += 1

                    # 解析 Viseme 数据（Rhubarb Lip Sync，可选）
                    visemes = None
                    viseme_b64 = resp.headers.get("X-Viseme-Data")
                    if viseme_b64:
                        try:
                            import json as _json
                            visemes = _json.loads(base64.b64decode(viseme_b64).decode('utf-8'))
                        except Exception:
                            pass

                    wav_bytes = resp.content
                    audio = self._wav_bytes_to_array(wav_bytes)
                    yield (audio, segment_idx, total_segments, visemes)

                except requests.Timeout:
                    log.tts("[远程TTS] 等待音频超时，继续轮询...")
                    continue

            # 结束时打印汇总
            elapsed = time.time() - t_start
            log.tts(f"[远程TTS] 流式合成完成。收到 {received_count}/{total_segments} 段，总耗时 {elapsed:.2f}s")

            if received_count < total_segments:
                log.tts(f"[TTS段警告] 丢失段！期望 {total_segments} 段，实际仅收到 {received_count} 段")

        except Exception as e:
            log.error(f"[远程TTS] 流式错误: {e}")
            import traceback
            traceback.print_exc()
            
        except Exception as e:
            log.error(f"[远程TTS] 流式错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _wav_bytes_to_array(self, wav_bytes: bytes) -> np.ndarray:
        """将 WAV 字节转换为 numpy 数组"""
        with io.BytesIO(wav_bytes) as f:
            with wave.open(f, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        return audio
    
    def text_to_speech(self, text: str, use_clone: bool = True, output_file: str = None) -> bool:
        """
        兼容本地 TTS 引擎的接口
        
        Args:
            text: 要合成的文本
            use_clone: 是否使用语音克隆
            output_file: 输出文件路径
            
        Returns:
            是否成功
        """
        self.config.use_clone = use_clone
        result = self.generate_audio(text)
        
        if result is None:
            return False
        
        audio, sr = result
        
        if output_file:
            self._save_wav(audio, sr, output_file)
        
        return True
    
    def _save_wav(self, audio: np.ndarray, sample_rate: int, path: str):
        """保存音频到 WAV 文件"""
        audio_int16 = (audio * 32767).astype(np.int16)
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())


# === 便捷函数 ===

def create_remote_tts(
    url: str = "http://localhost:5001",
    spk_id: str = None
) -> RemoteTTSClient:
    """
    创建远程 TTS 客户端
    
    Args:
        url: TTS 服务地址（本地或云端）
        spk_id: 说话人 ID
        
    Returns:
        RemoteTTSClient 实例
    """
    config = RemoteTTSConfig(
        base_url=url,
        spk_id=spk_id
    )
    return RemoteTTSClient(config)


if __name__ == "__main__":
    # 测试
    client = create_remote_tts("http://localhost:5001")
    
    if client.health_check():
        print("TTS 服务可用")
        
        # 测试同步生成
        result = client.generate_audio("你好，这是测试")
        if result:
            audio, sr = result
            print(f"生成成功: {len(audio)/sr:.2f}s")
    else:
        print("TTS 服务不可用")
