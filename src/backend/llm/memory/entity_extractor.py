"""
实体关系提取器
使用 LLM 从对话中自动提取实体和关系，构建知识图谱

提取流程：
1. 分析用户消息
2. 识别实体（人物、地点、物品等）
3. 识别关系（喜欢、讨厌、拥有、住在等）
4. 生成三元组
"""
from typing import Optional, List, Dict, Any, Tuple
import logging
import json
import re

logger = logging.getLogger(__name__)


# 提取 prompt 模板
EXTRACTION_PROMPT = """你是一个信息提取专家。请从用户的消息中提取实体和关系，构建知识图谱。

**任务**：
1. 识别消息中的实体（人物、地点、物品、事件、概念等）
2. 识别实体之间的关系
3. 输出结构化的三元组列表

**实体类型**：
- person: 人物（包括用户自己，用"用户"表示）
- place: 地点
- object: 物品
- event: 事件
- concept: 概念/抽象事物
- time: 时间
- organization: 组织/机构

**关系类型**（使用英文）：
- spouse: 配偶
- parent: 父母
- child: 子女
- sibling: 兄弟姐妹
- friend: 朋友
- colleague: 同事
- likes: 喜欢
- dislikes: 不喜欢
- has: 拥有
- wants: 想要
- lives_in: 居住于
- works_at: 工作于
- from: 来自
- did: 做了（过去）
- will_do: 将要做
- is: 是（属性）
- related_to: 相关于

**输出格式**（JSON）：
```json
{
  "entities": [
    {"name": "实体名", "type": "person/place/object/..."}
  ],
  "triples": [
    {"subject": "主体", "relation": "关系类型", "object": "客体", "confidence": 0.9}
  ]
}
```

**注意**：
- 用户自己用"用户"表示
- 只提取明确提到的信息，不要推测
- confidence 表示置信度（0-1），明确信息用 1.0，推测信息用 0.7 以下
- 如果没有可提取的信息，返回空列表

**用户消息**：
{message}

请提取并输出 JSON："""


