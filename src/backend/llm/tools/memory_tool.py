"""
记忆工具
保存和检索长期记忆
"""
from typing import List, Optional
from .base_tool import BaseTool, ToolParameter, ToolResult


class MemoryTool(BaseTool):
    """记忆管理工具"""
    
    def __init__(self, memory_manager=None):
        """
        Args:
            memory_manager: LongTermMemoryManager 实例
        """
        self._memory_manager = memory_manager
    
    def set_memory_manager(self, memory_manager):
        """设置记忆管理器"""
        self._memory_manager = memory_manager
    
    @property
    def name(self) -> str:
        return "memory"
    
    @property
    def description(self) -> str:
        return """管理用户的长期记忆。
使用场景：
1. save: 当用户分享了重要的个人信息时保存（如：喜好、身份、重要事件等）
2. search: 当需要回忆用户之前说过的话时搜索
3. list: 列出用户的记忆

注意：只保存真正重要的信息，不要保存日常闲聊。
重要信息包括：用户的名字、喜好、厌恶、身份信息、重要事件、约定等。"""
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型：save(保存)、search(搜索)、list(列表)",
                required=True,
                enum=["save", "search", "list"]
            ),
            ToolParameter(
                name="content",
                type="string",
                description="记忆内容（save时必填）或搜索关键词（search时必填）",
                required=False
            ),
            ToolParameter(
                name="memory_type",
                type="string",
                description="记忆类型",
                required=False,
                enum=["fact", "preference", "event", "emotion"],
                default="fact"
            ),
            ToolParameter(
                name="importance",
                type="number",
                description="重要程度 0-1，默认0.5。非常重要的信息设为0.8以上",
                required=False,
                default=0.5
            )
        ]
    
    def execute(
        self, 
        action: str,
        content: Optional[str] = None,
        memory_type: str = "fact",
        importance: float = 0.5,
        **kwargs
    ) -> ToolResult:
        """执行记忆操作"""
        if not self._memory_manager:
            return ToolResult(success=False, error="记忆管理器未初始化")
        
        try:
            if action == "save":
                if not content:
                    return ToolResult(success=False, error="保存记忆需要提供 content")
                
                memory_id = self._memory_manager.add_memory(
                    content=content,
                    memory_type=memory_type,
                    importance=importance
                )
                return ToolResult(
                    success=True, 
                    data={"message": f"记忆已保存", "memory_id": memory_id}
                )
            
            elif action == "search":
                if not content:
                    return ToolResult(success=False, error="搜索记忆需要提供关键词")
                
                memories = self._memory_manager.search_relevant_memories(
                    query=content,
                    n_results=5
                )
                return ToolResult(
                    success=True,
                    data={
                        "count": len(memories),
                        "memories": [
                            {
                                "content": m.get("content"),
                                "type": m.get("type"),
                                "importance": m.get("importance")
                            }
                            for m in memories
                        ]
                    }
                )
            
            elif action == "list":
                memories = self._memory_manager.get_recent_memories(limit=10)
                return ToolResult(
                    success=True,
                    data={
                        "count": len(memories),
                        "memories": [
                            {
                                "content": m.get("content"),
                                "type": m.get("type"),
                                "created_at": str(m.get("created_at", ""))[:19]
                            }
                            for m in memories
                        ]
                    }
                )
            
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
                
        except Exception as e:
            return ToolResult(success=False, error=str(e))
