#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音频采集 + VAD 端点检测 —— 论文配图 / 截屏演示脚本

本脚本对应论文章节中「麦克风连续采集、RMS/Silero VAD、预缓冲、hangover、flush_buffer」等描述，
用于在终端输出可截图的配置说明与（可选）一次录音过程的调试日志。

用法（在项目根目录、Liying conda 环境下）：

  1）仅打印当前 VAD/音频参数（无需麦克风，适合截“参数表”类配图说明）
     conda activate "F:\\envs\\Liying"
     python scripts/demo_vad_audio_capture.py

  2）打印参数 + 录一段直到静音（需麦克风；会输出 [VAD] / [AudioIO] 调试行，适合截“运行过程”）
     python scripts/demo_vad_audio_capture.py --record

  3）切换 VAD 后端或预设
     python scripts/demo_vad_audio_capture.py --backend silero --preset conservative --record

说明：
  - 调试日志依赖 core.log 的 debug 输出，本脚本会调用 set_debug(True)。
  - 若未安装 sounddevice，请先: pip install sounddevice
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.audio_io import AudioConfig, AudioInput  # noqa: E402
from core.log import set_debug  # noqa: E402
from core.vad import VADConfig  # noqa: E402


def _print_config(vc: VADConfig, ac: AudioConfig) -> None:
    print("=" * 60)
    print("  音频采集 / VAD 配置（与 src/core/audio_io.py、src/core/vad.py 一致）")
    print("=" * 60)
    print(f"  采样率 sample_rate     : {ac.sample_rate} Hz")
    print(f"  声道 channels           : {ac.channels}")
    print(f"  样本类型 dtype          : {ac.dtype}（归一化到约 [-1, 1]）")
    print(f"  每块 chunk_size(样本)   : {ac.chunk_size}")
    print("-" * 60)
    print(f"  VAD 后端 backend        : {vc.backend}（rms=能量门限 / silero=神经网络）")
    print(f"  静音判停 silence_duration: {vc.silence_duration} s")
    print(f"  最少连续语音块 min_speech_chunks: {vc.min_speech_chunks}")
    print(f"  尾音延续 hangover_chunks: {vc.hangover_chunks}")
    print(f"  预缓冲回溯 pre_buffer_chunks: {vc.pre_buffer_chunks}")
    if vc.backend == "rms":
        print(f"  RMS 静音阈值 silence_threshold: {vc.silence_threshold}")
        print(f"  噪声底噪平滑 noise_floor_alpha: {vc.noise_floor_alpha}")
    else:
        print(f"  Silero 语音概率阈值 silero_threshold: {vc.silero_threshold}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="VAD/音频采集演示")
    parser.add_argument(
        "--backend",
        choices=["rms", "silero"],
        default="rms",
        help="VAD 后端：rms 或 silero",
    )
    parser.add_argument(
        "--preset",
        choices=["aggressive", "balanced", "conservative"],
        default="balanced",
        help="端点策略预设：更激进/折中/更保守",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="录制一段直到检测到静音结束（需要麦克风）",
    )
    args = parser.parse_args()

    set_debug(True)

    vc = VADConfig.preset(args.preset)  # type: ignore[arg-type]
    vc.backend = args.backend  # type: ignore[assignment]

    ac = AudioConfig(
        vad_config=vc,
        vad_backend=args.backend,
    )
    _print_config(vc, ac)

    if not args.record:
        return 0

    print("\n开始监听麦克风：请说话，停顿约 {:.1f}s 后系统将判定结束…\n".format(vc.silence_duration))

    audio_in = AudioInput(ac)
    result_holder: list = []

    def on_start():
        print("[回调] on_speech_start：已确认语音开始（预缓冲已回填）")

    def on_end(full):
        import numpy as np

        arr = np.asarray(full)
        result_holder.append(arr)
        sec = len(arr) / float(ac.sample_rate)
        print(f"[回调] on_speech_end：语音结束，样本数={len(arr)}，约 {sec:.2f} s")

    try:
        audio_in.record_until_silence(on_speech_start=on_start, on_speech_end=on_end)
    except KeyboardInterrupt:
        print("\n用户中断。")
        return 130
    finally:
        try:
            audio_in.stop_listening()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
