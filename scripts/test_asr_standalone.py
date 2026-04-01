#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立测试 ASR 模块（不依赖 GUI/Agent/TTS）。

用法示例:
  1) 音频文件离线识别
     python scripts/test_asr_standalone.py file --audio data/test.wav

  2) 麦克风离线识别（录制 4 秒后识别）
     python scripts/test_asr_standalone.py mic-offline --seconds 4

  3) 麦克风流式识别（实时输出中间结果，结束输出 final）
     python scripts/test_asr_standalone.py mic-stream --seconds 6
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
from pathlib import Path

import numpy as np

# 将 src 加入路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from backend.asr import ASREngine, ASRConfig


def _default_model_dir() -> str:
    p = PROJECT_ROOT / "models" / "ASR" / "paraformer-zh-streaming"
    return str(p)


def _default_vad_model() -> str:
    p = PROJECT_ROOT / "models" / "ASR" / "fsmn-vad"
    return str(p)


def build_engine(model_dir: str, vad_model: str, device: str) -> ASREngine:
    cfg = ASRConfig(
        model_dir=model_dir,
        vad_model=vad_model,
        device=device,
        use_vad=True,
        chunk_size=[0, 6, 3],
    )
    return ASREngine(config=cfg)


def run_file_mode(engine: ASREngine, audio_path: str) -> int:
    p = Path(audio_path)
    if not p.exists():
        print(f"[ERROR] 音频文件不存在: {p}")
        return 2

    t0 = time.perf_counter()
    text = engine.recognize_file(str(p)).strip()
    dt = time.perf_counter() - t0
    print("\n=== ASR 文件离线识别结果 ===")
    print(f"文件: {p}")
    print(f"耗时: {dt:.2f}s")
    print(f"文本: {text or '<empty>'}")
    return 0


def _record_mic(seconds: float, sample_rate: int) -> np.ndarray:
    try:
        import sounddevice as sd
    except ImportError as e:
        raise RuntimeError("请先安装 sounddevice: pip install sounddevice") from e

    frames = int(seconds * sample_rate)
    print(f"\n[ASR] 开始录音: {seconds:.1f}s, sr={sample_rate}")
    print("[ASR] 请开始说话...")
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    print("[ASR] 录音结束")
    return audio.reshape(-1)


def run_mic_offline_mode(engine: ASREngine, seconds: float, sample_rate: int) -> int:
    audio = _record_mic(seconds=seconds, sample_rate=sample_rate)

    t0 = time.perf_counter()
    text = engine.recognize_audio(audio, sample_rate=sample_rate).strip()
    dt = time.perf_counter() - t0

    print("\n=== ASR 麦克风离线识别结果 ===")
    print(f"耗时: {dt:.2f}s")
    print(f"文本: {text or '<empty>'}")
    return 0


def run_mic_stream_mode(engine: ASREngine, seconds: float, sample_rate: int) -> int:
    try:
        import sounddevice as sd
    except ImportError as e:
        raise RuntimeError("请先安装 sounddevice: pip install sounddevice") from e

    chunk = engine.get_chunk_stride()
    last_text = ""
    partial_history: list[str] = []
    audio_chunks: list[np.ndarray] = []
    overflow_count = 0
    q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=128)

    print(f"\n[ASR] 流式测试开始: {seconds:.1f}s, sr={sample_rate}, chunk={chunk}")
    print("[ASR] 请开始说话...")

    engine.start_stream()
    t0 = time.perf_counter()

    def on_audio(indata, frames, time_info, status):
        nonlocal overflow_count
        if status:
            # 仅计数，避免在回调线程频繁打印阻塞音频采集
            overflow_count += 1
        pcm = indata[:, 0].astype(np.float32).copy()
        try:
            q.put_nowait(pcm)
        except queue.Full:
            # 队列满说明主线程处理跟不上，丢弃当前块并计数
            overflow_count += 1

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        blocksize=chunk,
        callback=on_audio,
    ):
        while time.perf_counter() - t0 < seconds:
            # 在主线程做推理，避免阻塞音频回调线程
            while True:
                try:
                    pcm = q.get_nowait()
                except queue.Empty:
                    break
                audio_chunks.append(pcm)
                part = engine.feed_audio(pcm).strip()
                if part:
                    partial_history.append(part)
                    if part != last_text:
                        last_text = part
                        print(f"[PARTIAL] {part}")
            time.sleep(0.05)

    # 结束前尽量清空剩余队列，避免尾部语音丢失
    while True:
        try:
            pcm = q.get_nowait()
        except queue.Empty:
            break
        audio_chunks.append(pcm)
        part = engine.feed_audio(pcm).strip()
        if part:
            partial_history.append(part)
            if part != last_text:
                last_text = part
                print(f"[PARTIAL] {part}")

    final = engine.end_stream().strip()

    # 兜底1：流式 final 为空时，取最长 partial 作为临时最终文本
    if not final and partial_history:
        final = max((p.strip() for p in partial_history if p.strip()), key=len, default="")

    # 兜底2：仍为空则对整段音频做一次离线识别（会慢一些，但结果更稳）
    if not final and audio_chunks:
        full_audio = np.concatenate(audio_chunks)
        if len(full_audio) > int(0.8 * sample_rate):
            final = engine.recognize_audio(full_audio, sample_rate=sample_rate).strip()

    dt = time.perf_counter() - t0

    print("\n=== ASR 麦克风流式识别结果 ===")
    print(f"总时长: {dt:.2f}s")
    print(f"overflow计数: {overflow_count}")
    print(f"最终文本: {final or '<empty>'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="独立测试 ASR 模块")
    parser.add_argument(
        "mode",
        choices=["file", "mic-offline", "mic-stream"],
        help="测试模式",
    )
    parser.add_argument("--audio", default="", help="音频文件路径（mode=file 时必填）")
    parser.add_argument("--seconds", type=float, default=5.0, help="麦克风录音/流式时长")
    parser.add_argument("--sample-rate", type=int, default=16000, help="采样率")
    parser.add_argument("--model-dir", default=_default_model_dir(), help="ASR 模型目录")
    parser.add_argument("--vad-model", default=_default_vad_model(), help="VAD 模型目录")
    parser.add_argument("--device", default="cpu", help="推理设备，如 cpu / cuda:0")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 60)
    print("ASR Standalone Test")
    print("=" * 60)
    print(f"mode={args.mode}, device={args.device}")
    print(f"model={args.model_dir}")

    engine = build_engine(
        model_dir=args.model_dir,
        vad_model=args.vad_model,
        device=args.device,
    )

    if args.mode == "file":
        if not args.audio:
            print("[ERROR] mode=file 时必须传 --audio")
            return 2
        return run_file_mode(engine, args.audio)

    if args.mode == "mic-offline":
        return run_mic_offline_mode(engine, seconds=args.seconds, sample_rate=args.sample_rate)

    if args.mode == "mic-stream":
        return run_mic_stream_mode(engine, seconds=args.seconds, sample_rate=args.sample_rate)

    print(f"[ERROR] 未知模式: {args.mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
