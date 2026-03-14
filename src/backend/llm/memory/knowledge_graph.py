"""
知识图谱模块
用于存储和查询实体关系，增强记忆系统的关系推理能力

设计思路：
1. 实体（Entity）：人、地点、物品、事件等
2. 关系（Relation）：实体之间的关系
3. 三元组（Triple）：(主体, 关系, 客体) 如 (用户, 妻子, 小红)

存储：
- MongoDB 存储三元组
- 支持按实体、关系类型检索
- 支持简单的关系推理
"""
from typing import Optional, List, Dict, Any, Set, Tuple
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class Entity:
    """实体"""
    def __init__(
        self,
        name: str,
        entity_type: str = "unknown",
        aliases: List[str] = None,
        properties: Dict[str, Any] = None
    ):
        self.name = name
        self.entity_type = entity_type  # person, place, object, event, concept, etc.
        self.aliases = aliases or []  # 别名列表
        self.properties = properties or {}  # 属性
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.entity_type,
            "aliases": self.aliases,
            "properties": self.properties
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Entity':
        return cls(
            name=data["name"],
            entity_type=data.get("type", "unknown"),
            aliases=data.get("aliases", []),
            properties=data.get("properties", {})
        )
    
    def __repr__(self):
        return f"Entity({self.name}, type={self.entity_type})"
    
    def __eq__(self, other):
        if isinstance(other, Entity):
            return self.name.lower() == other.name.lower()
        return False
    
    def __hash__(self):
        return hash(self.name.lower())


