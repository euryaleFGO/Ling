"""
终端执行工具
允许 Agent 在系统终端执行命令
"""
from typing import List, Optional
import subprocess
from pathlib import Path
import os
import re
import json

try:
    import tkinter as tk
    from tkinter import simpledialog
except Exception:
    tk = None
    simpledialog = None

from .base_tool import BaseTool, ToolParameter, ToolResult


class TerminalExecuteTool(BaseTool):
    """在终端执行命令并返回输出"""

    @property
    def name(self) -> str:
        return "terminal_execute"

    @property
    def description(self) -> str:
        return (
            "在本机 cmd 终端执行命令并返回输出。"
            "当用户需要检查环境、运行脚本、查看文件或执行命令行操作时使用。"
            "如果命令包含删除操作，将弹窗要求输入密钥确认。"
        )

    def _is_delete_command(self, command: str) -> bool:
        """检测命令是否包含删除行为。"""
        cmd = (command or "").strip().lower()
        if not cmd:
            return False

        # 更全面的删除命令检测
        patterns = [
            r"\bdel\b",           # del, DEL, Del
            r"\berase\b",         # erase
            r"\brd\b",             # rd, rmdir
            r"\brmdir\b",         # rmdir
            r"\bremove-item\b",   # PowerShell remove-item
            r"\brm\b",             # rm (Unix)
            r"\brm-rf\b",          # rm -rf
            r"\brm -",            # rm -rf, rm -r, etc.
            r"/d\s",              # cmd /d (disable autorun)
            r"deltree\b",         # deltree (old Windows)
            r"format\b.*\/q",     # format /q (quick format)
            r"shift\s+\+",        # shift + (秘密删除)
        ]

        # 检查是否有管道或重定向到删除命令的情况
        if re.search(r"\|\s*(del|erase|rm|rmdir)", cmd):
            return True

        return any(re.search(p, cmd, flags=re.IGNORECASE) for p in patterns)

    def _project_root(self) -> Path:
        """获取项目根目录。"""
        return Path(__file__).resolve().parents[4]

    def _read_env_key(self, env_path: Path, key_name: str) -> str:
        """从 .env 风格文件读取指定键。"""
        if not env_path.exists() or not env_path.is_file():
            return ""

        try:
            for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() != key_name:
                    continue
                value = v.strip().strip('"').strip("'")
                return value
        except Exception:
            return ""
        return ""

    def _load_delete_confirm_key(self) -> str:
        """
        读取删除授权密钥，按优先级：
        1) 系统环境变量
        2) 项目 .env / 后端 .env
        3) config/llm_profiles.json
        """
        key_name = "LIYING_DELETE_CONFIRM_KEY"

        # 1) 系统环境变量
        value = os.getenv(key_name, "").strip()
        if value:
            return value

        project_root = self._project_root()

        # 2) .env 文件
        env_candidates = [
            project_root / ".env",
            project_root / "src" / "backend" / "llm" / "api_infer" / ".env",
        ]
        for env_path in env_candidates:
            value = self._read_env_key(env_path, key_name)
            if value:
                return value

        # 3) JSON 配置
        profiles_path = project_root / "config" / "llm_profiles.json"
        try:
            if profiles_path.exists() and profiles_path.is_file():
                data = json.loads(profiles_path.read_text(encoding="utf-8", errors="replace"))

                # 支持顶层字段
                top = str(data.get("delete_confirm_key", "")).strip()
                if top:
                    return top

                # 支持 security 对象
                security = data.get("security", {}) if isinstance(data, dict) else {}
                sec_key = str(security.get("delete_confirm_key", "")).strip() if isinstance(security, dict) else ""
                if sec_key:
                    return sec_key

                # 支持当前激活 profile 字段
                active = str(data.get("active", "")).strip()
                profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
                if active and isinstance(profiles, dict):
                    profile = profiles.get(active, {})
                    if isinstance(profile, dict):
                        profile_key = str(profile.get("delete_confirm_key", "")).strip()
                        if profile_key:
                            return profile_key
        except Exception:
            return ""

        return ""

    def _confirm_delete_authorization(self, command: str) -> ToolResult:
        """删除命令授权弹窗。"""
        expected_key = self._load_delete_confirm_key()
        if not expected_key:
            return ToolResult(
                success=False,
                error=(
                    "检测到删除命令，但未配置删除授权密钥。"
                    "请在环境变量/.env/或 config/llm_profiles.json 中设置 delete_confirm_key"
                ),
            )

        if tk is None or simpledialog is None:
            return ToolResult(success=False, error="检测到删除命令，但当前环境无法弹出授权窗口")

        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            prompt = (
                "检测到删除操作命令，为防止误删请先授权。\n\n"
                f"命令: {command}\n\n"
                "请输入删除授权密钥后点击确定："
            )
            user_key = simpledialog.askstring(
                title="删除命令授权",
                prompt=prompt,
                show="*",
                parent=root,
            )
            if user_key is None:
                return ToolResult(success=False, error="已取消删除命令执行")
            if user_key.strip() != expected_key:
                return ToolResult(success=False, error="删除授权失败：密钥错误")
            return ToolResult(success=True, data="授权通过")
        except Exception as e:
            return ToolResult(success=False, error=f"删除授权弹窗异常: {e}")
        finally:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="command",
                type="string",
                description="要执行的命令字符串，例如 dir、python --version、pip list",
                required=True,
            ),
            ToolParameter(
                name="cwd",
                type="string",
                description="可选，命令执行目录（默认当前工作目录）",
                required=False,
                default="",
            ),
            ToolParameter(
                name="timeout",
                type="number",
                description="可选，超时时间（秒），默认30，最大120",
                required=False,
                default=30,
            ),
        ]

    def execute(self, command: str, cwd: str = "", timeout: float = 30) -> ToolResult:
        if not command or not str(command).strip():
            return ToolResult(success=False, error="command 不能为空")

        if self._is_delete_command(command):
            auth_result = self._confirm_delete_authorization(command)
            if not auth_result.success:
                return auth_result

        safe_timeout = 30.0
        try:
            safe_timeout = float(timeout)
        except Exception:
            safe_timeout = 30.0
        safe_timeout = max(1.0, min(120.0, safe_timeout))

        run_cwd: Optional[str] = None
        if cwd:
            try:
                resolved = Path(cwd).expanduser().resolve()
            except Exception:
                return ToolResult(success=False, error=f"cwd 无法解析: {cwd}")
            if not resolved.exists() or not resolved.is_dir():
                return ToolResult(success=False, error=f"cwd 不存在或不是目录: {cwd}")
            run_cwd = str(resolved)

        try:
            completed = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=run_cwd,
                timeout=safe_timeout,
            )

            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()

            max_len = 6000
            if len(stdout) > max_len:
                stdout = stdout[:max_len] + "\n... (stdout 已截断)"
            if len(stderr) > max_len:
                stderr = stderr[:max_len] + "\n... (stderr 已截断)"

            return ToolResult(
                success=(completed.returncode == 0),
                data={
                    "command": command,
                    "cwd": run_cwd or str(Path.cwd()),
                    "returncode": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                error=None if completed.returncode == 0 else f"命令执行失败，返回码 {completed.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"命令执行超时（>{safe_timeout}秒）")
        except Exception as e:
            return ToolResult(success=False, error=f"终端执行异常: {e}")
