# -*- coding: utf-8 -*-
"""
离线多说话人识别（Diarization）脚本

用法：
  python scripts/diarize_audio.py --audio path/to/audio.wav
  python scripts/diarize_audio.py --audio path/to/audio.wav --out diarization.json

可选依赖：
  - silero-vad（更稳的 VAD 切分）
  - librosa（重采样）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ensure_paths():
    project_root = Path(__file__).parent.parent
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    return project_root


def main():
    _ensure_paths()
    from core.diarization_engine import SpeakerDiarizer

    p = argparse.ArgumentParser(description="离线多说话人识别（轻量实现）")
    p.add_argument("--audio", "-a", required=True, help="输入音频文件路径（wav/mp3/flac/m4a 等，取决于 soundfile 支持）")
    p.add_argument("--out", "-o", default="", help="输出 JSON 文件路径（可选）")
    p.add_argument("--min-seg", type=float, default=0.6, help="最短语音段（秒），过短会丢弃")
    p.add_argument("--max-seg", type=float, default=18.0, help="最长语音段（秒），过长会切块")
    p.add_argument("--thr", type=float, default=0.72, help="聚类相似度阈值（越大越严格，speaker 数更可能变多）")
    args = p.parse_args()

    diarizer = SpeakerDiarizer(min_segment_sec=args.min_seg, max_segment_sec=args.max_seg, cluster_sim_threshold=args.thr)
    r = diarizer.diarize_file(args.audio)

    payload = {
        "audio": str(Path(args.audio).resolve()),
        "sample_rate": r.sample_rate,
        "backend": r.backend,
        "num_speakers": r.num_speakers,
        "segments": [
            {
                "start": round(s.start_sec, 3),
                "end": round(s.end_sec, 3),
                "dur": round(s.duration_sec, 3),
                "speaker": s.speaker,
                "score": round(float(s.score), 4),
            }
            for s in r.segments
        ],
    }

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 已写入: {outp}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

