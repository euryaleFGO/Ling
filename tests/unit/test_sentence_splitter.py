# -*- coding: utf-8 -*-
"""
句子切分单元测试
"""

import pytest
from core.conversation.sentence_splitter import pop_sentence, split_sentences


class TestPopSentence:
    """pop_sentence 函数测试"""

    def test_hard_split_period(self):
        """测试句号硬切"""
        sentence, remaining = pop_sentence("你好。再见")
        assert sentence == "你好。"
        assert remaining == "再见"

    def test_hard_split_question(self):
        """测试问号硬切"""
        sentence, remaining = pop_sentence("你好吗？我很好")
        assert sentence == "你好吗？"
        assert remaining == "我很好"

    def test_hard_split_exclamation(self):
        """测试感叹号硬切"""
        sentence, remaining = pop_sentence("太好了！真的吗")
        assert sentence == "太好了！"
        assert remaining == "真的吗"

    def test_soft_split(self):
        """测试软切（逗号）"""
        sentence, remaining = pop_sentence("这是一个很长的句子，包含了很多内容，应该被切分")
        assert sentence is not None
        assert "，" in sentence

    def test_no_split(self):
        """测试无需切分"""
        sentence, remaining = pop_sentence("短文本")
        assert sentence is None
        assert remaining == "短文本"

    def test_min_length_single_char(self):
        """测试单字符句子被过滤（小于 _MIN_SENTENCE_CHARS=2）"""
        sentence, remaining = pop_sentence("。，rest")
        assert sentence is None
        assert remaining == "。，rest"

    def test_min_length_exactly_two(self):
        """测试刚好两个字符的句子通过过滤"""
        sentence, remaining = pop_sentence("你好。再见")
        assert sentence == "你好。"
        assert remaining == "再见"


class TestSplitSentences:
    """split_sentences 函数测试"""

    def test_single_sentence(self):
        """测试单句"""
        sentences = split_sentences("你好。")
        assert len(sentences) == 1
        assert sentences[0] == "你好。"

    def test_multiple_sentences(self):
        """测试多句"""
        sentences = split_sentences("你好。我是玲。很高兴认识你。")
        assert len(sentences) == 3

    def test_empty_text(self):
        """测试空文本"""
        sentences = split_sentences("")
        assert len(sentences) == 0

    def test_mixed_split(self):
        """测试混合切分"""
        text = "你好，我是玲。很高兴认识你！有什么可以帮助你的吗？"
        sentences = split_sentences(text)
        assert len(sentences) >= 3
