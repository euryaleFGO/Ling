"""
记忆提取器
从对话中自动提取重要信息作为长期记忆
"""
from typing import Optional, List, Dict, Any
import logging
import re

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    记忆提取器
    
    职责:
    1. 从对话中识别重要信息
    2. 分类记忆类型
    3. 评估重要程度
    
    后续可以接入 LLM 来做更智能的提取
    """
    
    # 关键词模式 - 用于基于规则的提取
    PATTERNS = {
        "preference": [
            r"我喜欢(.{2,20})",
            r"我爱(.{2,20})",
            r"我最喜欢的(.+)是(.+)",
            r"我偏好(.{2,20})",
            r"我想要(.{2,20})",
            r"我希望(.{2,20})",
            r"我觉得(.{2,20})很好",
        ],
        "dislike": [
            r"我不喜欢(.{2,20})",
            r"我讨厌(.{2,20})",
            r"我不想(.{2,20})",
            r"我不要(.{2,20})",
            r"我不太喜欢(.{2,20})",
        ],
        "fact": [
            r"我是(\S{2,20})",
            r"我叫(\S{2,10})",
            r"我的名字是(\S{2,10})",
            r"我在(.{2,20})工作",
            r"我住在(.{2,20})",
            r"我今年(\d+)岁",
            r"我的(\S+)是(.{2,20})",
            r"今天是(\d{4}年\d{1,2}月\d{1,2}[日号])",  # 日期信息 - 更严格
            r"现在是(\d+[点时])",  # 时间信息
            r"我有(\S{2,20})",
        ],
        "event": [
            r"我今天(.{3,30})",
            r"我昨天(.{3,30})",
            r"我明天要(.{3,30})",
            r"我刚才(.{3,30})",
            r"我最近(.{3,30})",
            r"我上周(.{3,30})",
            r"我下周(.{3,30})",
            r"我已经(.{3,30})",
            r"我正在(.{3,30})",
            r"我马上(.{2,20})",  # 新增
        ],
        "emotion": [
            r"我很(开心|高兴|快乐)",
            r"我很(难过|伤心|悲伤)",
            r"我很(生气|愤怒)",
            r"我很(累|疲惫)",
            r"我感到(.{2,10})",
            r"我觉得很(.{2,10})",
        ],
        "correction": [  # 用户纠正信息
            r"不对.{0,5}是(.{3,30})",
            r"不是.{0,5}是(.{3,30})",
            r"应该是(.{3,30})",
            r"其实是(.{3,30})",
        ]
    }
    
    # 排除问句 - 包含这些词的消息不提取记忆
    QUESTION_WORDS = ["吗", "呢", "?", "？", "什么", "怎么", "哪", "几", "谁", "为何", "如何"]
    
    # 重要程度关键词
    IMPORTANCE_KEYWORDS = {
        "high": ["最", "非常", "特别", "一直", "永远", "从不", "绝对"],
        "medium": ["很", "比较", "挺", "有点", "可能", "大概"],
        "low": ["有时", "偶尔", "也许", "随便"]
    }
    
    def __init__(self):
        # 编译正则表达式
        self._compiled_patterns = {}
        for category, patterns in self.PATTERNS.items():
            self._compiled_patterns[category] = [
                re.compile(p) for p in patterns
            ]
    
    def extract_from_message(
        self, 
        content: str,
        role: str = "user"
    ) -> List[Dict]:
        """
        从单条消息中提取记忆
        
        Args:
            content: 消息内容
            role: 角色 (主要处理 user 的消息)
            
        Returns:
            提取的记忆列表 [{"content": "...", "type": "...", "importance": 0.5}, ...]
        """
        if role != "user":
            return []
        
        # 过滤问句 - 问句通常不包含需要记住的信息
        if any(q in content for q in self.QUESTION_WORDS):
            return []
        
        memories = []
        
        for category, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(content)
                for match in matches:
                    # 处理匹配结果
                    if isinstance(match, tuple):
                        memory_content = " ".join(match)
                    else:
                        memory_content = match
                    
                    memory_content = memory_content.strip()
                    if not memory_content or len(memory_content) < 2:
                        continue
                    
                    # 确定记忆类型
                    memory_type = "fact"
                    if category in ["preference", "dislike"]:
                        memory_type = "preference"
                    elif category == "event":
                        memory_type = "event"
                    elif category == "emotion":
                        memory_type = "emotion"
                    elif category == "correction":
                        memory_type = "fact"  # 纠正信息也是事实
                    
                    # 计算重要程度
                    importance = self._calculate_importance(content)
                    
                    # 构建完整的记忆内容
                    if category == "preference":
                        full_content = f"用户喜欢{memory_content}"
                    elif category == "dislike":
                        full_content = f"用户不喜欢{memory_content}"
                    elif category == "fact":
                        # 检查是否是日期/时间信息
                        if content.startswith("今天是") or content.startswith("现在是"):
                            full_content = content  # 保留原始内容
                        else:
                            full_content = f"用户{memory_content}"
                    elif category == "event":
                        # 保留原始表述更自然
                        full_content = f"用户说: {content}"
                    elif category == "emotion":
                        full_content = f"用户感到{memory_content}"
                    elif category == "correction":
                        full_content = f"纠正信息: {memory_content}"
                    else:
                        full_content = memory_content
                    
                    memories.append({
                        "content": full_content,
                        "type": memory_type,
                        "importance": importance,
                        "source_text": content
                    })
        
        return memories
    
    def extract_from_conversation(
        self,
        messages: List[Dict]
    ) -> List[Dict]:
        """
        从整个对话中提取记忆
        
        Args:
            messages: 消息列表
            
        Returns:
            提取的记忆列表
        """
        all_memories = []
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            memories = self.extract_from_message(content, role)
            for mem in memories:
                mem["message_index"] = i
            
            all_memories.extend(memories)
        
        # 去重
        unique_memories = self._deduplicate(all_memories)
        
        return unique_memories
    
    def _calculate_importance(self, text: str) -> float:
        """计算重要程度"""
        importance = 0.5  # 默认中等
        
        for keyword in self.IMPORTANCE_KEYWORDS["high"]:
            if keyword in text:
                importance = max(importance, 0.8)
        
        for keyword in self.IMPORTANCE_KEYWORDS["medium"]:
            if keyword in text:
                importance = max(importance, 0.6)
        
        for keyword in self.IMPORTANCE_KEYWORDS["low"]:
            if keyword in text:
                importance = min(importance, 0.4)
        
        return importance
    
    def _deduplicate(self, memories: List[Dict]) -> List[Dict]:
        """去除重复记忆"""
        seen = set()
        unique = []
        
        for mem in memories:
            content = mem["content"]
            if content not in seen:
                seen.add(content)
                unique.append(mem)
        
        return unique
    
    async def extract_with_llm(
        self,
        messages: List[Dict],
        llm_client
    ) -> List[Dict]:
        """
        使用 LLM 提取记忆 (更智能)
        
        TODO: 实现 LLM 辅助提取
        """
        # 这里可以构建 prompt 让 LLM 从对话中提取重要信息
        # 返回格式化的记忆列表
        pass
