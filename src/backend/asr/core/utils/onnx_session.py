# -*- coding: utf-8 -*-
"""
ONNX Runtime 推理会话封装
简化自 FunASR runtime/python/onnxruntime/funasr_onnx/utils/utils.py
"""

import warnings
from pathlib import Path
from typing import List, Union
import numpy as np

try:
    from onnxruntime import (
        GraphOptimizationLevel,
        InferenceSession,
        SessionOptions,
        get_available_providers,
        get_device,
    )
except ImportError:
    raise ImportError("请安装 onnxruntime: pip install onnxruntime 或 pip install onnxruntime-gpu")


class ONNXRuntimeError(Exception):
    """ONNX Runtime 推理错误"""
    pass


class OrtInferSession:
    """ONNX Runtime 推理会话"""
    
    def __init__(
        self,
        model_file: str,
        device_id: Union[str, int] = "-1",
        intra_op_num_threads: int = 4
    ):
        """
        初始化 ONNX Runtime 推理会话
        
        Args:
            model_file: ONNX 模型文件路径
            device_id: 设备ID，"-1" 表示 CPU，其他表示 GPU ID
            intra_op_num_threads: CPU 推理线程数
        """
        device_id = str(device_id)
        
        # 验证模型文件
        self._verify_model(model_file)
        
        # 配置会话选项
        sess_opt = SessionOptions()
        sess_opt.intra_op_num_threads = intra_op_num_threads
        sess_opt.log_severity_level = 4
        sess_opt.enable_cpu_mem_arena = False
        sess_opt.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL

        # 配置执行提供器
        cuda_ep = "CUDAExecutionProvider"
        cuda_provider_options = {
            "device_id": device_id,
            "arena_extend_strategy": "kNextPowerOfTwo",
            "cudnn_conv_algo_search": "EXHAUSTIVE",
            "do_copy_in_default_stream": "true",
        }
        cpu_ep = "CPUExecutionProvider"
        cpu_provider_options = {
            "arena_extend_strategy": "kSameAsRequested",
        }

        EP_list = []
        if device_id != "-1" and get_device() == "GPU" and cuda_ep in get_available_providers():
            EP_list = [(cuda_ep, cuda_provider_options)]
        EP_list.append((cpu_ep, cpu_provider_options))

        self.session = InferenceSession(model_file, sess_options=sess_opt, providers=EP_list)

        # 检查 GPU 是否可用
        if device_id != "-1" and cuda_ep not in self.session.get_providers():
            warnings.warn(
                f"{cuda_ep} 不可用，将使用 {cpu_ep} 进行推理。\n"
                "请确保安装的 onnxruntime-gpu 版本与 CUDA/cuDNN 版本匹配。",
                RuntimeWarning,
            )

    def __call__(self, input_content: List[np.ndarray], run_options=None) -> np.ndarray:
        """执行推理"""
        input_dict = dict(zip(self.get_input_names(), input_content))
        try:
            return self.session.run(self.get_output_names(), input_dict, run_options)
        except Exception as e:
            raise ONNXRuntimeError("ONNX Runtime 推理失败") from e

    def get_input_names(self) -> List[str]:
        """获取输入名称列表"""
        return [v.name for v in self.session.get_inputs()]

    def get_output_names(self) -> List[str]:
        """获取输出名称列表"""
        return [v.name for v in self.session.get_outputs()]

    @staticmethod
    def _verify_model(model_path: str):
        """验证模型文件"""
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        if not model_path.is_file():
            raise FileExistsError(f"路径不是文件: {model_path}")


def read_yaml(yaml_path: Union[str, Path]) -> dict:
    """读取 YAML 配置文件"""
    import yaml
    
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileExistsError(f"配置文件不存在: {yaml_path}")

    with open(str(yaml_path), "rb") as f:
        data = yaml.load(f, Loader=yaml.Loader)
    return data
