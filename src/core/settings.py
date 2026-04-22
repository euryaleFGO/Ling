from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v.strip() if v is not None and str(v).strip() else default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class AppSettings:
    """
    项目运行时配置（只读 env；不硬编码本机路径）。

    约定：
    - 项目根目录通过本文件位置推导（src/core/settings.py → 上两级）
    - 允许用户通过环境变量覆盖
    """

    # MongoDB
    mongodb_uri: str
    mongodb_db: str

    # Message server (WebSocket)
    ws_host: str
    ws_port: int

    # Remote TTS
    remote_tts_url: str

    # 模型目录（可选覆盖）
    models_dir: Path
    asr_model_dir: Path
    asr_vad_dir: Path
    tts_model_dir: Path

    # Chroma 持久化目录
    chroma_persist_dir: Path

    @property
    def project_root(self) -> Path:
        # .../src/core/settings.py -> .../src -> 项目根
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def load() -> "AppSettings":
        project_root = Path(__file__).resolve().parents[2]

        models_dir = Path(_env_str("LIYING_MODELS_DIR", str(project_root / "models"))).expanduser()
        asr_model_dir = Path(
            _env_str("LIYING_ASR_MODEL_DIR", str(models_dir / "ASR" / "paraformer-zh-streaming"))
        ).expanduser()
        asr_vad_dir = Path(_env_str("LIYING_ASR_VAD_DIR", str(models_dir / "ASR" / "fsmn-vad"))).expanduser()
        tts_model_dir = Path(_env_str("LIYING_TTS_MODEL_DIR", str(models_dir / "TTS" / "CosyVoice2-0.5B"))).expanduser()

        chroma_dir = Path(
            _env_str("LIYING_CHROMA_DIR", str(project_root / "data" / "chroma_data"))
        ).expanduser()

        return AppSettings(
            mongodb_uri=_env_str("MONGODB_URI", "mongodb://localhost:27017"),
            mongodb_db=_env_str("MONGODB_DB", "liying_db"),
            ws_host=_env_str("LIYING_WS_HOST", "localhost"),
            ws_port=_env_int("LIYING_WS_PORT", 8765),
            remote_tts_url=_env_str("REMOTE_TTS_URL", "http://localhost:5001"),
            models_dir=models_dir,
            asr_model_dir=asr_model_dir,
            asr_vad_dir=asr_vad_dir,
            tts_model_dir=tts_model_dir,
            chroma_persist_dir=chroma_dir,
        )

