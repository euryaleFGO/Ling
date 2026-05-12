"""调试声纹：对比注册embedding和实时embedding"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from core.sv_engine import SVEngine

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("初始化 SVEngine...")
sv = SVEngine(model_id="iic/speech_campplus_sv_zh-cn_16k-common", device="cuda:0")

# 1. 加载已注册的 embedding
enrolled = np.load(PROJECT_ROOT / "data/voiceprints/昆伦.npy")
print(f"已注册 embedding: shape={enrolled.shape}, norm={np.linalg.norm(enrolled):.4f}")
print(f"  前5维: {enrolled[:5]}")

# 2. 重新从注册音频提取 embedding
print("\n从 enroll_master.wav 重新提取...")
emb1 = sv.enroll_file(str(PROJECT_ROOT / "data/voiceprints/enroll_master.wav"))
print(f"重新提取: shape={emb1.shape}, norm={np.linalg.norm(emb1):.4f}")
print(f"  前5维: {emb1[:5]}")

sim1 = float(np.dot(enrolled, emb1))
print(f"  与已注册的相似度: {sim1:.4f}")

# 3. 从微信音频提取
wechat_path = r"D:\新建文件夹 (4)\xwechat_files\wxid_n0oqpx92dizw22_9776\msg\file\2026-05\2025年04月23日 下午04点45分(1).wav"
if os.path.exists(wechat_path):
    print(f"\n从微信音频提取...")
    emb2 = sv.enroll_file(wechat_path)
    print(f"微信音频: shape={emb2.shape}, norm={np.linalg.norm(emb2):.4f}")
    sim2 = float(np.dot(enrolled, emb2))
    sim3 = float(np.dot(emb1, emb2))
    print(f"  与已注册的相似度: {sim2:.4f}")
    print(f"  与重新提取的相似度: {sim3:.4f}")

# 4. 录一段实时音频对比
print(f"\n录音 3 秒...")
input("按回车开始录音...")
audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype='int16')
sd.wait()
audio = audio.astype(np.float32).reshape(-1) / 32768.0

emb_live = sv.embed(audio, sample_rate=16000)
print(f"实时音频: shape={emb_live.shape}, norm={np.linalg.norm(emb_live):.4f}")

sim_live_enrolled = float(np.dot(enrolled, emb_live))
sim_live_reextract = float(np.dot(emb1, emb_live))
print(f"  与已注册的相似度: {sim_live_enrolled:.4f}")
print(f"  与重新提取的相似度: {sim_live_reextract:.4f}")

print(f"\n阈值 0.5, 匹配结果: {'MATCH' if sim_live_enrolled >= 0.5 else 'NO MATCH'}")
