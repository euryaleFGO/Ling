"""
代码修改工具
安全的文件修改操作，支持读取、修改、创建、测试、回滚
"""
from typing import List, Optional
import os
import shutil
from datetime import datetime
from pathlib import Path

from .base_tool import BaseTool, ToolParameter, ToolResult


class CodeModifyTool(BaseTool):
    """
    安全的文件修改工具

    支持的操作：
    - read: 读取文件内容
    - modify: 修改文件（自动备份）
    - create: 创建新文件（自动备份目录）
    - test: 测试修改（验证语法/运行测试）
    - rollback: 回滚到备份版本

    安全限制：
    - 只允许操作项目根目录内的文件
    - 排除敏感目录：.git, node_modules, __pycache__, data/backups, models
    """

    # 默认排除的目录
    EXCLUDED_DIRS = {
        ".git", "node_modules", "__pycache__", "data", "models",
        ".venv", "venv", "env", ".env", ".idea", ".vscode",
    }

    def __init__(self, project_root: str = None):
        """
        Args:
            project_root: 项目根目录路径（安全边界）。默认自动检测。
        """
        if project_root is None:
            # Auto-detect: walk up from this file to find the project root
            # src/backend/llm/tools/code_modify_tool.py -> parents[4] = project root
            project_root = str(Path(__file__).resolve().parents[4])
        self._project_root = os.path.normpath(project_root)
        self._backup_dir = os.path.join(self._project_root, "data", "backups")
        os.makedirs(self._backup_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return "code_modify"

    @property
    def description(self) -> str:
        return """安全的文件修改工具，支持读取、修改、创建、测试、回滚代码文件。
当需要查看或修改项目代码时使用。所有修改操作会自动备份。
仅允许操作项目目录内的文件，且排除 .git、node_modules 等敏感目录。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型",
                required=True,
                enum=["read", "modify", "create", "test", "rollback"]
            ),
            ToolParameter(
                name="file_path",
                type="string",
                description="文件路径（相对于项目根目录）",
                required=True
            ),
            ToolParameter(
                name="content",
                type="string",
                description="文件内容（modify/create 时必填）",
                required=False,
                default=""
            ),
            ToolParameter(
                name="search",
                type="string",
                description="要搜索替换的文本（modify 时可选，留空则覆盖整个文件）",
                required=False,
                default=""
            ),
        ]

    def execute(
        self,
        action: str,
        file_path: str,
        content: str = "",
        search: str = "",
        **kwargs
    ) -> ToolResult:
        """
        执行文件操作
        """
        # 解析完整路径
        full_path = self._resolve_path(file_path)
        if full_path is None:
            return ToolResult(
                success=False,
                error=f"无效的文件路径: {file_path}"
            )

        # 安全检查
        is_safe, safety_msg = self._safety_check(full_path)
        if not is_safe:
            return ToolResult(success=False, error=safety_msg)

        # 分发到对应处理方法
        handlers = {
            "read": self._read_file,
            "modify": self._modify_file,
            "create": self._create_file,
            "test": self._test_file,
            "rollback": self._rollback_file,
        }

        handler = handlers.get(action)
        if not handler:
            return ToolResult(
                success=False,
                error=f"不支持的操作: {action}"
            )

        return handler(full_path, file_path, content, search)

    def _resolve_path(self, file_path: str) -> Optional[str]:
        """
        解析文件路径为绝对路径

        支持相对路径（相对于项目根目录）和绝对路径
        绝对路径也检查是否在项目根目录内（防路径遍历）
        """
        try:
            # 如果是绝对路径，检查是否在项目根目录内
            if os.path.isabs(file_path):
                rel = os.path.relpath(file_path, self._project_root)
                if rel.startswith('..'):
                    return None
                return os.path.normpath(file_path)

            # 相对于项目根目录
            full_path = os.path.join(self._project_root, file_path)
            return os.path.normpath(full_path)
        except Exception:
            return None

    def _safety_check(self, full_path: str) -> tuple:
        """
        安全检查：确保文件在项目根目录内且不在排除目录中

        Returns:
            (is_safe, message)
        """
        # 检查是否在项目根目录内
        try:
            rel_path = os.path.relpath(full_path, self._project_root)
            # 如果路径以 .. 开头，说明不在项目目录内
            if rel_path.startswith('..'):
                return False, f"安全限制：不允许操作项目目录外的文件: {full_path}"
        except ValueError:
            return False, f"安全限制：无法解析路径关系: {full_path}"

        # 检查是否在排除目录中
        path_parts = Path(full_path).parts
        for excluded in self.EXCLUDED_DIRS:
            if excluded in path_parts:
                return False, f"安全限制：不允许操作 {excluded} 目录下的文件"

        # 检查是否是备份目录本身
        if full_path.startswith(self._backup_dir):
            return False, "安全限制：不允许直接修改备份目录"

        return True, "通过"

    def _read_file(
        self, full_path: str, rel_path: str, content: str, search: str
    ) -> ToolResult:
        """读取文件内容"""
        try:
            if not os.path.exists(full_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {rel_path}"
                )

            # 检查文件大小
            file_size = os.path.getsize(full_path)
            if file_size > 1_000_000:  # 1MB
                return ToolResult(
                    success=False,
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，请指定具体行范围"
                )

            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                file_content = f.read()

            return ToolResult(
                success=True,
                data={
                    "file_path": rel_path,
                    "content": file_content,
                    "size": file_size,
                    "lines": file_content.count('\n') + 1,
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"读取文件失败: {e}"
            )

    def _modify_file(
        self, full_path: str, rel_path: str, content: str, search: str
    ) -> ToolResult:
        """修改文件（自动备份）"""
        try:
            if not os.path.exists(full_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {rel_path}"
                )

            # 备份原文件
            backup_path = self._backup_file(full_path)

            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                original_content = f.read()

            if search:
                # 搜索替换模式
                if search not in original_content:
                    return ToolResult(
                        success=False,
                        error=f"未在文件中找到搜索文本: {search[:50]}..."
                    )
                new_content = original_content.replace(search, content, 1)
            else:
                # 覆盖整个文件
                new_content = content

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                data={
                    "file_path": rel_path,
                    "action": "modify",
                    "backup": backup_path,
                    "original_size": len(original_content),
                    "new_size": len(new_content),
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"修改文件失败: {e}"
            )

    def _create_file(
        self, full_path: str, rel_path: str, content: str, search: str
    ) -> ToolResult:
        """创建新文件"""
        try:
            if os.path.exists(full_path):
                return ToolResult(
                    success=False,
                    error=f"文件已存在: {rel_path}，如需覆盖请使用 modify 操作"
                )

            # 确保目录存在
            parent_dir = os.path.dirname(full_path)
            os.makedirs(parent_dir, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return ToolResult(
                success=True,
                data={
                    "file_path": rel_path,
                    "action": "create",
                    "size": len(content),
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"创建文件失败: {e}"
            )

    def _test_file(
        self, full_path: str, rel_path: str, content: str, search: str
    ) -> ToolResult:
        """测试文件（验证语法）"""
        try:
            if not os.path.exists(full_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {rel_path}"
                )

            results = {
                "file_path": rel_path,
                "tests": [],
            }

            # 根据文件类型执行不同测试
            if full_path.endswith('.py'):
                # Python 语法检查
                try:
                    import py_compile
                    py_compile.compile(full_path, doraise=True)
                    results["tests"].append({
                        "name": "syntax_check",
                        "passed": True,
                        "message": "Python 语法检查通过",
                    })
                except py_compile.PyCompileError as e:
                    results["tests"].append({
                        "name": "syntax_check",
                        "passed": False,
                        "message": f"语法错误: {e}",
                    })

            elif full_path.endswith('.json'):
                # JSON 格式检查
                import json
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        json.load(f)
                    results["tests"].append({
                        "name": "json_check",
                        "passed": True,
                        "message": "JSON 格式正确",
                    })
                except json.JSONDecodeError as e:
                    results["tests"].append({
                        "name": "json_check",
                        "passed": False,
                        "message": f"JSON 格式错误: {e}",
                    })

            else:
                results["tests"].append({
                    "name": "type_check",
                    "passed": True,
                    "message": f"文件类型 {os.path.splitext(full_path)[1]} 暂不支持自动测试",
                })

            all_passed = all(t["passed"] for t in results["tests"])
            results["all_passed"] = all_passed

            return ToolResult(
                success=True,
                data=results
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"测试文件失败: {e}"
            )

    def _rollback_file(
        self, full_path: str, rel_path: str, content: str, search: str
    ) -> ToolResult:
        """回滚到最近的备份版本"""
        try:
            filename = os.path.basename(full_path)

            # 搜索备份文件
            backups = []
            for f in os.listdir(self._backup_dir):
                if f.startswith(filename) and f.endswith('.bak'):
                    backup_path = os.path.join(self._backup_dir, f)
                    backups.append((backup_path, os.path.getmtime(backup_path)))

            if not backups:
                return ToolResult(
                    success=False,
                    error=f"未找到 {rel_path} 的备份文件"
                )

            # 按时间排序，获取最新的备份
            backups.sort(key=lambda x: x[1], reverse=True)
            latest_backup = backups[0][0]

            # 回滚
            shutil.copy2(latest_backup, full_path)

            return ToolResult(
                success=True,
                data={
                    "file_path": rel_path,
                    "action": "rollback",
                    "from_backup": os.path.basename(latest_backup),
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"回滚文件失败: {e}"
            )

    def _backup_file(self, file_path: str) -> str:
        """
        备份文件到备份目录

        返回备份文件路径
        """
        filename = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{filename}.{timestamp}.bak"
        backup_path = os.path.join(self._backup_dir, backup_filename)

        shutil.copy2(file_path, backup_path)

        return backup_path
