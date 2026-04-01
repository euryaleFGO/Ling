# -*- coding: utf-8 -*-
"""
技能生成器工具
基于 OpenClaw Skill Creator 的设计理念创建新工具

核心原则：
1. Concise is Key - 保持描述简洁，只添加模型不具备的知识
2. Progressive Disclosure - 分层加载：元数据 → SKILL.md → References
3. 遵循 BaseTool 接口规范
"""
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from .base_tool import BaseTool, ToolParameter, ToolResult


# 工具模板库
TOOL_TEMPLATES = {
    "simple": {
        "description": "简单工具 - 执行单一操作，无状态依赖",
        "example": "DateTimeTool, ExitAppTool",
        "template": '''"""
{class_doc}
"""
from .base_tool import BaseTool, ToolParameter, ToolResult


class {class_name}(BaseTool):
    """{tool_description}"""

    @property
    def name(self) -> str:
        return "{tool_name}"

    @property
    def description(self) -> str:
        return "{tool_description}"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="param_name",
                type="string",
                description="参数描述",
                required=True
            ),
        ]

    def execute(self, **kwargs) -> ToolResult:
        try:
            # 实现逻辑
            return ToolResult(success=True, data="结果数据")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
''',
    },
    "manager": {
        "description": "管理器工具 - 管理多个实例，支持增删改查",
        "example": "ReminderManager, ReminderTool",
        "template": '''"""
{class_doc}
"""
import threading
from typing import List, Optional, Dict, Any

from .base_tool import BaseTool, ToolParameter, ToolResult


class {class_name}Manager:
    """{tool_description}管理器"""
    _instance = None

    @classmethod
    def get_instance(cls) -> "{class_name}Manager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._storage: Dict[str, Any] = {{}}

    def add(self, key: str, value: Any) -> bool:
        self._storage[key] = value
        return True

    def get(self, key: str) -> Optional[Any]:
        return self._storage.get(key)

    def remove(self, key: str) -> bool:
        return self._storage.pop(key, None) is not None

    def list_all(self) -> List[Any]:
        return list(self._storage.values())


class {class_name}Tool(BaseTool):
    """{tool_description}工具"""

    def __init__(self):
        self._manager = {class_name}Manager.get_instance()

    @property
    def name(self) -> str:
        return "{tool_name}"

    @property
    def description(self) -> str:
        return "{tool_description}"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型: add, get, remove, list",
                required=True,
                enum=["add", "get", "remove", "list"]
            ),
            ToolParameter(
                name="key",
                type="string",
                description="键名（add/get/remove时必填）",
                required=False
            ),
            ToolParameter(
                name="value",
                type="string",
                description="值（add时必填）",
                required=False
            ),
        ]

    def execute(self, action: str, key: str = None, value: str = None, **kwargs) -> ToolResult:
        try:
            if action == "list":
                items = self._manager.list_all()
                return ToolResult(success=True, data=items)
            elif action == "add":
                if not key or value is None:
                    return ToolResult(success=False, error="add 需要 key 和 value")
                self._manager.add(key, value)
                return ToolResult(success=True, data=f"已添加: {{key}}")
            elif action == "get":
                if not key:
                    return ToolResult(success=False, error="get 需要 key")
                result = self._manager.get(key)
                return ToolResult(success=True, data=result)
            elif action == "remove":
                if not key:
                    return ToolResult(success=False, error="remove 需要 key")
                self._manager.remove(key)
                return ToolResult(success=True, data=f"已删除: {{key}}")
            else:
                return ToolResult(success=False, error=f"未知操作: {{action}}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
''',
    },
    "file": {
        "description": "文件操作工具 - 读写文件系统",
        "example": "FileReadTool, FileWriteTool",
        "template": '''"""
{class_doc}
"""
from pathlib import Path
from typing import List

from .base_tool import BaseTool, ToolParameter, ToolResult


class {class_name}(BaseTool):
    """{tool_description}"""

    def __init__(self):
        self._allowed_dirs = [
            Path(__file__).resolve().parents[4],  # 项目根目录
        ]

    def _is_safe_path(self, filepath: str) -> bool:
        """检查路径是否在允许范围内"""
        try:
            target = Path(filepath).resolve()
            return any(target.is_relative_to(d) for d in self._allowed_dirs)
        except Exception:
            return False

    @property
    def name(self) -> str:
        return "{tool_name}"

    @property
    def description(self) -> str:
        return "{tool_description}"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="filepath",
                type="string",
                description="文件路径",
                required=True
            ),
        ]

    def execute(self, filepath: str, **kwargs) -> ToolResult:
        try:
            if not self._is_safe_path(filepath):
                return ToolResult(success=False, error="路径不在允许范围内")
            # 实现逻辑
            return ToolResult(success=True, data="结果")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
''',
    },
    "api": {
        "description": "API调用工具 - 外部服务集成",
        "example": "BrowserSearchTool",
        "template": '''"""
{class_doc}
"""
import requests
from typing import List, Optional, Dict, Any

from .base_tool import BaseTool, ToolParameter, ToolResult


class {class_name}(BaseTool):
    """{tool_description}"""

    def __init__(self):
        self._base_url = None  # TODO: 设置 API 地址
        self._timeout = 30

    @property
    def name(self) -> str:
        return "{tool_name}"

    @property
    def description(self) -> str:
        return "{tool_description}"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="查询参数",
                required=True
            ),
        ]

    def execute(self, query: str, **kwargs) -> ToolResult:
        try:
            # TODO: 实现 API 调用逻辑
            return ToolResult(success=True, data={{"result": "待实现"}})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
''',
    },
}

