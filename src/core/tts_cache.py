# -*- coding: utf-8 -*-
"""
TTS 缓存模块

使用 LRU 缓存策略缓存常用短语的 TTS 音频，减少重复合成
"""

import hashlib
import json
import base64
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np

from core.log import log


class TTSCache:
    """TTS 缓存类（LRU 策略）"""
    
    def __init__(
        self,
        max_size: int = 100,
        cache_dir: Optional[Path] = None,
        enable_disk_cache: bool = False,
    ):
        """
        初始化 TTS 缓存
        
        Args:
            max_size: 最大缓存数量
            cache_dir: 磁盘缓存目录（可选）
            enable_disk_cache: 是否启用磁盘缓存
        """
        self.max_size = max_size
        self.cache_dir = cache_dir
        self.enable_disk_cache = enable_disk_cache
        
        # 内存缓存（LRU）
        self._memory_cache: OrderedDict[str, Tuple[np.ndarray, int, dict]] = OrderedDict()
        
        # 统计信息
        self._hits = 0
        self._misses = 0
        self._total_requests = 0
        
        # 初始化磁盘缓存目录
        if self.enable_disk_cache and self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            log.debug(f"[TTS 缓存] 磁盘缓存目录: {self.cache_dir}")
    
    def _generate_key(self, text: str, spk_id: Optional[str] = None, **kwargs) -> str:
        """
        生成缓存键
        
        Args:
            text: 文本
            spk_id: 说话人 ID
            **kwargs: 其他参数
        
        Returns:
            缓存键（MD5 哈希）
        """
        # 组合所有参数
        key_parts = [text]
        if spk_id:
            key_parts.append(f"spk:{spk_id}")
        
        # 添加其他参数
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        
        # 生成 MD5 哈希
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(
        self,
        text: str,
        spk_id: Optional[str] = None,
        **kwargs
    ) -> Optional[Tuple[np.ndarray, int, dict]]:
        """
        从缓存获取音频
        
        Args:
            text: 文本
            spk_id: 说话人 ID
            **kwargs: 其他参数
        
        Returns:
            (audio, sample_rate, metadata) 或 None
        """
        self._total_requests += 1
        key = self._generate_key(text, spk_id, **kwargs)
        
        # 先查内存缓存
        if key in self._memory_cache:
            self._hits += 1
            # 移到最后（LRU）
            self._memory_cache.move_to_end(key)
            log.debug(f"[TTS 缓存] 内存命中: {text[:20]}...")
            return self._memory_cache[key]
        
        # 再查磁盘缓存
        if self.enable_disk_cache and self.cache_dir:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)

                    # 从 JSON 反序列化音频数据
                    audio_array = np.frombuffer(
                        base64.b64decode(cache_data["audio_base64"]),
                        dtype=np.dtype(cache_data["dtype"])
                    )
                    data = (audio_array, cache_data["sample_rate"], cache_data.get("metadata", {}))

                    # 加载到内存缓存
                    self._put_memory(key, data)
                    self._hits += 1
                    log.debug(f"[TTS 缓存] 磁盘命中: {text[:20]}...")
                    return data
                except Exception as e:
                    log.warn(f"[TTS 缓存] 磁盘缓存加载失败: {e}")
        
        # 未命中
        self._misses += 1
        log.debug(f"[TTS 缓存] 未命中: {text[:20]}...")
        return None
    
    def put(
        self,
        text: str,
        audio: np.ndarray,
        sample_rate: int,
        spk_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        **kwargs
    ):
        """
        将音频放入缓存
        
        Args:
            text: 文本
            audio: 音频数据
            sample_rate: 采样率
            spk_id: 说话人 ID
            metadata: 元数据
            **kwargs: 其他参数
        """
        key = self._generate_key(text, spk_id, **kwargs)
        data = (audio, sample_rate, metadata or {})
        
        # 放入内存缓存
        self._put_memory(key, data)
        
        # 放入磁盘缓存
        if self.enable_disk_cache and self.cache_dir:
            try:
                # 序列化为 JSON（安全，无反序列化漏洞）
                cache_data = {
                    "audio_base64": base64.b64encode(audio.tobytes()).decode(),
                    "sample_rate": sample_rate,
                    "dtype": str(audio.dtype),
                    "metadata": metadata or {}
                }
                cache_file = self.cache_dir / f"{key}.json"
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f)
                log.debug(f"[TTS 缓存] 已保存到磁盘: {text[:20]}...")
            except Exception as e:
                log.warn(f"[TTS 缓存] 磁盘缓存保存失败: {e}")
    
    def _put_memory(self, key: str, data: Tuple[np.ndarray, int, dict]):
        """将数据放入内存缓存（LRU）"""
        # 如果已存在，先删除
        if key in self._memory_cache:
            del self._memory_cache[key]
        
        # 添加到末尾
        self._memory_cache[key] = data
        
        # 如果超过最大大小，删除最旧的
        while len(self._memory_cache) > self.max_size:
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]
            log.debug(f"[TTS 缓存] LRU 淘汰: {oldest_key}")
    
    def preload_common_phrases(
        self,
        phrases: List[str],
        tts_engine,
        spk_id: Optional[str] = None,
        **kwargs
    ):
        """
        预加载常用短语
        
        Args:
            phrases: 短语列表
            tts_engine: TTS 引擎
            spk_id: 说话人 ID
            **kwargs: 其他参数
        """
        log.info(f"[TTS 缓存] 预加载 {len(phrases)} 个常用短语...")
        
        for phrase in phrases:
            # 检查是否已缓存
            if self.get(phrase, spk_id, **kwargs):
                continue
            
            try:
                # 合成音频
                audio = tts_engine.generate_audio(phrase, **kwargs)
                sample_rate = getattr(tts_engine, 'sample_rate', 16000)
                
                # 放入缓存
                self.put(phrase, audio, sample_rate, spk_id, **kwargs)
                log.debug(f"[TTS 缓存] 预加载: {phrase}")
            except Exception as e:
                log.warn(f"[TTS 缓存] 预加载失败 '{phrase}': {e}")
        
        log.info(f"[TTS 缓存] 预加载完成，缓存大小: {len(self._memory_cache)}")
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        hit_rate = self._hits / self._total_requests if self._total_requests > 0 else 0.0
        
        return {
            "size": len(self._memory_cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": self._total_requests,
            "hit_rate": hit_rate,
        }
    
    def print_stats(self):
        """打印缓存统计信息"""
        stats = self.get_stats()
        
        log.info("\n" + "=" * 60)
        log.info("TTS 缓存统计")
        log.info("=" * 60)
        log.info(f"缓存大小: {stats['size']}/{stats['max_size']}")
        log.info(f"总请求: {stats['total_requests']}")
        log.info(f"命中: {stats['hits']}")
        log.info(f"未命中: {stats['misses']}")
        log.info(f"命中率: {stats['hit_rate']*100:.1f}%")
        log.info("=" * 60)
    
    def clear(self):
        """清空缓存"""
        self._memory_cache.clear()
        self._hits = 0
        self._misses = 0
        self._total_requests = 0
        log.info("[TTS 缓存] 已清空")
    
    def clear_disk_cache(self):
        """清空磁盘缓存"""
        if self.enable_disk_cache and self.cache_dir and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    log.warn(f"[TTS 缓存] 删除磁盘缓存失败 {cache_file}: {e}")
            log.info("[TTS 缓存] 磁盘缓存已清空")


# 全局 TTS 缓存实例
_global_tts_cache: Optional[TTSCache] = None


def get_global_tts_cache(
    max_size: int = 100,
    cache_dir: Optional[Path] = None,
    enable_disk_cache: bool = False,
) -> TTSCache:
    """获取全局 TTS 缓存实例"""
    global _global_tts_cache
    if _global_tts_cache is None:
        _global_tts_cache = TTSCache(
            max_size=max_size,
            cache_dir=cache_dir,
            enable_disk_cache=enable_disk_cache,
        )
    return _global_tts_cache


def reset_global_tts_cache():
    """重置全局 TTS 缓存实例"""
    global _global_tts_cache
    _global_tts_cache = None
