"""
查询处理器
负责查询预处理、意图识别、查询扩展

功能：
1. 意图识别 - 判断用户查询的类型
2. 查询清洗 - 去除噪声、标准化
3. 查询扩展 - 添加同义词、相关词
4. 关键词提取 - 用于 BM25 检索
"""
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """查询意图类型"""
    FACTUAL = "factual"           # 事实查询：用户的名字是什么
    PREFERENCE = "preference"     # 偏好查询：用户喜欢什么
    EVENT = "event"               # 事件查询：用户做了什么
    RELATION = "relation"         # 关系查询：用户的妻子是谁
    EMOTION = "emotion"           # 情感查询：用户心情如何
    KNOWLEDGE = "knowledge"       # 知识查询：一般性知识问题
    CHAT = "chat"                 # 闲聊：不需要检索
    UNKNOWN = "unknown"           # 未知


@dataclass
class ProcessedQuery:
    """处理后的查询"""
    original: str                 # 原始查询
    cleaned: str                  # 清洗后的查询
    intent: QueryIntent           # 意图
    keywords: List[str]           # 关键词
    expanded_queries: List[str]   # 扩展查询
    entities: List[str]           # 识别的实体
    confidence: float             # 置信度
    metadata: Dict                # 额外元数据


class QueryProcessor:
    """
    查询处理器
    
    职责：
    1. 识别查询意图
    2. 提取关键词
    3. 扩展查询
    """
    
    # 意图识别关键词
    INTENT_PATTERNS = {
        QueryIntent.RELATION: [
            r"谁是.+的",
            r".+的.+是谁",
            r".+和.+是什么关系",
            r".+的(?:妻子|丈夫|老婆|老公|父母|孩子|朋友)",
            r"(?:妻子|丈夫|老婆|老公|父母|孩子|朋友)是",
        ],
        QueryIntent.PREFERENCE: [
            r"喜欢(?:什么|吃|玩|做)",
            r"不喜欢",
            r"偏好",
            r"最爱",
            r"讨厌",
            r"想要",
        ],
        QueryIntent.FACTUAL: [
            r"叫什么",
            r"是什么",
            r"在哪",
            r"住在",
            r"工作",
            r"年龄|多大",
            r"什么时候",
        ],
        QueryIntent.EVENT: [
            r"做了什么",
            r"发生了什么",
            r"今天|昨天|明天",
            r"最近",
            r"上次|下次",
        ],
        QueryIntent.EMOTION: [
            r"心情|情绪",
            r"开心|高兴|快乐",
            r"难过|伤心|悲伤",
            r"生气|愤怒",
            r"感觉|觉得",
        ],
        QueryIntent.CHAT: [
            r"^你好",
            r"^hi|hello",
            r"^嗯|哦|啊",
            r"^谢谢",
            r"^好的|知道了",
            r"^再见|拜拜",
        ],
    }
    
    # 停用词
    STOP_WORDS = {
        "的", "了", "是", "在", "有", "和", "与", "或",
        "我", "你", "他", "她", "它", "我们", "你们", "他们",
        "这", "那", "什么", "怎么", "为什么", "如何",
        "吗", "呢", "吧", "啊", "嗯", "哦",
        "一个", "一些", "所有", "每个",
        "可以", "能够", "应该", "需要",
        "the", "a", "an", "is", "are", "was", "were",
        "to", "of", "in", "for", "on", "with",
    }
    
    # 同义词映射（用于查询扩展）
    SYNONYMS = {
        "喜欢": ["爱", "喜爱", "热爱", "偏好"],
        "讨厌": ["不喜欢", "厌恶", "反感"],
        "妻子": ["老婆", "太太", "媳妇", "爱人"],
        "丈夫": ["老公", "先生", "爱人"],
        "孩子": ["儿子", "女儿", "小孩"],
        "朋友": ["好友", "伙伴", "闺蜜", "哥们"],
        "工作": ["上班", "职业", "工作于"],
        "住": ["居住", "住在", "家在"],
    }
    
    def __init__(self):
        # 编译正则表达式
        self._compiled_patterns = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def process(self, query: str) -> ProcessedQuery:
        """
        处理查询
        
        Args:
            query: 原始查询
            
        Returns:
            ProcessedQuery 对象
        """
        # 1. 清洗查询
        cleaned = self._clean_query(query)
        
        # 2. 识别意图
        intent, confidence = self._identify_intent(cleaned)
        
        # 3. 提取关键词
        keywords = self._extract_keywords(cleaned)
        
        # 4. 识别实体
        entities = self._extract_entities(cleaned)
        
        # 5. 扩展查询
        expanded = self._expand_query(cleaned, keywords)
        
        return ProcessedQuery(
            original=query,
            cleaned=cleaned,
            intent=intent,
            keywords=keywords,
            expanded_queries=expanded,
            entities=entities,
            confidence=confidence,
            metadata={
                "has_question_mark": "?" in query or "？" in query,
                "length": len(query),
            }
        )
    
    def _clean_query(self, query: str) -> str:
        """清洗查询"""
        # 去除首尾空白
        cleaned = query.strip()
        
        # 标准化标点
        cleaned = re.sub(r'[？?]+', '?', cleaned)
        cleaned = re.sub(r'[！!]+', '!', cleaned)
        cleaned = re.sub(r'[。\.]+', '.', cleaned)
        
        # 去除多余空格
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned
    
    def _identify_intent(self, query: str) -> Tuple[QueryIntent, float]:
        """
        识别查询意图
        
        Returns:
            (意图, 置信度)
        """
        query_lower = query.lower()
        
        # 检查每种意图的模式
        intent_scores = {}
        
        for intent, patterns in self._compiled_patterns.items():
            score = 0
            for pattern in patterns:
                if pattern.search(query_lower):
                    score += 1
            if score > 0:
                intent_scores[intent] = score
        
        if not intent_scores:
            return QueryIntent.UNKNOWN, 0.5
        
        # 返回得分最高的意图
        best_intent = max(intent_scores, key=intent_scores.get)
        max_score = intent_scores[best_intent]
        confidence = min(0.5 + max_score * 0.2, 0.95)
        
        return best_intent, confidence
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 简单分词（中文按字符，英文按空格）
        # 更好的做法是使用 jieba 等分词工具
        words = []
        
        # 中文分词（简单实现：2-4字的组合）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', query)
        for chars in chinese_chars:
            if len(chars) >= 2:
                words.append(chars)
                # 也添加 bigram
                for i in range(len(chars) - 1):
                    words.append(chars[i:i+2])
        
        # 英文分词
        english_words = re.findall(r'[a-zA-Z]+', query)
        words.extend(english_words)
        
        # 过滤停用词
        keywords = [w for w in words if w.lower() not in self.STOP_WORDS and len(w) > 1]
        
        # 去重保序
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords[:10]  # 最多返回10个关键词
    
    def _extract_entities(self, query: str) -> List[str]:
        """提取实体（简单实现）"""
        entities = []
        
        # 提取引号中的内容
        quoted = re.findall(r'[""「」『』](.+?)[""「」『』]', query)
        entities.extend(quoted)
        
        # 提取人名模式（简单：2-4个汉字）
        # 实际应用中应该使用 NER 模型
        name_patterns = [
            r'叫(\S{2,4})',
            r'(\S{2,4})是',
            r'的(\S{2,4})',
        ]
        for pattern in name_patterns:
            matches = re.findall(pattern, query)
            for match in matches:
                if not any(sw in match for sw in self.STOP_WORDS):
                    entities.append(match)
        
        return list(set(entities))
    
    def _expand_query(self, query: str, keywords: List[str]) -> List[str]:
        """扩展查询"""
        expanded = [query]  # 包含原查询
        
        # 基于同义词扩展
        for keyword in keywords:
            if keyword in self.SYNONYMS:
                for synonym in self.SYNONYMS[keyword]:
                    expanded_query = query.replace(keyword, synonym)
                    if expanded_query != query and expanded_query not in expanded:
                        expanded.append(expanded_query)
        
        return expanded[:5]  # 最多5个扩展查询
    
    def should_retrieve(self, processed: ProcessedQuery) -> bool:
        """
        判断是否需要检索
        
        有些查询（如简单闲聊）不需要检索
        """
        # 闲聊意图不需要检索
        if processed.intent == QueryIntent.CHAT:
            return False
        
        # 太短的查询可能不需要
        if len(processed.cleaned) < 3:
            return False
        
        # 没有关键词
        if not processed.keywords:
            return False
        
        return True
    
    def get_retrieval_config(self, processed: ProcessedQuery) -> Dict:
        """
        根据查询意图获取检索配置
        
        不同意图使用不同的检索策略
        """
        config = {
            "use_vector": True,
            "use_keyword": True,
            "vector_weight": 0.7,
            "keyword_weight": 0.3,
            "top_k": 5,
            "min_score": 0.3,
            "source_priority": ["memory", "knowledge_graph", "knowledge_base"],
        }
        
        if processed.intent == QueryIntent.RELATION:
            # 关系查询优先使用知识图谱
            config["source_priority"] = ["knowledge_graph", "memory"]
            config["top_k"] = 3
        
        elif processed.intent == QueryIntent.PREFERENCE:
            # 偏好查询优先使用记忆
            config["source_priority"] = ["memory", "knowledge_graph"]
            config["vector_weight"] = 0.8
            config["keyword_weight"] = 0.2
        
        elif processed.intent == QueryIntent.EVENT:
            # 事件查询关注时间
            config["source_priority"] = ["memory"]
            config["top_k"] = 7
        
        elif processed.intent == QueryIntent.KNOWLEDGE:
            # 知识查询使用知识库
            config["source_priority"] = ["knowledge_base", "memory"]
            config["keyword_weight"] = 0.4
        
        return config