# 工具创建指南（用于 LLM 参考）
TOOL_CREATION_GUIDE = """
## 工具创建指南

### 命名规范
- 工具名: 小写字母、数字、连字符 (如 `my-tool`, `file-reader`)
- 类名: PascalCase (如 `MyTool`, `FileReadTool`)
- 文件名: snake_case (如 `my_tool.py`)

### 必填字段
1. name - 唯一标识，LLM 用此调用
2. description - 何时使用此工具（LLM 判断依据）
3. parameters - 参数列表，含 name/type/description/required
4. execute() - 实际执行逻辑

### 描述编写原则
- 描述应该帮助 LLM 判断何时调用，而不是解释实现细节
- 示例: "当用户需要搜索网页内容时使用" 而非 "调用 Google Search API"

### 安全考虑
- 文件操作必须检查路径安全
- 删除操作必须二次确认
- API 调用需要超时控制
- 敏感操作需要用户授权
"""


class SkillGeneratorTool(BaseTool):
    """
    技能生成器工具

    当用户要求创建新工具、自定义功能扩展、自动化任务时使用。
    支持生成工具模板、验证工具代码、自动注册到工具系统。

    遵循 OpenClaw Skill Creator 设计原则：
    - Concise is Key: 保持描述简洁
    - Progressive Disclosure: 分层加载资源
    """

    TOOLS_DIR = Path(__file__).resolve().parents[0]

    @property
    def name(self) -> str:
        return "skill_generator"

    @property
    def description(self) -> str:
        return (
            "创建新工具、生成工具模板、验证工具代码。当用户要求添加新功能、"
            "创建自动化工具、自定义技能时使用。可生成简单工具、管理器工具、"
            "文件操作工具、API调用工具等多种类型的工具模板。"
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型: create, list_templates, generate_template, validate, guide",
                required=True,
                enum=["create", "list_templates", "generate_template", "validate", "guide"]
            ),
            ToolParameter(
                name="tool_name",
                type="string",
                description="工具名称（create时必填），使用小写字母和连字符",
                required=False
            ),
            ToolParameter(
                name="tool_type",
                type="string",
                description="工具类型: simple, manager, file, api",
                required=False,
                enum=["simple", "manager", "file", "api"]
            ),
            ToolParameter(
                name="description",
                type="string",
                description="工具描述，说明何时使用此工具",
                required=False
            ),
            ToolParameter(
                name="code",
                type="string",
                description="工具代码（validate时使用）",
                required=False
            ),
            ToolParameter(
                name="filepath",
                type="string",
                description="文件路径（validate时使用）",
                required=False
            ),
        ]

    def _normalize_tool_name(self, name: str) -> str:
        """标准化工具名称为 snake_case 文件名"""
        # 转换为小写
        name = name.lower()
        # 替换空格和下划线为连字符
        name = re.sub(r'[\s_]+', '-', name)
        # 移除非字母数字和连字符的字符
        name = re.sub(r'[^a-z0-9\-]', '', name)
        return name

    def _to_class_name(self, name: str) -> str:
        """将工具名转换为 PascalCase 类名"""
        # 先标准化为 kebab-case
        normalized = self._normalize_tool_name(name)
        # 拆分为单词
        words = normalized.split('-')
        # 转换为首字母大写
        return ''.join(word.capitalize() for word in words if word)

    def _create_tool_file(self, tool_name: str, tool_type: str, description: str) -> Dict[str, Any]:
        """创建工具文件"""
        class_name = self._to_class_name(tool_name)
        file_name = self._normalize_tool_name(tool_name) + "_tool.py"
        file_path = self.TOOLS_DIR / file_name

        # 检查是否已存在
        if file_path.exists():
            return {
                "success": False,
                "error": f"工具文件已存在: {file_path}",
                "existing": True
            }

        # 获取模板
        template = TOOL_TEMPLATES.get(tool_type, TOOL_TEMPLATES["simple"])["template"]

        # 替换模板变量
        code = template.format(
            class_name=class_name,
            tool_name=self._normalize_tool_name(tool_name),
            tool_description=description,
            class_doc=f"{description}\n\n自动生成工具"
        )

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)

        return {
            "success": True,
            "file_path": str(file_path),
            "class_name": class_name,
            "file_name": file_name,
            "code": code
        }

    def _generate_skill_md(self, tool_name: str, description: str, class_name: str) -> str:
        """生成 SKILL.md 内容"""
        normalized_name = self._normalize_tool_name(tool_name)
        return f'''---
name: {normalized_name}
description: {description}
---

# {class_name}

## 功能说明

{description}

## 使用场景

- 何时使用此工具的典型场景
- 用户可能的请求方式

## 使用示例

```
# 示例调用
result = tool.execute(param_name="参数值")
```

## 注意事项

- 任何特殊限制或注意事项
- 安全相关说明
'''

    def execute(self, action: str, tool_name: str = None, tool_type: str = None,
                description: str = None, code: str = None, filepath: str = None,
                **kwargs) -> ToolResult:
        try:
            if action == "list_templates":
                """列出所有可用的工具模板"""
                templates = {}
                for key, val in TOOL_TEMPLATES.items():
                    templates[key] = {
                        "description": val["description"],
                        "example": val["example"]
                    }
                return ToolResult(success=True, data={
                    "templates": templates,
                    "guide": TOOL_CREATION_GUIDE.strip()
                })

            elif action == "generate_template":
                """生成工具模板代码（不保存文件）"""
                if not tool_name:
                    return ToolResult(success=False, error="generate_template 需要 tool_name")
                if not tool_type:
                    tool_type = "simple"
                if not description:
                    description = f"{tool_name} 工具描述"

                class_name = self._to_class_name(tool_name)
                template = TOOL_TEMPLATES.get(tool_type, TOOL_TEMPLATES["simple"])["template"]
                code = template.format(
                    class_name=class_name,
                    tool_name=self._normalize_tool_name(tool_name),
                    tool_description=description,
                    class_doc=f"{description}\n\n自动生成工具"
                )
                return ToolResult(success=True, data={"code": code})

            elif action == "create":
                """创建新工具"""
                if not tool_name:
                    return ToolResult(success=False, error="create 需要 tool_name")
                if not tool_type:
                    tool_type = "simple"
                if not description:
                    return ToolResult(success=False, error="create 需要 description")

                result = self._create_tool_file(tool_name, tool_type, description)
                if not result["success"]:
                    return ToolResult(success=False, error=result["error"])

                # 生成 SKILL.md
                skill_md = self._generate_skill_md(
                    tool_name,
                    description,
                    result["class_name"]
                )

                # 保存 SKILL.md
                skill_md_path = self.TOOLS_DIR / f"{result['file_name'].replace('_tool.py', '')}.md"
                with open(skill_md_path, 'w', encoding='utf-8') as f:
                    f.write(skill_md)

                return ToolResult(success=True, data={
                    "message": f"工具创建成功！",
                    "file_path": result["file_path"],
                    "skill_md_path": str(skill_md_path),
                    "class_name": result["class_name"],
                    "next_steps": [
                        f"1. 编辑 {result['file_path']} 实现具体逻辑",
                        f"2. 在 tools/__init__.py 中导入: from .{result['file_name'].replace('.py', '')} import {result['class_name']}",
                        f"3. 在 tool_manager.py 中注册: self.register({result['class_name']}())",
                        f"4. 查看 {skill_md_path} 了解工具使用指南"
                    ]
                })

            elif action == "validate":
                """验证工具代码或文件"""
                content = None
                source = None

                if filepath:
                    path = Path(filepath)
                    if not path.exists():
                        return ToolResult(success=False, error=f"文件不存在: {filepath}")
                    content = path.read_text(encoding='utf-8')
                    source = f"文件: {filepath}"
                elif code:
                    content = code
                    source = "输入代码"
                else:
                    return ToolResult(success=False, error="validate 需要 filepath 或 code")

                issues = []

                # 检查基本结构
                if "class " not in content:
                    issues.append("缺少类定义")
                if "BaseTool" not in content and "def execute" not in content:
                    issues.append("未继承 BaseTool 或缺少 execute 方法")

                # 检查必要方法
                if "@property" not in content or "def name" not in content:
                    issues.append("缺少 name 属性")
                if "@property" not in content or "def description" not in content:
                    issues.append("缺少 description 属性")
                if "def execute" not in content:
                    issues.append("缺少 execute 方法")

                # 检查 return ToolResult
                if "ToolResult" not in content:
                    issues.append("未返回 ToolResult")

                if issues:
                    return ToolResult(success=True, data={
                        "valid": False,
                        "source": source,
                        "issues": issues,
                        "suggestion": "请参考其他工具（如 terminal_tool.py）确保包含所有必要元素"
                    })
                else:
                    return ToolResult(success=True, data={
                        "valid": True,
                        "source": source,
                        "issues": []
                    })

            elif action == "guide":
                """返回工具创建指南"""
                return ToolResult(success=True, data={
                    "guide": TOOL_CREATION_GUIDE.strip(),
                    "naming_rules": {
                        "tool_name": "小写字母、连字符 (如 my-tool)",
                        "class_name": "PascalCase (如 MyTool)",
                        "file_name": "snake_case + _tool.py (如 my_tool_tool.py)"
                    },
                    "required_elements": [
                        "name property - 工具唯一标识",
                        "description property - 何时使用",
                        "parameters property - 参数列表",
                        "execute() method - 执行逻辑",
                        "ToolResult return - 执行结果"
                    ]
                })

            else:
                return ToolResult(success=False, error=f"未知操作: {action}")

        except Exception as e:
            return ToolResult(success=False, error=str(e))