class EntityRelationExtractor:
    """
    实体关系提取器
    
    支持两种模式：
    1. 规则提取（快速，但不够智能）
    2. LLM 提取（智能，但需要 API 调用）
    """
    
    # 规则模式的正则表达式
    PATTERNS = {
        # 人际关系
        ("用户", "spouse"): [
            r"我(?:的)?(?:老婆|妻子|老公|丈夫|爱人)(?:是|叫)?(\S{2,10})",
            r"(\S{2,10})是我(?:的)?(?:老婆|妻子|老公|丈夫|爱人)",
        ],
        ("用户", "parent"): [
            r"我(?:的)?(?:爸爸|父亲|妈妈|母亲)(?:是|叫)?(\S{2,10})",
        ],
        ("用户", "child"): [
            r"我(?:的)?(?:儿子|女儿|孩子)(?:是|叫)?(\S{2,10})",
        ],
        ("用户", "friend"): [
            r"我(?:的)?(?:朋友|好友|闺蜜|哥们)(\S{2,10})",
            r"(\S{2,10})是我(?:的)?(?:朋友|好友)",
        ],
        
        # 喜好
        ("用户", "likes"): [
            r"我(?:喜欢|爱|爱吃|喜欢吃|喜欢玩)(\S{2,20})",
            r"我最喜欢的\S*是(\S{2,20})",
        ],
        ("用户", "dislikes"): [
            r"我(?:不喜欢|讨厌|不爱|不想)(\S{2,20})",
        ],
        
        # 位置
        ("用户", "lives_in"): [
            r"我住在(\S{2,20})",
            r"我在(\S{2,20})住",
            r"我家在(\S{2,20})",
        ],
        ("用户", "works_at"): [
            r"我在(\S{2,30})(?:工作|上班)",
            r"我的工作是(\S{2,20})",
        ],
        ("用户", "from"): [
            r"我(?:是|来自)(\S{2,20})人",
            r"我老家(?:是|在)(\S{2,20})",
        ],
        
        # 属性
        ("用户", "is"): [
            r"我是(?:一个|一名)?(\S{2,20})",
            r"我叫(\S{2,10})",
            r"我的名字(?:是|叫)(\S{2,10})",
            r"我今年(\d+)岁",
        ],
        
        # 拥有
        ("用户", "has"): [
            r"我有(?:一个|一只|一台)?(\S{2,20})",
            r"我养了(?:一只|一条)?(\S{2,10})",
        ],
    }
    
    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 客户端（可选，用于智能提取）
        """
        self._llm_client = llm_client
        self._compiled_patterns = {}
        
        # 编译正则表达式
        for (subject, relation), patterns in self.PATTERNS.items():
            self._compiled_patterns[(subject, relation)] = [
                re.compile(p) for p in patterns
            ]
    
    def set_llm_client(self, llm_client):
        """设置 LLM 客户端"""
        self._llm_client = llm_client
    
    def extract_with_rules(self, message: str) -> List[Dict]:
        """
        使用规则提取（快速模式）
        
        Returns:
            三元组列表 [{"subject": "...", "relation": "...", "object": "...", "confidence": 0.9}]
        """
        triples = []
        
        for (subject, relation), patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(message)
                for match in matches:
                    obj = match.strip() if isinstance(match, str) else match[0].strip()
                    if obj and len(obj) >= 2:
                        triples.append({
                            "subject": subject,
                            "relation": relation,
                            "object": obj,
                            "confidence": 0.9
                        })
        
        return triples
    
    def extract_with_llm(self, message: str) -> Dict:
        """
        使用 LLM 提取（智能模式）
        
        Returns:
            {"entities": [...], "triples": [...]}
        """
        if not self._llm_client:
            logger.warning("LLM 客户端未设置，降级使用规则提取")
            return {
                "entities": [],
                "triples": self.extract_with_rules(message)
            }
        
        try:
            prompt = EXTRACTION_PROMPT.format(message=message)
            
            response = self._llm_client.infer(
                messages=[
                    {"role": "system", "content": "你是一个信息提取专家，只输出 JSON，不要其他内容。"},
                    {"role": "user", "content": prompt}
                ],
                stream=False,
                temperature=0.1  # 低温度，更确定性的输出
            )
            
            content = response.choices[0].message.content.strip()
            
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
                return result
            
            logger.warning(f"LLM 输出无法解析为 JSON: {content[:100]}")
            return {"entities": [], "triples": []}
            
        except Exception as e:
            logger.error(f"LLM 提取失败: {e}")
            return {"entities": [], "triples": []}
    
    def extract(self, message: str, use_llm: bool = False) -> Dict:
        """
        提取实体和关系
        
        Args:
            message: 用户消息
            use_llm: 是否使用 LLM（默认使用规则）
            
        Returns:
            {"entities": [...], "triples": [...]}
        """
        if use_llm and self._llm_client:
            return self.extract_with_llm(message)
        else:
            # 规则模式不返回实体列表（因为实体已经在三元组中了）
            triples = self.extract_with_rules(message)
            return {
                "entities": [],
                "triples": triples
            }
    
    def extract_from_conversation(
        self,
        messages: List[Dict],
        use_llm: bool = False
    ) -> Dict:
        """
        从整个对话中提取
        
        Args:
            messages: 消息列表
            use_llm: 是否使用 LLM
            
        Returns:
            合并后的提取结果
        """
        all_entities = []
        all_triples = []
        seen_triples = set()
        
        for msg in messages:
            if msg.get("role") != "user":
                continue
            
            content = msg.get("content", "")
            if not content:
                continue
            
            result = self.extract(content, use_llm=use_llm)
            
            # 合并实体
            for entity in result.get("entities", []):
                if entity not in all_entities:
                    all_entities.append(entity)
            
            # 合并三元组（去重）
            for triple in result.get("triples", []):
                triple_key = (triple["subject"], triple["relation"], triple["object"])
                if triple_key not in seen_triples:
                    seen_triples.add(triple_key)
                    all_triples.append(triple)
        
        return {
            "entities": all_entities,
            "triples": all_triples
        }


# 全局实例
_extractor: Optional[EntityRelationExtractor] = None


def get_entity_extractor(llm_client=None) -> EntityRelationExtractor:
    """获取实体关系提取器实例"""
    global _extractor
    if _extractor is None:
        _extractor = EntityRelationExtractor(llm_client)
    elif llm_client and _extractor._llm_client is None:
        _extractor.set_llm_client(llm_client)
    return _extractor
