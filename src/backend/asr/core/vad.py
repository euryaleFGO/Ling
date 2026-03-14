# -*- coding: utf-8 -*-
"""
FSMN-VAD 语音活动检测模型
简化自 FunASR runtime/python/onnxruntime/funasr_onnx/vad_bin.py
"""

import os
from pathlib import Path
from typing import List, Union, Tuple, Dict

import numpy as np

try:
    import librosa
except ImportError:
    raise ImportError("请安装 librosa: pip install librosa")

from .utils.onnx_session import OrtInferSession, read_yaml
from .utils.frontend import WavFrontend, WavFrontendOnline
from .utils.vad_utils import E2EVadModel


class FsmnVAD:
    """
    FSMN-VAD 语音活动检测（离线版本）
    
    使用方法:
        vad = FsmnVAD(model_dir="models/ASR/fsmn-vad")
        segments = vad("audio.wav")  # 返回 [[start_ms, end_ms], ...]
    """

    def __init__(
        self,
        model_dir: Union[str, Path],
        batch_size: int = 1,
        device_id: Union[str, int] = "-1",
        quantize: bool = False,
        intra_op_num_threads: int = 4,
        max_end_sil: int = None,
        **kwargs,
    ):
        """
        初始化 FSMN-VAD 模型
        
        Args:
            model_dir: 模型目录路径
            batch_size: 批处理大小
            device_id: 设备ID，"-1" 表示 CPU
            quantize: 是否使用量化模型
            intra_op_num_threads: CPU 推理线程数
            max_end_sil: 最大结尾静音时长 (ms)
        """
        model_dir = Path(model_dir)
        if not model_dir.exists():
            raise FileNotFoundError(f"模型目录不存在: {model_dir}")

        model_file = model_dir / ("model_quant.onnx" if quantize else "model.onnx")
        if not model_file.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_file}")

        config_file = model_dir / "config.yaml"
        cmvn_file = model_dir / "am.mvn"
        config = read_yaml(config_file)

        self.frontend = WavFrontend(cmvn_file=str(cmvn_file), **config["frontend_conf"])
        self.ort_infer = OrtInferSession(
            str(model_file), device_id, intra_op_num_threads=intra_op_num_threads
        )
        self.batch_size = batch_size
        self.vad_scorer_config = config["model_conf"]
        self.max_end_sil = (
            max_end_sil if max_end_sil is not None else config["model_conf"]["max_end_silence_time"]
        )
        self.encoder_conf = config["encoder_conf"]

    def prepare_cache(self, in_cache: list = None) -> list:
        """准备缓存"""
        if in_cache is None:
            in_cache = []
        if len(in_cache) > 0:
            return in_cache
        
        fsmn_layers = self.encoder_conf["fsmn_layers"]
        proj_dim = self.encoder_conf["proj_dim"]
        lorder = self.encoder_conf["lorder"]
        
        for i in range(fsmn_layers):
            cache = np.zeros((1, proj_dim, lorder - 1, 1)).astype(np.float32)
            in_cache.append(cache)
        return in_cache

    def __call__(self, audio_in: Union[str, np.ndarray, List[str]], **kwargs) -> List:
        """
        执行 VAD 检测
        
        Args:
            audio_in: 音频输入（文件路径、numpy 数组或路径列表）
            
        Returns:
            检测到的语音段列表 [[start_ms, end_ms], ...]
        """
        waveform_list = self.load_data(audio_in, self.frontend.opts.frame_opts.samp_freq)
        waveform_nums = len(waveform_list)
        is_final = kwargs.get("kwargs", False)
        segments = [[]] * self.batch_size
        
        for beg_idx in range(0, waveform_nums, self.batch_size):
            vad_scorer = E2EVadModel(self.vad_scorer_config)
            end_idx = min(waveform_nums, beg_idx + self.batch_size)
            waveform = waveform_list[beg_idx:end_idx]
            feats, feats_len = self.extract_feat(waveform)
            waveform = np.array(waveform)
            param_dict = kwargs.get("param_dict", dict())
            in_cache = param_dict.get("in_cache", list())
            in_cache = self.prepare_cache(in_cache)
            
            try:
                t_offset = 0
                step = int(min(feats_len.max(), 6000))
                for t_offset in range(0, int(feats_len), min(step, feats_len - t_offset)):
                    if t_offset + step >= feats_len - 1:
                        step = feats_len - t_offset
                        is_final = True
                    else:
                        is_final = False
                    
                    feats_package = feats[:, t_offset:int(t_offset + step), :]
                    waveform_package = waveform[
                        :,
                        t_offset * 160: min(waveform.shape[-1], (int(t_offset + step) - 1) * 160 + 400),
                    ]

                    inputs = [feats_package]
                    inputs.extend(in_cache)
                    scores, out_caches = self.infer(inputs)
                    in_cache = out_caches
                    segments_part = vad_scorer(
                        scores,
                        waveform_package,
                        is_final=is_final,
                        max_end_sil=self.max_end_sil,
                        online=False,
                    )

                    if segments_part:
                        for batch_num in range(0, self.batch_size):
                            segments[batch_num] += segments_part[batch_num]

            except Exception as e:
                print(f"VAD 检测失败: {e}")
                segments = []

        return segments

    def load_data(self, wav_content: Union[str, np.ndarray, List[str]], fs: int = None) -> List:
        """加载音频数据"""
        def load_wav(path: str) -> np.ndarray:
            waveform, _ = librosa.load(path, sr=fs)
            return waveform

        if isinstance(wav_content, np.ndarray):
            return [wav_content]
        if isinstance(wav_content, str):
            return [load_wav(wav_content)]
        if isinstance(wav_content, list):
            return [load_wav(path) for path in wav_content]

        raise TypeError(f"不支持的类型: {type(wav_content)}")

    def extract_feat(self, waveform_list: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
        """提取特征"""
        feats, feats_len = [], []
        for waveform in waveform_list:
            speech, _ = self.frontend.fbank(waveform)
            feat, feat_len = self.frontend.lfr_cmvn(speech)
            feats.append(feat)
            feats_len.append(feat_len)

        feats = self._pad_feats(feats, np.max(feats_len))
        feats_len = np.array(feats_len).astype(np.int32)
        return feats, feats_len

    @staticmethod
    def _pad_feats(feats: List[np.ndarray], max_feat_len: int) -> np.ndarray:
        """填充特征"""
        def pad_feat(feat: np.ndarray, cur_len: int) -> np.ndarray:
            pad_width = ((0, max_feat_len - cur_len), (0, 0))
            return np.pad(feat, pad_width, "constant", constant_values=0)

        feat_res = [pad_feat(feat, feat.shape[0]) for feat in feats]
        feats = np.array(feat_res).astype(np.float32)
        return feats

    def infer(self, feats: List) -> Tuple[np.ndarray, np.ndarray]:
        """推理"""
        outputs = self.ort_infer(feats)
        scores, out_caches = outputs[0], outputs[1:]
        return scores, out_caches


class FsmnVADOnline:
    """
    FSMN-VAD 语音活动检测（在线流式版本）
    
    使用方法:
        vad = FsmnVADOnline(model_dir="models/ASR/fsmn-vad")
        
        param_dict = {}
        for audio_chunk in audio_stream:
            segments = vad(audio_chunk, param_dict=param_dict, is_final=False)
            for seg in segments:
                print(f"语音段: {seg[0]}ms - {seg[1]}ms")
    """

    def __init__(
        self,
        model_dir: Union[str, Path],
        batch_size: int = 1,
        device_id: Union[str, int] = "-1",
        quantize: bool = False,
        intra_op_num_threads: int = 4,
        max_end_sil: int = None,
        **kwargs,
    ):
        """
        初始化 FSMN-VAD 在线模型
        """
        model_dir = Path(model_dir)
        if not model_dir.exists():
            raise FileNotFoundError(f"模型目录不存在: {model_dir}")

        model_file = model_dir / ("model_quant.onnx" if quantize else "model.onnx")
        if not model_file.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_file}")

        config_file = model_dir / "config.yaml"
        self.cmvn_file = str(model_dir / "am.mvn")
        self.config = read_yaml(config_file)

        self.ort_infer = OrtInferSession(
            str(model_file), device_id, intra_op_num_threads=intra_op_num_threads
        )
        self.batch_size = batch_size
        self.max_end_sil = (
            max_end_sil if max_end_sil is not None else self.config["model_conf"]["max_end_silence_time"]
        )
        self.encoder_conf = self.config["encoder_conf"]

    def prepare_cache(self, in_cache: list = None) -> list:
        """准备缓存"""
        if in_cache is None:
            in_cache = []
        if len(in_cache) > 0:
            return in_cache
        
        fsmn_layers = self.encoder_conf["fsmn_layers"]
        proj_dim = self.encoder_conf["proj_dim"]
        lorder = self.encoder_conf["lorder"]
        
        for i in range(fsmn_layers):
            cache = np.zeros((1, proj_dim, lorder - 1, 1)).astype(np.float32)
            in_cache.append(cache)
        return in_cache

    def __call__(self, audio_in: np.ndarray, **kwargs) -> List:
        """
        流式 VAD 检测
        
        Args:
            audio_in: 音频数据块
            **kwargs:
                param_dict: 参数字典（包含缓存状态）
                is_final: 是否为最后一帧
                
        Returns:
            检测到的语音段列表
        """
        waveforms = np.expand_dims(audio_in, axis=0)

        param_dict: Dict = kwargs.get("param_dict", dict())
        is_final = param_dict.get("is_final", False)
        frontend: WavFrontendOnline = param_dict.get(
            "frontend", 
            WavFrontendOnline(cmvn_file=self.cmvn_file, **self.config["frontend_conf"])
        )
        
        feats, feats_len = self.extract_feat(frontend=frontend, waveforms=waveforms, is_final=is_final)
        segments = []
        
        if feats.size != 0:
            in_cache = param_dict.get("in_cache", list())
            in_cache = self.prepare_cache(in_cache)
            vad_scorer = param_dict.get("vad_scorer", E2EVadModel(self.config["model_conf"]))
            
            try:
                inputs = [feats]
                inputs.extend(in_cache)
                scores, out_caches = self.infer(inputs)
                param_dict["in_cache"] = out_caches
                waveforms = frontend.get_waveforms()
                segments = vad_scorer(
                    scores, waveforms, is_final=is_final, max_end_sil=self.max_end_sil, online=True
                )
            except Exception as e:
                print(f"VAD 检测失败: {e}")
                segments = []
        
        param_dict.update({"frontend": frontend, "vad_scorer": vad_scorer})
        return segments

    def extract_feat(
        self, frontend: WavFrontendOnline, waveforms: np.ndarray, is_final: bool = False
    ) -> Tuple[np.ndarray, np.ndarray]:
        """提取特征"""
        waveforms_lens = np.zeros(waveforms.shape[0]).astype(np.int32)
        for idx, waveform in enumerate(waveforms):
            waveforms_lens[idx] = waveform.shape[-1]

        feats, feats_len = frontend.extract_fbank(waveforms, waveforms_lens, is_final)
        return feats.astype(np.float32), feats_len.astype(np.int32)

    def infer(self, feats: List) -> Tuple[np.ndarray, np.ndarray]:
        """推理"""
        outputs = self.ort_infer(feats)
        scores, out_caches = outputs[0], outputs[1:]
        return scores, out_caches
