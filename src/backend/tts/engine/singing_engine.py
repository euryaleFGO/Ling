"""
DiffSinger 歌声合成引擎封装

通过 subprocess 调用独立的 DiffSinger Python 环境，
避免与主项目的依赖冲突。
"""

import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional, Generator, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class DiffSingerEngine:
    """
    DiffSinger 歌声合成引擎

    通过 subprocess 调用独立的 DiffSinger 推理脚本，
    实现与主项目依赖隔离。
    """

    def __init__(
        self,
        diffsinger_root: str = "",
        exp_name: str = "opencpop",
        vocoder_ckpt: str = "",
        device: str = "cuda",
        sample_rate: int = 44100,
    ):
        """
        初始化 DiffSinger 引擎

        Args:
            diffsinger_root: DiffSinger 仓库根目录路径
            exp_name: 实验名称（模型名）
            vocoder_ckpt: NSF-HiFiGAN vocoder 模型路径
            device: 推理设备 (cuda/cpu)
            sample_rate: 输出采样率
        """
        self.diffsinger_root = Path(diffsinger_root) if diffsinger_root else None
        self.exp_name = exp_name
        self.vocoder_ckpt = vocoder_ckpt
        self.device = device
        self.sample_rate = sample_rate
        self._available = False

        # 推理脚本路径（内嵌于本模块）
        self._script_dir = Path(__file__).parent.parent / "singing" / "scripts"
        self._infer_script = self._script_dir / "infer_singing.py"

        # 检查可用性
        self._check_availability()

    def _check_availability(self):
        """检查 DiffSinger 是否可用"""
        if not self.diffsinger_root or not self.diffsinger_root.exists():
            logger.info("DiffSinger 根目录未配置或不存在，歌声合成功能不可用")
            return

        if not self._infer_script.exists():
            logger.warning(f"推理脚本不存在: {self._infer_script}")
            return

        self._available = True
        logger.info(f"DiffSinger 引擎初始化成功 (root={self.diffsinger_root}, exp={self.exp_name})")

    def is_available(self) -> bool:
        """检查引擎是否可用"""
        return self._available

    def generate_singing(
        self,
        ds_params: dict,
        output_path: Optional[str] = None,
    ) -> Optional[np.ndarray]:
        """
        生成歌声音频（同步）

        Args:
            ds_params: DiffSinger DS 格式参数
            output_path: 输出 WAV 文件路径（可选）

        Returns:
            numpy 音频数组 (float32, -1~1)，失败返回 None
        """
        if not self._available:
            logger.error("DiffSinger 引擎不可用")
            return None

        # 准备输出路径
        auto_output = output_path is None
        if output_path is None:
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"singing_{uuid.uuid4().hex[:8]}.wav"
            )

        # 写入参数文件
        params_path = os.path.join(tempfile.gettempdir(), f"ds_params_{uuid.uuid4().hex[:8]}.json")
        try:
            with open(params_path, 'w', encoding='utf-8') as f:
                json.dump(ds_params, f, ensure_ascii=False, indent=2)

            # 调用子进程
            cmd = [
                self._get_python_path(),
                str(self._infer_script),
                "--params", params_path,
                "--output", output_path,
                "--diffsinger-root", str(self.diffsinger_root),
                "--exp-name", self.exp_name,
                "--device", self.device,
            ]

            if self.vocoder_ckpt:
                cmd.extend(["--vocoder-ckpt", self.vocoder_ckpt])

            logger.info(f"调用 DiffSinger: {' '.join(cmd[:6])}...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
            )

            if result.returncode != 0:
                logger.error(f"DiffSinger 推理失败:\n{result.stderr}")
                return None

            # 读取生成的 WAV
            if os.path.exists(output_path):
                result = self._load_wav(output_path)
                if result is not None:
                    audio, sr = result
                    return audio
                return None
            else:
                logger.error(f"输出文件不存在: {output_path}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("DiffSinger 推理超时 (120s)")
            return None
        except Exception as e:
            logger.error(f"DiffSinger 推理异常: {e}")
            return None
        finally:
            # 清理临时参数文件
            if os.path.exists(params_path):
                os.remove(params_path)
            # 清理自动生成的临时 WAV
            if auto_output and output_path and os.path.exists(output_path):
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

    def generate_singing_streaming(
        self,
        ds_params: dict,
        output_path: Optional[str] = None,
    ) -> Generator[Tuple[np.ndarray, int, int], None, None]:
        """
        生成歌声音频（流式）

        对于 SVS，通常一次性生成整段音频，这里将单次结果作为一个 chunk 返回。

        Yields:
            (audio_data, segment_index, total_segments)
        """
        audio = self.generate_singing(ds_params, output_path)
        if audio is not None:
            yield (audio, 0, 1)

    def _get_python_path(self) -> str:
        """获取 Python 解释器路径"""
        # 优先使用 DiffSinger 环境的 Python
        if self.diffsinger_root:
            # 检查 venv
            venv_python = self.diffsinger_root / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists():
                return str(venv_python)
            venv_python = self.diffsinger_root / ".venv" / "bin" / "python"
            if venv_python.exists():
                return str(venv_python)
            # 检查 conda env
            conda_python = self.diffsinger_root / "env" / "python.exe"
            if conda_python.exists():
                return str(conda_python)

        # 回退到当前 Python
        import sys
        return sys.executable

    def _load_wav(self, path: str) -> Optional[Tuple[np.ndarray, int]]:
        """加载 WAV 文件为 numpy 数组，返回 (audio, sample_rate) 元组"""
        try:
            import scipy.io.wavfile as wavfile
            sr, data = wavfile.read(path)

            # 转换为 float32, -1~1
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0

            # 如果是多声道，取第一个声道
            if len(data.shape) > 1:
                data = data[:, 0]

            return (data, sr)
        except Exception as e:
            logger.error(f"加载 WAV 失败: {e}")
            return None

    def cleanup(self):
        """清理资源"""
        self._available = False
        logger.info("DiffSinger 引擎已清理")


class DiffSingerRemoteClient:
    """
    DiffSinger 远程客户端

    通过 HTTP 调用远程 DiffSinger 服务。
    适用于 DiffSinger 部署在独立服务器上的场景。
    """

    def __init__(self, base_url: str, timeout: int = 120):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._available = False

    def is_available(self) -> bool:
        """检查远程服务是否可用"""
        try:
            import requests
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def generate_singing(self, ds_params: dict, output_path: Optional[str] = None) -> Optional[np.ndarray]:
        """调用远程歌声合成"""
        try:
            import requests
            resp = requests.post(
                f"{self.base_url}/sing",
                json=ds_params,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                # 保存到文件
                if output_path:
                    with open(output_path, 'wb') as f:
                        f.write(resp.content)

                # 转为 numpy（通过 wave 模块根据 sampwidth 判断 dtype）
                import io
                import wave as _wave
                with _wave.open(io.BytesIO(resp.content), 'rb') as wf:
                    sampwidth = wf.getsampwidth()
                    raw = wf.readframes(wf.getnframes())
                if sampwidth == 2:
                    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    data = np.frombuffer(raw, dtype=np.float32)
                else:
                    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                return data
            else:
                logger.error(f"远程歌声合成失败: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"远程歌声合成异常: {e}")
            return None
