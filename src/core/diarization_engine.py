# -*- coding: utf-8 -*-
"""
多说话人识别（Speaker Diarization）- 轻量离线实现

目标：
- 给一段音频做“说话片段切分 + 每段说话人标签”
- 不依赖 HuggingFace token/pyannote，优先复用本项目已有的 SVEngine（CampPlus）声纹向量

实现策略：
1) VAD 切分：优先用 silero-vad 的 get_speech_timestamps（若可用），否则使用简单能量门限 + 静音合并
2) 对每个语音片段提取 speaker embedding（SVEngine.embed）
3) 用余弦相似度做贪心聚类（无需 sklearn）

注意：
- 这是“可用的最小实现”，效果强依赖录音质量、说话重叠（重叠说话暂不处理）与片段长度。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.core.sv_engine import SVEngine

log = logging.getLogger(__name__)


# ============================================================================
# Real-time Speaker Identification (DiarizationEngine)
# ============================================================================

@dataclass(frozen=True)
class DiarizationResult:
    """实时说话人识别结果"""
    speaker_id: str              # "speaker_1" | "speaker_2" | "unknown"
    score: float                 # 相似度分数 (0.0-1.0)
    reason: str                  # 识别原因/状态
    duration_sec: float          # 音频时长
    is_confident: bool           # 是否高置信度


class DiarizationEngine:
    """
    实时说话人识别引擎
    
    功能：
    - 从音频中提取声纹特征
    - 与声纹数据库中的已知说话人进行匹配
    - 返回识别结果（speaker_id, score, confidence）
    
    使用场景：
    - 实时对话中识别"谁在说话"
    - 需要预先注册说话人声纹
    """
    
    def __init__(
        self,
        sv_engine: SVEngine,
        voiceprint_db,  # VoiceprintDatabase
        threshold: float = 0.75,
        min_audio_sec: float = 0.8,
        device: str = "auto",
        timeout_ms: int = 500,
        max_failures: int = 3
    ):
        """
        初始化识别引擎
        
        Args:
            sv_engine: 声纹提取引擎（复用现有 SVEngine）
            voiceprint_db: 声纹数据库
            threshold: 相似度阈值（0.0-1.0）
            min_audio_sec: 最小音频时长（秒）
            device: 运行设备 ("auto" | "cpu" | "cuda")
            timeout_ms: 识别超时时间（毫秒）
            max_failures: 最大连续失败次数
        """
        self.sv_engine = sv_engine
        self.voiceprint_db = voiceprint_db
        self.threshold = float(threshold)
        self.min_audio_sec = float(min_audio_sec)
        self.device = device
        self.timeout_ms = int(timeout_ms)
        
        # 缓存机制（避免重复计算）
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._cache_size = 100
        
        # 记录上一次识别的说话人
        self._last_speaker_id: Optional[str] = None
        
        # 错误处理和降级策略（需求 8.1-8.6）
        self._consecutive_failures: int = 0
        self._max_failures: int = max_failures
        self._temporarily_disabled: bool = False
        self._user_notification_callback: Optional[callable] = None
    
    def identify(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> DiarizationResult:
        """
        识别音频中的说话人（带超时控制和错误处理）
        
        Args:
            audio: 音频数据（float32, mono）
            sample_rate: 采样率
            
        Returns:
            DiarizationResult: 包含 speaker_id, score, reason
        """
        import concurrent.futures
        import time
        
        # 需求 8.6: 检查是否临时禁用
        if self._temporarily_disabled:
            log.debug("[说话人识别] 已临时禁用，使用上一次结果")
            return DiarizationResult(
                speaker_id=self._last_speaker_id or "unknown",
                score=0.0,
                reason="temporarily_disabled",
                duration_sec=0.0,
                is_confident=False
            )
        
        # 转换为 float32 mono
        audio = _to_mono_float32(audio)
        
        # 检查音频时长（需求 2.5）
        duration_sec = len(audio) / sample_rate
        if duration_sec < self.min_audio_sec:
            log.debug(f"[说话人识别] 音频过短: {duration_sec:.2f}s < {self.min_audio_sec}s，跳过识别")
            return DiarizationResult(
                speaker_id=self._last_speaker_id or "unknown",
                score=0.0,
                reason=f"audio_too_short:{duration_sec:.2f}s<{self.min_audio_sec}s",
                duration_sec=duration_sec,
                is_confident=False
            )
        
        # 需求 8.4: 使用超时控制（默认 500ms）
        start_time = time.time()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._do_identify, audio, sample_rate, duration_sec)
        
        try:
            result = future.result(timeout=self.timeout_ms / 1000.0)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # 需求 8.1: 识别成功，重置失败计数
            self._consecutive_failures = 0
            
            log.debug(f"[说话人识别] 成功: speaker_id={result.speaker_id}, score={result.score:.3f}, 耗时={elapsed_ms:.0f}ms")
            return result
            
        except concurrent.futures.TimeoutError:
            # 需求 8.4: 识别超时，使用上一次结果
            elapsed_ms = (time.time() - start_time) * 1000
            self._consecutive_failures += 1
            log.warning(f"[说话人识别] 超时 ({elapsed_ms:.0f}ms > {self.timeout_ms}ms)，使用上一次结果 (失败次数: {self._consecutive_failures}/{self._max_failures})")
            
            # 需求 8.6: 检查是否达到最大失败次数
            self._check_and_disable_if_needed()
            
            # 需求 8.2: 返回上一次识别的 Speaker_ID
            return DiarizationResult(
                speaker_id=self._last_speaker_id or "unknown",
                score=0.0,
                reason=f"timeout:{elapsed_ms:.0f}ms",
                duration_sec=duration_sec,
                is_confident=False
            )
            
        except Exception as e:
            # 需求 8.5: 记录错误日志
            elapsed_ms = (time.time() - start_time) * 1000
            self._consecutive_failures += 1
            log.error(f"[说话人识别] 失败: {type(e).__name__}: {e} (失败次数: {self._consecutive_failures}/{self._max_failures})")
            
            # 需求 8.6: 检查是否达到最大失败次数
            self._check_and_disable_if_needed()
            
            # 需求 8.2: 返回上一次识别的 Speaker_ID
            return DiarizationResult(
                speaker_id=self._last_speaker_id or "unknown",
                score=0.0,
                reason=f"error:{type(e).__name__}",
                duration_sec=duration_sec,
                is_confident=False
            )
        finally:
            executor.shutdown(wait=False)
    
    def get_last_speaker(self) -> Optional[str]:
        """获取上一次识别的说话人 ID"""
        return self._last_speaker_id
    
    def set_notification_callback(self, callback: callable):
        """
        设置用户通知回调函数
        
        Args:
            callback: 回调函数，接收通知消息字符串
        """
        self._user_notification_callback = callback
    
    def reset_failure_counter(self):
        """重置失败计数器（用于手动恢复）"""
        self._consecutive_failures = 0
        self._temporarily_disabled = False
        log.info("[说话人识别] 失败计数器已重置，识别功能已恢复")
    
    def is_temporarily_disabled(self) -> bool:
        """检查是否临时禁用"""
        return self._temporarily_disabled
    
    def _do_identify(
        self,
        audio: np.ndarray,
        sample_rate: int,
        duration_sec: float
    ) -> DiarizationResult:
        """
        执行实际的识别逻辑（内部方法，用于超时控制）
        
        Args:
            audio: 音频数据
            sample_rate: 采样率
            duration_sec: 音频时长
            
        Returns:
            DiarizationResult
        """
        # 提取声纹特征（带缓存）
        query_emb = self._extract_embedding_cached(audio, sample_rate)
        
        # 需求 8.3: 与数据库匹配（可能抛出数据库访问异常）
        speaker_id, score = self.voiceprint_db.find_best_match(
            query_emb,
            threshold=self.threshold
        )
        
        # 判断是否识别成功
        if speaker_id is None:
            return DiarizationResult(
                speaker_id="unknown",
                score=score,
                reason=f"no_match:best_score={score:.3f}<threshold={self.threshold}",
                duration_sec=duration_sec,
                is_confident=False
            )
        
        # 识别成功
        self._last_speaker_id = speaker_id
        is_confident = score >= (self.threshold + 0.05)  # 高置信度：超过阈值 5%
        
        return DiarizationResult(
            speaker_id=speaker_id,
            score=score,
            reason="matched",
            duration_sec=duration_sec,
            is_confident=is_confident
        )
    
    def _check_and_disable_if_needed(self):
        """
        需求 8.6: 检查连续失败次数，达到阈值时临时禁用并通知用户
        """
        if self._consecutive_failures >= self._max_failures:
            self._temporarily_disabled = True
            error_msg = f"说话人识别连续失败 {self._max_failures} 次，已临时禁用。系统已切换到单用户模式。"
            log.error(f"[说话人识别] {error_msg}")
            
            # 通知用户
            if self._user_notification_callback:
                try:
                    self._user_notification_callback(error_msg)
                except Exception as e:
                    log.warning(f"[说话人识别] 用户通知回调失败: {e}")
    
    def _extract_embedding_cached(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> np.ndarray:
        """
        提取声纹特征（带缓存）
        
        Args:
            audio: 音频数据
            sample_rate: 采样率
            
        Returns:
            声纹向量
        """
        # 计算音频哈希
        audio_hash = hashlib.md5(audio.tobytes()).hexdigest()
        
        # 检查缓存
        if audio_hash in self._embedding_cache:
            return self._embedding_cache[audio_hash]
        
        # 提取声纹
        embedding = self.sv_engine.embed(audio, sample_rate=sample_rate)
        
        # 添加到缓存
        self._add_to_cache(audio_hash, embedding)
        
        return embedding
    
    def _add_to_cache(self, audio_hash: str, embedding: np.ndarray):
        """添加到缓存（LRU 策略）"""
        if len(self._embedding_cache) >= self._cache_size:
            # 删除最早的一个（简单 FIFO）
            first_key = next(iter(self._embedding_cache))
            del self._embedding_cache[first_key]
        
        self._embedding_cache[audio_hash] = embedding


# ============================================================================
# Offline Speaker Diarization (SpeakerDiarizer)
# ============================================================================

@dataclass(frozen=True)
class SpeechSegment:
    start_sec: float
    end_sec: float
    speaker: str
    score: float = 0.0  # 与该 speaker 原型的相似度（余弦）

    @property
    def duration_sec(self) -> float:
        return max(0.0, float(self.end_sec) - float(self.start_sec))


@dataclass(frozen=True)
class OfflineDiarizationResult:
    """离线说话人分离结果（用于 SpeakerDiarizer）"""
    segments: List[SpeechSegment]
    num_speakers: int
    sample_rate: int
    backend: str  # "silero" | "energy"


def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
    if audio is None:
        return np.zeros(0, dtype=np.float32)
    if not isinstance(audio, np.ndarray):
        audio = np.asarray(audio)
    if audio.size == 0:
        return np.zeros(0, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    elif audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    return audio.reshape(-1)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1e-8 or nb <= 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SpeakerDiarizer:
    """
    轻量离线说话人分离：
    - 输入：音频文件 / ndarray
    - 输出：SpeechSegment 列表（每段 speaker_1, speaker_2, ...）
    - 用途：对未知说话人进行聚类分析
    """

    def __init__(
        self,
        sv: Optional[SVEngine] = None,
        sample_rate: int = 16000,
        min_segment_sec: float = 0.6,
        max_segment_sec: float = 18.0,
        pad_sec: float = 0.15,
        cluster_sim_threshold: float = 0.72,
        energy_threshold: float = 0.006,
        energy_min_speech_sec: float = 0.25,
        energy_min_silence_sec: float = 0.35,
    ):
        self.sample_rate = int(sample_rate)
        self.min_segment_sec = float(min_segment_sec)
        self.max_segment_sec = float(max_segment_sec)
        self.pad_sec = float(pad_sec)
        self.cluster_sim_threshold = float(cluster_sim_threshold)
        self.energy_threshold = float(energy_threshold)
        self.energy_min_speech_sec = float(energy_min_speech_sec)
        self.energy_min_silence_sec = float(energy_min_silence_sec)
        self.sv = sv or SVEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def diarize_file(self, audio_path: str | Path) -> OfflineDiarizationResult:
        import soundfile as sf

        p = Path(audio_path)
        audio, sr = sf.read(str(p))
        audio = _to_mono_float32(audio)
        sr = int(sr)
        if sr != self.sample_rate:
            audio = self._resample(audio, orig_sr=sr, target_sr=self.sample_rate)
        return self.diarize_audio(audio, sample_rate=self.sample_rate)

    def diarize_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> OfflineDiarizationResult:
        a = _to_mono_float32(audio)
        sr = int(sample_rate)
        if sr != self.sample_rate:
            a = self._resample(a, orig_sr=sr, target_sr=self.sample_rate)
            sr = self.sample_rate

        segments, backend = self._vad_segments(a, sr)
        if not segments:
            return OfflineDiarizationResult(segments=[], num_speakers=0, sample_rate=sr, backend=backend)

        # 对每段提 embedding
        seg_embs: List[np.ndarray] = []
        kept_segments: List[Tuple[int, int]] = []
        for s0, s1 in segments:
            seg = a[s0:s1]
            dur = (s1 - s0) / sr
            if dur < self.min_segment_sec:
                continue
            if dur > self.max_segment_sec:
                # 过长段简单切块，避免 embedding 退化/吞并多说话人
                chunks = self._split_long_segment(s0, s1, sr)
                for c0, c1 in chunks:
                    e = self._safe_embed(a[c0:c1], sr)
                    if e is not None:
                        seg_embs.append(e)
                        kept_segments.append((c0, c1))
                continue

            e = self._safe_embed(seg, sr)
            if e is not None:
                seg_embs.append(e)
                kept_segments.append((s0, s1))

        if not kept_segments:
            return OfflineDiarizationResult(segments=[], num_speakers=0, sample_rate=sr, backend=backend)

        # 贪心聚类
        labels, scores = self._greedy_cluster(seg_embs, sim_threshold=self.cluster_sim_threshold)

        out: List[SpeechSegment] = []
        for (s0, s1), lab, sc in zip(kept_segments, labels, scores):
            out.append(
                SpeechSegment(
                    start_sec=s0 / sr,
                    end_sec=s1 / sr,
                    speaker=f"speaker_{lab + 1}",
                    score=float(sc),
                )
            )

        num_spk = 0 if not labels else (max(labels) + 1)
        return OfflineDiarizationResult(segments=out, num_speakers=num_spk, sample_rate=sr, backend=backend)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        if orig_sr == target_sr:
            return audio
        try:
            import librosa

            return librosa.resample(audio.astype(np.float32), orig_sr=orig_sr, target_sr=target_sr).astype(np.float32)
        except Exception as e:
            raise ImportError(f"重采样需要 librosa (pip install librosa)。当前: orig_sr={orig_sr}, target_sr={target_sr}, err={e}")

    def _split_long_segment(self, s0: int, s1: int, sr: int) -> List[Tuple[int, int]]:
        max_len = int(self.max_segment_sec * sr)
        step = max_len
        out = []
        i = s0
        while i < s1:
            j = min(s1, i + step)
            if (j - i) / sr >= self.min_segment_sec:
                out.append((i, j))
            i = j
        return out

    def _safe_embed(self, seg_audio: np.ndarray, sr: int) -> Optional[np.ndarray]:
        try:
            # SVEngine 内部会做 float32 与归一化
            return self.sv.embed(seg_audio, sample_rate=sr)
        except Exception:
            return None

    def _vad_segments(self, audio: np.ndarray, sr: int) -> Tuple[List[Tuple[int, int]], str]:
        # 1) 优先 silero-vad（若安装）
        try:
            from silero_vad import get_speech_timestamps  # type: ignore
            import torch  # noqa: F401

            ts = get_speech_timestamps(audio, sr)
            segments = []
            pad = int(self.pad_sec * sr)
            for t in ts:
                s = max(0, int(t.get("start", 0)) - pad)
                e = min(len(audio), int(t.get("end", 0)) + pad)
                if e > s:
                    segments.append((s, e))
            segments = self._merge_close_segments(segments, sr, max_gap_sec=self.energy_min_silence_sec)
            return segments, "silero"
        except Exception:
            pass

        # 2) fallback：能量门限切分
        segments = self._energy_vad(audio, sr)
        return segments, "energy"

    def _merge_close_segments(self, segs: List[Tuple[int, int]], sr: int, max_gap_sec: float) -> List[Tuple[int, int]]:
        if not segs:
            return []
        segs = sorted(segs, key=lambda x: x[0])
        out = [segs[0]]
        max_gap = int(max_gap_sec * sr)
        for s, e in segs[1:]:
            ps, pe = out[-1]
            if s <= pe + max_gap:
                out[-1] = (ps, max(pe, e))
            else:
                out.append((s, e))
        return out

    def _energy_vad(self, audio: np.ndarray, sr: int) -> List[Tuple[int, int]]:
        # 使用短窗 RMS 判断语音，合并成段
        win_ms = 30
        hop_ms = 10
        win = max(1, int(sr * win_ms / 1000))
        hop = max(1, int(sr * hop_ms / 1000))

        if audio.size == 0:
            return []

        # 计算帧级 RMS
        rms = []
        for i in range(0, len(audio) - win + 1, hop):
            frame = audio[i : i + win]
            rms.append(float(np.sqrt(np.mean(frame * frame))))
        if not rms:
            return []

        th = float(self.energy_threshold)
        speech = np.asarray([v > th for v in rms], dtype=np.int32)

        min_speech_frames = max(1, int(self.energy_min_speech_sec / (hop_ms / 1000.0)))
        min_sil_frames = max(1, int(self.energy_min_silence_sec / (hop_ms / 1000.0)))

        # 找连续 speech 区间
        segs: List[Tuple[int, int]] = []
        i = 0
        n = len(speech)
        while i < n:
            if speech[i] == 0:
                i += 1
                continue
            j = i
            while j < n and speech[j] == 1:
                j += 1
            if (j - i) >= min_speech_frames:
                s0 = i * hop
                s1 = min(len(audio), j * hop + win)
                segs.append((s0, s1))
            i = j

        # 合并间隔很短的段
        segs = self._merge_close_segments(segs, sr, max_gap_sec=self.energy_min_silence_sec)

        # padding
        pad = int(self.pad_sec * sr)
        padded = []
        for s, e in segs:
            s2 = max(0, s - pad)
            e2 = min(len(audio), e + pad)
            if e2 > s2:
                padded.append((s2, e2))
        padded = self._merge_close_segments(padded, sr, max_gap_sec=self.energy_min_silence_sec)
        return padded

    def _greedy_cluster(self, embs: Iterable[np.ndarray], sim_threshold: float) -> Tuple[List[int], List[float]]:
        centroids: List[np.ndarray] = []
        counts: List[int] = []
        labels: List[int] = []
        scores: List[float] = []

        for e in embs:
            if not centroids:
                centroids.append(np.asarray(e, dtype=np.float32))
                counts.append(1)
                labels.append(0)
                scores.append(1.0)
                continue

            sims = [float(np.dot(c, e)) for c in centroids]  # SVEngine 已 L2norm，点积≈cosine
            k = int(np.argmax(sims))
            best = float(sims[k])
            if best >= sim_threshold:
                labels.append(k)
                scores.append(best)
                # 更新 centroid（在线均值）
                cnt = counts[k]
                centroids[k] = (centroids[k] * cnt + e) / float(cnt + 1)
                # 归一化，保持点积≈cosine
                centroids[k] = centroids[k] / max(1e-8, float(np.linalg.norm(centroids[k])))
                counts[k] = cnt + 1
            else:
                new_id = len(centroids)
                centroids.append(np.asarray(e, dtype=np.float32))
                counts.append(1)
                labels.append(new_id)
                scores.append(1.0)

        return labels, scores

