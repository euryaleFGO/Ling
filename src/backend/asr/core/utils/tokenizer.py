# -*- coding: utf-8 -*-
"""
Token 处理工具
简化自 FunASR runtime/python/onnxruntime/funasr_onnx/utils/utils.py
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Set, Union
import numpy as np


class TokenIDConverterError(Exception):
    """Token ID 转换错误"""
    pass


class TokenIDConverter:
    """Token ID 转换器"""
    
    def __init__(self, token_list: Union[List, str]):
        """
        初始化 Token ID 转换器
        
        Args:
            token_list: Token 列表
        """
        self.token_list = token_list
        self.unk_symbol = token_list[-1]
        self.token2id = {v: i for i, v in enumerate(self.token_list)}
        self.unk_id = self.token2id[self.unk_symbol]

    def get_num_vocabulary_size(self) -> int:
        """获取词表大小"""
        return len(self.token_list)

    def ids2tokens(self, integers: Union[np.ndarray, Iterable[int]]) -> List[str]:
        """将 ID 序列转换为 Token 序列"""
        if isinstance(integers, np.ndarray) and integers.ndim != 1:
            raise TokenIDConverterError(f"必须是一维数组，但得到 {integers.ndim} 维")
        return [self.token_list[i] for i in integers]

    def tokens2ids(self, tokens: Iterable[str]) -> List[int]:
        """将 Token 序列转换为 ID 序列"""
        return [self.token2id.get(i, self.unk_id) for i in tokens]


class CharTokenizer:
    """字符级分词器"""
    
    def __init__(
        self,
        symbol_value: Union[Path, str, Iterable[str]] = None,
        space_symbol: str = "<space>",
        remove_non_linguistic_symbols: bool = False,
    ):
        self.space_symbol = space_symbol
        self.non_linguistic_symbols = self._load_symbols(symbol_value)
        self.remove_non_linguistic_symbols = remove_non_linguistic_symbols

    @staticmethod
    def _load_symbols(value: Union[Path, str, Iterable[str]] = None) -> Set:
        """加载特殊符号"""
        if value is None:
            return set()

        if isinstance(value, (list, set)):
            return set(value)

        file_path = Path(value)
        if not file_path.exists():
            return set()

        with file_path.open("r", encoding="utf-8") as f:
            return set(line.rstrip() for line in f)

    def text2tokens(self, line: Union[str, list]) -> List[str]:
        """将文本转换为 Token 列表"""
        tokens = []
        while len(line) != 0:
            for w in self.non_linguistic_symbols:
                if line.startswith(w):
                    if not self.remove_non_linguistic_symbols:
                        tokens.append(line[: len(w)])
                    line = line[len(w):]
                    break
            else:
                t = line[0]
                if t == " ":
                    t = "<space>"
                tokens.append(t)
                line = line[1:]
        return tokens

    def tokens2text(self, tokens: Iterable[str]) -> str:
        """将 Token 列表转换为文本"""
        tokens = [t if t != self.space_symbol else " " for t in tokens]
        return "".join(tokens)


class Hypothesis(NamedTuple):
    """假设数据类型（用于解码）"""
    yseq: np.ndarray
    score: Union[float, np.ndarray] = 0
    scores: Dict[str, Union[float, np.ndarray]] = dict()
    states: Dict[str, Any] = dict()

    def asdict(self) -> dict:
        """转换为字典"""
        return self._replace(
            yseq=self.yseq.tolist(),
            score=float(self.score),
            scores={k: float(v) for k, v in self.scores.items()},
        )._asdict()