class Relation:
    """关系"""
    # 预定义的关系类型
    RELATION_TYPES = {
        # 人际关系
        "spouse": "配偶",
        "parent": "父母",
        "child": "子女",
        "sibling": "兄弟姐妹",
        "friend": "朋友",
        "colleague": "同事",
        "boss": "上司",
        
        # 属性关系
        "has": "拥有",
        "likes": "喜欢",
        "dislikes": "不喜欢",
        "wants": "想要",
        
        # 位置关系
        "lives_in": "居住于",
        "works_at": "工作于",
        "from": "来自",
        
        # 事件关系
        "did": "做了",
        "will_do": "将要做",
        "participated_in": "参与了",
        
        # 其他
        "is": "是",
        "related_to": "相关于",
    }
    
    def __init__(
        self,
        relation_type: str,
        properties: Dict[str, Any] = None
    ):
        self.relation_type = relation_type
        self.properties = properties or {}
    
    def to_dict(self) -> Dict:
        return {
            "type": self.relation_type,
            "properties": self.properties
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Relation':
        return cls(
            relation_type=data["type"],
            properties=data.get("properties", {})
        )
    
    def get_display_name(self) -> str:
        """获取关系的显示名称"""
        return self.RELATION_TYPES.get(self.relation_type, self.relation_type)
    
    def __repr__(self):
        return f"Relation({self.relation_type})"


class Triple:
    """三元组：(主体, 关系, 客体)"""
    def __init__(
        self,
        subject: Entity,
        relation: Relation,
        obj: Entity,
        confidence: float = 1.0,
        source: str = None,
        created_at: datetime = None
    ):
        self.subject = subject
        self.relation = relation
        self.obj = obj
        self.confidence = confidence  # 置信度 0-1
        self.source = source  # 来源（如会话ID）
        self.created_at = created_at or datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            "subject": self.subject.to_dict(),
            "relation": self.relation.to_dict(),
            "object": self.obj.to_dict(),
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Triple':
        return cls(
            subject=Entity.from_dict(data["subject"]),
            relation=Relation.from_dict(data["relation"]),
            obj=Entity.from_dict(data["object"]),
            confidence=data.get("confidence", 1.0),
            source=data.get("source"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        )
    
    def to_natural_language(self) -> str:
        """转换为自然语言描述"""
        rel_name = self.relation.get_display_name()
        return f"{self.subject.name} {rel_name} {self.obj.name}"
    
    def __repr__(self):
        return f"Triple({self.subject.name} --[{self.relation.relation_type}]--> {self.obj.name})"
    
    def __eq__(self, other):
        if isinstance(other, Triple):
            return (self.subject == other.subject and 
                    self.relation.relation_type == other.relation.relation_type and
                    self.obj == other.obj)
        return False
    
    def __hash__(self):
        return hash((self.subject.name.lower(), self.relation.relation_type, self.obj.name.lower()))


class KnowledgeGraph:
    """
    知识图谱
    
    存储和查询实体关系
    """
    
    # 用户实体的特殊名称
    USER_ENTITY_NAME = "用户"
    
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self._triples: List[Triple] = []
        self._entities: Dict[str, Entity] = {}  # name -> Entity
        self._mongo_collection = None
        
        # 初始化用户实体
        self._ensure_user_entity()
        
        # 加载已有数据
        self._load_from_db()
    
    def _ensure_user_entity(self):
        """确保用户实体存在"""
        if self.USER_ENTITY_NAME not in self._entities:
            user_entity = Entity(
                name=self.USER_ENTITY_NAME,
                entity_type="person",
                aliases=["我", "本人"],
                properties={"is_user": True}
            )
            self._entities[self.USER_ENTITY_NAME] = user_entity
    
    def _get_collection(self):
        """获取 MongoDB 集合"""
        if self._mongo_collection is None:
            try:
                from ..database.mongo_client import get_mongo_client
                client = get_mongo_client()
                db = client.get_database()
                self._mongo_collection = db["knowledge_graph"]
            except Exception as e:
                logger.warning(f"无法连接 MongoDB: {e}")
        return self._mongo_collection
    
    def _load_from_db(self):
        """从数据库加载"""
        collection = self._get_collection()
        if collection is None:
            return
        
        try:
            docs = collection.find({"user_id": self.user_id})
            for doc in docs:
                triple = Triple.from_dict(doc["triple"])
                self._triples.append(triple)
                
                # 注册实体
                self._entities[triple.subject.name] = triple.subject
                self._entities[triple.obj.name] = triple.obj
            
            logger.info(f"从数据库加载了 {len(self._triples)} 个三元组")
        except Exception as e:
            logger.warning(f"加载知识图谱失败: {e}")
    
    def _save_triple_to_db(self, triple: Triple):
        """保存三元组到数据库"""
        collection = self._get_collection()
        if collection is None:
            return
        
        try:
            doc = {
                "user_id": self.user_id,
                "triple": triple.to_dict(),
                "created_at": datetime.now()
            }
            
            # 使用 upsert 避免重复
            collection.update_one(
                {
                    "user_id": self.user_id,
                    "triple.subject.name": triple.subject.name,
                    "triple.relation.type": triple.relation.relation_type,
                    "triple.object.name": triple.obj.name
                },
                {"$set": doc},
                upsert=True
            )
        except Exception as e:
            logger.warning(f"保存三元组失败: {e}")
    
    def add_triple(
        self,
        subject: str,
        relation: str,
        obj: str,
        subject_type: str = "unknown",
        obj_type: str = "unknown",
        confidence: float = 1.0,
        source: str = None
    ) -> Triple:
        """
        添加三元组
        
        Args:
            subject: 主体名称
            relation: 关系类型
            obj: 客体名称
            subject_type: 主体类型
            obj_type: 客体类型
            confidence: 置信度
            source: 来源
            
        Returns:
            创建的 Triple
        """
        # 获取或创建实体
        if subject in self._entities:
            subject_entity = self._entities[subject]
        else:
            subject_entity = Entity(name=subject, entity_type=subject_type)
            self._entities[subject] = subject_entity
        
        if obj in self._entities:
            obj_entity = self._entities[obj]
        else:
            obj_entity = Entity(name=obj, entity_type=obj_type)
            self._entities[obj] = obj_entity
        
        # 创建关系
        relation_obj = Relation(relation_type=relation)
        
        # 创建三元组
        triple = Triple(
            subject=subject_entity,
            relation=relation_obj,
            obj=obj_entity,
            confidence=confidence,
            source=source
        )
        
        # 检查是否已存在（如果存在，更新置信度）
        existing = self._find_triple(subject, relation, obj)
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            existing.source = source
            self._save_triple_to_db(existing)
            logger.info(f"更新三元组: {existing}")
            return existing
        
        # 添加新三元组
        self._triples.append(triple)
        self._save_triple_to_db(triple)
        logger.info(f"添加三元组: {triple}")
        return triple
    
    def _find_triple(self, subject: str, relation: str, obj: str) -> Optional[Triple]:
        """查找三元组"""
        for triple in self._triples:
            if (triple.subject.name.lower() == subject.lower() and
                triple.relation.relation_type == relation and
                triple.obj.name.lower() == obj.lower()):
                return triple
        return None
    
    def query_by_subject(self, subject: str) -> List[Triple]:
        """查询主体的所有关系"""
        results = []
        subject_lower = subject.lower()
        for triple in self._triples:
            if triple.subject.name.lower() == subject_lower:
                results.append(triple)
            # 也检查别名
            if subject_lower in [a.lower() for a in triple.subject.aliases]:
                results.append(triple)
        return results
    
    def query_by_object(self, obj: str) -> List[Triple]:
        """查询客体的所有关系"""
        results = []
        obj_lower = obj.lower()
        for triple in self._triples:
            if triple.obj.name.lower() == obj_lower:
                results.append(triple)
            # 也检查别名
            if obj_lower in [a.lower() for a in triple.obj.aliases]:
                results.append(triple)
        return results
    
    def query_by_relation(self, relation: str) -> List[Triple]:
        """查询特定关系类型的所有三元组"""
        return [t for t in self._triples if t.relation.relation_type == relation]
    
    def query(
        self,
        subject: str = None,
        relation: str = None,
        obj: str = None
    ) -> List[Triple]:
        """
        灵活查询
        
        支持任意组合：
        - query(subject="用户") -> 用户的所有关系
        - query(relation="likes") -> 所有 likes 关系
        - query(subject="用户", relation="spouse") -> 用户的配偶
        """
        results = self._triples.copy()
        
        if subject:
            subject_lower = subject.lower()
            results = [t for t in results if t.subject.name.lower() == subject_lower]
        
        if relation:
            results = [t for t in results if t.relation.relation_type == relation]
        
        if obj:
            obj_lower = obj.lower()
            results = [t for t in results if t.obj.name.lower() == obj_lower]
        
        return results
    
    def get_entity_info(self, entity_name: str) -> Dict:
        """
        获取实体的完整信息
        
        包括：
        - 实体属性
        - 作为主体的关系
        - 作为客体的关系
        """
        entity = self._entities.get(entity_name)
        if not entity:
            return {"error": "实体不存在"}
        
        as_subject = self.query_by_subject(entity_name)
        as_object = self.query_by_object(entity_name)
        
        return {
            "entity": entity.to_dict(),
            "as_subject": [t.to_dict() for t in as_subject],
            "as_object": [t.to_dict() for t in as_object]
        }
    
    def get_related_entities(self, entity_name: str, max_depth: int = 2) -> Set[str]:
        """
        获取相关实体（多跳）
        
        Args:
            entity_name: 起始实体
            max_depth: 最大跳数
            
        Returns:
            相关实体名称集合
        """
        visited = set()
        current_level = {entity_name.lower()}
        
        for _ in range(max_depth):
            next_level = set()
            for name in current_level:
                if name in visited:
                    continue
                visited.add(name)
                
                # 作为主体
                for triple in self.query_by_subject(name):
                    next_level.add(triple.obj.name.lower())
                
                # 作为客体
                for triple in self.query_by_object(name):
                    next_level.add(triple.subject.name.lower())
            
            current_level = next_level - visited
        
        return visited
    
    def infer(self, question: str) -> List[Triple]:
        """
        简单推理
        
        支持的推理模式：
        1. 用户的妻子是谁 -> query(subject="用户", relation="spouse")
        2. 谁喜欢苹果 -> query(obj="苹果", relation="likes")
        
        TODO: 更复杂的推理需要接入 LLM
        """
        # 简单的关键词匹配
        question_lower = question.lower()
        
        # 模式1: "用户的XXX是谁/什么"
        for rel_type, rel_name in Relation.RELATION_TYPES.items():
            if rel_name in question:
                if "用户" in question:
                    return self.query(subject=self.USER_ENTITY_NAME, relation=rel_type)
        
        # 模式2: 检测实体名称
        for entity_name in self._entities.keys():
            if entity_name.lower() in question_lower:
                return self.query_by_subject(entity_name) + self.query_by_object(entity_name)
        
        return []
    
    def to_context_string(self, max_triples: int = 10) -> str:
        """
        转换为上下文字符串（用于注入 Prompt）
        
        Returns:
            自然语言描述的知识图谱
        """
        if not self._triples:
            return ""
        
        # 优先返回用户相关的
        user_triples = self.query_by_subject(self.USER_ENTITY_NAME)
        other_triples = [t for t in self._triples if t not in user_triples]
        
        selected = user_triples[:max_triples]
        remaining = max_triples - len(selected)
        if remaining > 0:
            selected.extend(other_triples[:remaining])
        
        lines = ["已知关于用户的信息："]
        for triple in selected:
            lines.append(f"- {triple.to_natural_language()}")
        
        return "\n".join(lines)
    
    def delete_triple(self, subject: str, relation: str, obj: str) -> bool:
        """删除三元组"""
        triple = self._find_triple(subject, relation, obj)
        if triple:
            self._triples.remove(triple)
            
            # 从数据库删除
            collection = self._get_collection()
            if collection:
                collection.delete_one({
                    "user_id": self.user_id,
                    "triple.subject.name": subject,
                    "triple.relation.type": relation,
                    "triple.object.name": obj
                })
            
            logger.info(f"删除三元组: {triple}")
            return True
        return False
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            "triple_count": len(self._triples),
            "entity_count": len(self._entities),
            "relation_types": list(set(t.relation.relation_type for t in self._triples))
        }


# 全局实例缓存
_knowledge_graphs: Dict[str, KnowledgeGraph] = {}


def get_knowledge_graph(user_id: str = "default_user") -> KnowledgeGraph:
    """获取知识图谱实例"""
    if user_id not in _knowledge_graphs:
        _knowledge_graphs[user_id] = KnowledgeGraph(user_id)
    return _knowledge_graphs[user_id]
