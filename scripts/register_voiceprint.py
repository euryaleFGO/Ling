"""注册声纹：把音频注册为指定名字"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np
from pathlib import Path
from core.sv_engine import SVEngine
from core.voiceprint_database import VoiceprintDatabase

NAME = "昆伦"

# 要注册的音频文件（路径相对于项目根目录，或使用绝对路径）
AUDIO_FILES = [
    "data/voiceprints/enroll_master.wav",
]

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = PROJECT_ROOT / "data" / "voiceprints"

print(f"初始化 SVEngine (campplus)...")
sv = SVEngine(model_id="iic/speech_campplus_sv_zh-cn_16k-common", device="cuda:0")

print(f"初始化 VoiceprintDatabase ({DB_PATH})...")
db = VoiceprintDatabase(storage_path=DB_PATH)

for audio_path in AUDIO_FILES:
    full_path = Path(audio_path)
    if not full_path.is_absolute():
        full_path = PROJECT_ROOT / audio_path

    if not full_path.exists():
        print(f"[SKIP] 文件不存在: {full_path}")
        continue

    print(f"\n处理: {full_path.name}")
    embedding = sv.enroll_file(str(full_path))
    print(f"  embedding shape: {embedding.shape}, dtype: {embedding.dtype}")

    db.save_voiceprint(
        speaker_id=NAME,
        embedding=embedding,
        metadata={"source": str(full_path.name)},
    )
    print(f"  [OK] 注册成功: {NAME}")

# 列出所有已注册
print("\n--- 已注册声纹 ---")
speakers = db.list_speakers()
for s in speakers:
    print(f"  {s}")

print("\n完成！")
