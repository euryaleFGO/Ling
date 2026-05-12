"""录音脚本：录制声纹注册音频"""
import sounddevice as sd
import numpy as np
import wave
import sys
import os

DURATION = 5  # 录音秒数
SAMPLERATE = 16000
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "voiceprints")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "enroll_master.wav")

os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"准备录音 {DURATION} 秒，采样率 {SAMPLERATE}...")
print("请用正常语速说一段话，比如：")
print("  '你好，我是玲的主人，今天天气真不错'")
print()
input("按回车开始录音...")
print("录音中...")

audio = sd.rec(int(DURATION * SAMPLERATE), samplerate=SAMPLERATE, channels=1, dtype='int16')
sd.wait()

print(f"录音完成，保存到: {OUTPUT_FILE}")

with wave.open(OUTPUT_FILE, 'w') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(SAMPLERATE)
    wf.writeframes(audio.tobytes())

print(f"已保存: {OUTPUT_FILE}")
print(f"时长: {len(audio) / SAMPLERATE:.1f}s")
