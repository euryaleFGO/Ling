# -*- coding: utf-8 -*-
"""
Paraformer 流式语音识别模型
简化自 FunASR runtime/python/onnxruntime/funasr_onnx/paraformer_online_bin.py
"""

import os
import json
from pathlib import Path
from typing import List, Union, Tuple

import numpy as np

try:
    import librosa
except ImportError:
    raise ImportError("请安装 librosa: pip install librosa")

from .utils.onnx_session import OrtInferSession, read_yaml
from .utils.tokenizer import TokenIDConverter, CharTokenizer, Hypothesis
from .utils.frontend import WavFrontendOnline, SinusoidalPositionEncoderOnline
from .utils.postprocess import sentence_postprocess


class ParaformerStreaming:
    """
    Paraformer 流式语音识别模型
    
    使用方法:
        model = ParaformerStreaming(model_dir="models/ASR/paraformer-zh-streaming")
        
        # 流式识别
        cache = {}
        for audio_chunk in audio_stream:
            result = model(audio_chunk, param_dict={"cache": cache, "is_final": False})
            if result:
                print(result[0]["preds"][0])
        
        # 最后一帧
        result = model(last_chunk, param_dict={"cache": cache, "is_final": True})
    """

    def __init__(
        self,
        model_dir: Union[str, Path],
        batch_size: int = 1,
        chunk_size: List[int] = None,
        device_id: Union[str, int] = "-1",
        quantize: bool = False,
        intra_op_num_threads: int = 4,
        **kwargs,
    ):
        """
        初始化 Paraformer 流式模型
        
        Args:
            model_dir: 模型目录路径
            batch_size: 批处理大小（目前只支持 1）
            chunk_size: 流式块大小 [左上下文, 当前块, 右上下文]，默认 [5, 10, 5]
            device_id: 设备ID，"-1" 表示 CPU，其他表示 GPU ID
            quantize: 是否使用量化模型
            intra_op_num_threads: CPU 推理线程数
        """
        if chunk_size is None:
            chunk_size = [5, 10, 5]
        
        model_dir = Path(model_dir)
        if not model_dir.exists():
            raise FileNotFoundError(f"模型目录不存在: {model_dir}")

        # 加载模型文件
        encoder_model_file = model_dir / ("model_quant.onnx" if quantize else "model.onnx")
        decoder_model_file = model_dir / ("decoder_quant.onnx" if quantize else "decoder.onnx")
        
        if not encoder_model_file.exists() or not decoder_model_file.exists():
            raise FileNotFoundError(
                f"模型文件不存在，请确保以下文件存在:\n"
                f"  - {encoder_model_file}\n"
                f"  - {decoder_model_file}"
            )

        # 加载配置
        config_file = model_dir / "config.yaml"
        cmvn_file = model_dir / "am.mvn"
        config = read_yaml(config_file)
        
        # 加载 Token 列表
        token_list_file = model_dir / "tokens.json"
        with open(token_list_file, "r", encoding="utf-8") as f:
            token_list = json.load(f)

        # 初始化组件
        self.converter = TokenIDConverter(token_list)
        self.tokenizer = CharTokenizer()
        self.frontend = WavFrontendOnline(cmvn_file=str(cmvn_file), **config["frontend_conf"])
        self.pe = SinusoidalPositionEncoderOnline()
        
        # 初始化 ONNX 推理会话
        self.ort_encoder_infer = OrtInferSession(
            str(encoder_model_file), device_id, intra_op_num_threads=intra_op_num_threads
        )
        self.ort_decoder_infer = OrtInferSession(
            str(decoder_model_file), device_id, intra_op_num_threads=intra_op_num_threads
        )
        
        # 配置参数
        self.batch_size = batch_size
        self.chunk_size = chunk_size
        self.encoder_output_size = config["encoder_conf"]["output_size"]
        self.fsmn_layer = config["decoder_conf"]["num_blocks"]
        self.fsmn_lorder = config["decoder_conf"]["kernel_size"] - 1
        self.fsmn_dims = config["encoder_conf"]["output_size"]
        self.feats_dims = config["frontend_conf"]["n_mels"] * config["frontend_conf"]["lfr_m"]
        self.cif_threshold = config["predictor_conf"]["threshold"]
        self.tail_threshold = config["predictor_conf"]["tail_threshold"]

    def prepare_cache(self, cache: dict = None, batch_size: int = 1) -> dict:
        """准备缓存"""
        if cache is None:
            cache = {}
        if len(cache) > 0:
            return cache
        
        cache["start_idx"] = 0
        cache["cif_hidden"] = np.zeros((batch_size, 1, self.encoder_output_size)).astype(np.float32)
        cache["cif_alphas"] = np.zeros((batch_size, 1)).astype(np.float32)
        cache["chunk_size"] = self.chunk_size
        cache["last_chunk"] = False
        cache["feats"] = np.zeros(
            (batch_size, self.chunk_size[0] + self.chunk_size[2], self.feats_dims)
        ).astype(np.float32)
        cache["decoder_fsmn"] = []
        
        for i in range(self.fsmn_layer):
            fsmn_cache = np.zeros((batch_size, self.fsmn_dims, self.fsmn_lorder)).astype(np.float32)
            cache["decoder_fsmn"].append(fsmn_cache)
        
        return cache

    def add_overlap_chunk(self, feats: np.ndarray, cache: dict) -> np.ndarray:
        """添加重叠块"""
        if len(cache) == 0:
            return feats
        
        overlap_feats = np.concatenate((cache["feats"], feats), axis=1)
        
        if cache["is_final"]:
            cache["feats"] = overlap_feats[:, -self.chunk_size[0]:, :]
            if not cache["last_chunk"]:
                padding_length = sum(self.chunk_size) - overlap_feats.shape[1]
                overlap_feats = np.pad(overlap_feats, ((0, 0), (0, padding_length), (0, 0)))
        else:
            cache["feats"] = overlap_feats[:, -(self.chunk_size[0] + self.chunk_size[2]):, :]
        
        return overlap_feats

    def __call__(self, audio_in: np.ndarray, **kwargs) -> List[dict]:
        """
        流式语音识别
        
        Args:
            audio_in: 音频数据，numpy 数组，16kHz 采样率
            **kwargs:
                param_dict: 参数字典，包含:
                    - cache: 缓存字典
                    - is_final: 是否为最后一帧
        
        Returns:
            识别结果列表，每个元素为字典，包含 "preds" 键
        """
        waveforms = np.expand_dims(audio_in, axis=0)
        param_dict = kwargs.get("param_dict", dict())
        is_final = param_dict.get("is_final", False)
        cache = param_dict.get("cache", dict())
        asr_res = []

        # 处理最后一个短块
        if waveforms.shape[1] < 16 * 60 and is_final and len(cache) > 0:
            cache["last_chunk"] = True
            feats = cache["feats"]
            feats_len = np.array([feats.shape[1]]).astype(np.int32)
            asr_res = self.infer(feats, feats_len, cache)
            return asr_res

        # 特征提取
        feats, feats_len = self.extract_feat(waveforms, is_final)
        
        if feats.shape[1] != 0:
            feats *= self.encoder_output_size ** 0.5
            cache = self.prepare_cache(cache)
            cache["is_final"] = is_final

            # fbank -> 位置编码 -> 重叠块
            feats = self.pe.forward(feats, cache["start_idx"])
            cache["start_idx"] += feats.shape[1]
            
            if is_final:
                if feats.shape[1] + self.chunk_size[2] <= self.chunk_size[1]:
                    cache["last_chunk"] = True
                    feats = self.add_overlap_chunk(feats, cache)
                else:
                    # 第一个块
                    feats_chunk1 = self.add_overlap_chunk(feats[:, :self.chunk_size[1], :], cache)
                    feats_len = np.array([feats_chunk1.shape[1]]).astype(np.int32)
                    asr_res_chunk1 = self.infer(feats_chunk1, feats_len, cache)

                    # 最后一个块
                    cache["last_chunk"] = True
                    feats_chunk2 = self.add_overlap_chunk(
                        feats[:, -(feats.shape[1] + self.chunk_size[2] - self.chunk_size[1]):, :],
                        cache,
                    )
                    feats_len = np.array([feats_chunk2.shape[1]]).astype(np.int32)
                    asr_res_chunk2 = self.infer(feats_chunk2, feats_len, cache)

                    # 合并结果
                    asr_res_chunk = asr_res_chunk1 + asr_res_chunk2
                    res = {}
                    for pred in asr_res_chunk:
                        for key, value in pred.items():
                            if key in res:
                                res[key][0] += value[0]
                                res[key][1].extend(value[1])
                            else:
                                res[key] = [value[0], value[1]]
                    return [res]
            else:
                feats = self.add_overlap_chunk(feats, cache)

            feats_len = np.array([feats.shape[1]]).astype(np.int32)
            asr_res = self.infer(feats, feats_len, cache)

        return asr_res

    def infer(self, feats: np.ndarray, feats_len: np.ndarray, cache: dict) -> List[dict]:
        """推理"""
        # 编码器前向
        enc_input = [feats, feats_len]
        enc, enc_lens, cif_alphas = self.ort_encoder_infer(enc_input)

        # 预测器前向
        acoustic_embeds, acoustic_embeds_len = self.cif_search(enc, cif_alphas, cache)

        # 解码器前向
        asr_res = []
        if acoustic_embeds.shape[1] > 0:
            dec_input = [enc, enc_lens, acoustic_embeds, acoustic_embeds_len]
            dec_input.extend(cache["decoder_fsmn"])
            dec_output = self.ort_decoder_infer(dec_input)
            logits, sample_ids = dec_output[0], dec_output[1]
            cache["decoder_fsmn"] = dec_output[2:]
            cache["decoder_fsmn"] = [
                item[:, :, -self.fsmn_lorder:] for item in cache["decoder_fsmn"]
            ]

            preds = self.decode(logits, acoustic_embeds_len)
            for pred in preds:
                pred = sentence_postprocess(pred)
                asr_res.append({"preds": pred})

        return asr_res

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

    def extract_feat(
        self, waveforms: np.ndarray, is_final: bool = False
    ) -> Tuple[np.ndarray, np.ndarray]:
        """提取特征"""
        waveforms_lens = np.zeros(waveforms.shape[0]).astype(np.int32)
        for idx, waveform in enumerate(waveforms):
            waveforms_lens[idx] = waveform.shape[-1]

        feats, feats_len = self.frontend.extract_fbank(waveforms, waveforms_lens, is_final)
        return feats.astype(np.float32), feats_len.astype(np.int32)

    def decode(self, am_scores: np.ndarray, token_nums: int) -> List[str]:
        """解码"""
        return [
            self.decode_one(am_score, token_num)
            for am_score, token_num in zip(am_scores, token_nums)
        ]

    def decode_one(self, am_score: np.ndarray, valid_token_num: int) -> List[str]:
        """解码单个"""
        yseq = am_score.argmax(axis=-1)
        score = am_score.max(axis=-1)
        score = np.sum(score, axis=-1)

        yseq = np.array([1] + yseq.tolist() + [2])
        hyp = Hypothesis(yseq=yseq, score=score)

        last_pos = -1
        token_int = hyp.yseq[1:last_pos].tolist()
        token_int = list(filter(lambda x: x not in (0, 2), token_int))
        token = self.converter.ids2tokens(token_int)
        token = token[:valid_token_num]
        
        return token

    def cif_search(self, hidden: np.ndarray, alphas: np.ndarray, cache: dict = None):
        """CIF 搜索"""
        batch_size, len_time, hidden_size = hidden.shape
        token_length = []
        list_frames = []
        cache_alphas = []
        cache_hiddens = []
        
        alphas[:, :self.chunk_size[0]] = 0.0
        alphas[:, sum(self.chunk_size[:2]):] = 0.0
        
        if cache is not None and "cif_alphas" in cache and "cif_hidden" in cache:
            hidden = np.concatenate((cache["cif_hidden"], hidden), axis=1)
            alphas = np.concatenate((cache["cif_alphas"], alphas), axis=1)
        
        if cache is not None and "last_chunk" in cache and cache["last_chunk"]:
            tail_hidden = np.zeros((batch_size, 1, hidden_size)).astype(np.float32)
            tail_alphas = np.array([[self.tail_threshold]]).astype(np.float32)
            tail_alphas = np.tile(tail_alphas, (batch_size, 1))
            hidden = np.concatenate((hidden, tail_hidden), axis=1)
            alphas = np.concatenate((alphas, tail_alphas), axis=1)

        len_time = alphas.shape[1]
        
        for b in range(batch_size):
            integrate = 0.0
            frames = np.zeros(hidden_size).astype(np.float32)
            list_frame = []
            
            for t in range(len_time):
                alpha = alphas[b][t]
                if alpha + integrate < self.cif_threshold:
                    integrate += alpha
                    frames += alpha * hidden[b][t]
                else:
                    frames += (self.cif_threshold - integrate) * hidden[b][t]
                    list_frame.append(frames)
                    integrate += alpha
                    integrate -= self.cif_threshold
                    frames = integrate * hidden[b][t]

            cache_alphas.append(integrate)
            if integrate > 0.0:
                cache_hiddens.append(frames / integrate)
            else:
                cache_hiddens.append(frames)

            token_length.append(len(list_frame))
            list_frames.append(list_frame)

        max_token_len = max(token_length)
        list_ls = []
        
        for b in range(batch_size):
            pad_frames = np.zeros((max_token_len - token_length[b], hidden_size)).astype(np.float32)
            if token_length[b] == 0:
                list_ls.append(pad_frames)
            else:
                list_ls.append(np.concatenate((list_frames[b], pad_frames), axis=0))

        cache["cif_alphas"] = np.stack(cache_alphas, axis=0)
        cache["cif_alphas"] = np.expand_dims(cache["cif_alphas"], axis=0)
        cache["cif_hidden"] = np.stack(cache_hiddens, axis=0)
        cache["cif_hidden"] = np.expand_dims(cache["cif_hidden"], axis=0)

        return np.stack(list_ls, axis=0).astype(np.float32), np.stack(token_length, axis=0).astype(np.int32)

    def reset(self):
        """重置状态（用于新一轮识别）"""
        self.frontend.cache_reset()
