# -*- coding: utf-8 -*-
"""轻量情绪分类器快速测试脚本。"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from core.emotion_classifier import EmotionClassifier


def main():
    clf = EmotionClassifier()
    samples = [
        "太好了！今天真的很开心！",
        "这也太离谱了吧，我有点生气。",
        "我有点难过，感觉很失落。",
        "真的假的？居然还能这样！",
        "有点不好意思，嘿嘿。",
        "让我想想这个问题该怎么分析。",
        "我有点害怕，担心会失败。",
        "呜呜呜我真的想哭。",
        "我们继续下一步。",
    ]

    for s in samples:
        r = clf.classify(s)
        print(f"{s} -> {r.emotion} (score={r.score:.2f}, reason={r.reason})")


if __name__ == "__main__":
    main()
