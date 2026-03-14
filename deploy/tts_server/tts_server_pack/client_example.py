#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地调用 TTS 服务器示例
在本地电脑运行此脚本，把 SERVER_URL 改成你的服务器地址即可。
需要：pip install requests
"""
import requests
import base64
import sys

# ========== 在这里改成你的服务器地址 ==========
# 若做了 SSH 端口转发：ssh -L 5001:localhost:5001 user@服务器
# 则这里用 http://127.0.0.1:5001
SERVER_URL = "http://127.0.0.1:5001"   # 或 "http://你的服务器IP:5001"

def check_health():
    """健康检查"""
    r = requests.get(f"{SERVER_URL}/health", timeout=5)
    r.raise_for_status()
    print("服务正常:", r.json())
    return True

def generate_and_save(text: str, output_path: str = "output.wav", use_clone: bool = True):
    """
    请求服务器生成音频并保存到本地文件。
    """
    url = f"{SERVER_URL}/tts/generate"
    payload = {"text": text, "use_clone": use_clone}
    print(f"正在请求: {url}")
    print(f"文本: {text}")
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    audio_b64 = data.get("audio")
    if not audio_b64:
        raise RuntimeError("响应中没有 audio 字段")
    audio_bytes = base64.b64decode(audio_b64)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    print(f"已保存: {output_path} ({len(audio_bytes)} bytes)")
    return output_path

def main():
    text = "你好，这是从本地发送到服务器的测试语音。" if len(sys.argv) < 2 else " ".join(sys.argv[1:])
    try:
        check_health()
        generate_and_save(text, "output.wav")
    except requests.exceptions.ConnectionError as e:
        print("连接失败，请检查：")
        print("  1. SERVER_URL 是否改为你的服务器地址（或 127.0.0.1 若已做端口转发）")
        print("  2. 服务器上的 TTS 服务是否已启动（python service.py --host 0.0.0.0 --port 5001）")
        print("  3. 防火墙/安全组是否放行 5001 端口")
        print("错误:", e)
        sys.exit(1)
    except Exception as e:
        print("错误:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
