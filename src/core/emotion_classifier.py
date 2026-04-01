# -*- coding: utf-8 -*-
"""
轻量文本情绪分类器（规则法）

设计目标：
1. 作为 LLM 显式情绪标签的兜底，不依赖额外模型下载。
2. 与当前 Live2D 支持的 9 类情绪对齐：
   neutral/joy/anger/sadness/surprise/shy/think/fear/cry
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable


@dataclass
class EmotionResult:
    emotion: str
    score: float
    reason: str = ""


class EmotionClassifier:
    """基于关键词和标点特征的轻量情绪分类器。"""

    _EMOTIONS = {"neutral", "joy", "anger", "sadness", "surprise", "shy", "think", "fear", "cry"}

    _LEXICON: Dict[str, Iterable[str]] = {
        "joy": [
            "开心", "高兴", "太好了", "真棒", "不错", "喜欢", "哈哈", "嘿嘿", "愉快", "幸福",
            "😀", "😄", "😊", "🥳", "❤", "♥",
        ],
        "anger": [
            "生气", "愤怒", "气死", "可恶", "讨厌", "烦死", "离谱", "火大", "怒", "恼火",
            "😠", "😡",
        ],
        "sadness": [
            "难过", "伤心", "失落", "遗憾", "可惜", "沮丧", "心情不好", "不开心", "悲伤",
            "😞", "😔", "😢",
        ],
        "surprise": [
            "惊讶", "震惊", "居然", "竟然", "真的吗", "真的假的", "不会吧", "天哪", "意外",
            "😮", "😲", "🤯",
        ],
        "shy": [
            "害羞", "不好意思", "脸红", "有点羞", "怪不好意思", "腼腆", "🙈", "😳",
        ],
        "think": [
            "我想想", "让我想想", "分析", "考虑", "推理", "先看", "首先", "其次", "总的来说", "综合来看", "🤔",
        ],
        "fear": [
            "害怕", "恐惧", "担心", "紧张", "不敢", "危险", "慌", "焦虑", "可怕", "😨", "😰",
        ],
        "cry": [
            "想哭", "哭了", "呜呜", "委屈", "泪", "眼泪", "崩溃", "😭", "T_T", "QAQ",
        ],
    }

    def classify(self, text: str) -> EmotionResult:
        if not text:
            return EmotionResult(emotion="neutral", score=0.0, reason="empty")

        s = text.strip().lower()
        if not s:
            return EmotionResult(emotion="neutral", score=0.0, reason="blank")

        scores = {k: 0.0 for k in self._LEXICON.keys()}

        # 关键词命中计分
        for emo, words in self._LEXICON.items():
            for w in words:
                if w and w.lower() in s:
                    scores[emo] += 1.0

        # 标点增强
        exclam = s.count("!") + s.count("！")
        quest = s.count("?") + s.count("？")
        if exclam >= 2:
            scores["joy"] += 0.3
            scores["anger"] += 0.3
            scores["surprise"] += 0.3
        if quest >= 2:
            scores["think"] += 0.2
            scores["surprise"] += 0.2

        # 优先处理更强烈情绪，避免被弱信号覆盖
        priority = ["cry", "anger", "fear", "sadness", "surprise", "shy", "joy", "think"]
        best_emo = "neutral"
        best_score = 0.0
        for emo in priority:
            sc = scores.get(emo, 0.0)
            if sc > best_score:
                best_score = sc
                best_emo = emo

        if best_score <= 0.0:
            return EmotionResult(emotion="neutral", score=0.0, reason="no_match")

        return EmotionResult(emotion=best_emo, score=best_score, reason="rule_match")
