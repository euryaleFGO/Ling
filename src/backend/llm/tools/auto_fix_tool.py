"""
自动修复工具
执行修复操作：重启服务、回滚配置、重试操作、运行命令
"""
from typing import List, Optional
import subprocess
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .base_tool import BaseTool, ToolParameter, ToolResult


class AutoFixTool(BaseTool):
    """
    自动修复工具

    支持的修复操作：
    - restart_service: 重启指定服务
    - rollback_config: 回滚配置文件到备份版本
    - retry_operation: 重试之前失败的操作
    - run_command: 运行修复命令
    """

    _DANGEROUS_COMMANDS = {
        'powershell', 'pwsh', 'reg', 'format', 'net', 'netsh',
        'certutil', 'taskkill', 'sc', 'wmic', 'rd',
    }
    _DANGEROUS_PATTERNS = [
        r'\bpowershell\b', r'\bpwsh\b', r'\breg\s+delete\b',
        r'\bformat\s+[a-zA-Z]:', r'\bnet\s+user\b', r'\bnetsh\b',
        r'\bcertutil\b', r'\btaskkill\b',
        r'\bsc\s+(create|delete|stop|config)\b', r'\bwmic\b',
    ]

    def _is_dangerous_command(self, command: str) -> bool:
        """检测命令是否包含危险操作（与 terminal_tool 保持一致）"""
        cmd = (command or "").strip().lower()
        if not cmd:
            return False
        first_token = cmd.split()[0] if cmd.split() else ""
        if first_token in self._DANGEROUS_COMMANDS:
            return True
        return any(re.search(p, cmd, flags=re.IGNORECASE) for p in self._DANGEROUS_PATTERNS)

    def __init__(self):
        """初始化自动修复工具"""
        self._backup_dir = "data/backups"
        os.makedirs(self._backup_dir, exist_ok=True)
        self._retry_history = {}  # 记录重试历史
        self._operation_registry = {}  # 存储可重试的操作 {id: (fix_type, target, params)}

    @property
    def name(self) -> str:
        return "auto_fix"

    @property
    def description(self) -> str:
        return """自动修复工具，执行修复操作。
当需要重启服务、回滚配置、重试操作或运行修复命令时使用。
支持的操作：restart_service, rollback_config, retry_operation, run_command"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="fix_type",
                type="string",
                description="修复类型",
                required=True,
                enum=["restart_service", "rollback_config", "retry_operation", "run_command"]
            ),
            ToolParameter(
                name="target",
                type="string",
                description="修复目标（服务名/配置路径/操作ID/命令）",
                required=True
            ),
            ToolParameter(
                name="fix_action",
                type="string",
                description="修复动作的 JSON 参数（可选）",
                required=False,
                default="{}"
            ),
        ]

    def execute(
        self,
        fix_type: str,
        target: str,
        fix_action: str = "{}",
        **kwargs
    ) -> ToolResult:
        """
        执行修复操作
        """
        try:
            import json
            action_params = json.loads(fix_action) if fix_action else {}
        except Exception:
            action_params = {}

        # 分发到对应处理方法
        handlers = {
            "restart_service": self._restart_service,
            "rollback_config": self._rollback_config,
            "retry_operation": self._retry_operation,
            "run_command": self._run_command,
        }

        handler = handlers.get(fix_type)
        if not handler:
            return ToolResult(
                success=False,
                error=f"不支持的修复类型: {fix_type}"
            )

        # Store operation for potential retry (except retry_operation itself)
        if fix_type != "retry_operation":
            op_id = f"{fix_type}:{target}"
            self._operation_registry[op_id] = (fix_type, target, action_params)

        return handler(target, action_params)

    def _restart_service(self, service_name: str, params: dict) -> ToolResult:
        """
        重启服务

        支持：
        - 进程名匹配并终止
        - 通过命令重启
        """
        # 安全验证 service_name
        if not service_name or not re.match(r'^[a-zA-Z0-9_.\-]+$', service_name):
            return ToolResult(
                success=False,
                error=f"无效的服务名称: {service_name}（仅允许字母、数字、下划线、点、连字符）"
            )

        # 安全验证 restart_command（如有）
        restart_cmd = params.get("restart_command", "")
        if restart_cmd and self._is_dangerous_command(restart_cmd):
            return ToolResult(
                success=False,
                error="安全限制：restart_command 包含危险命令，已拒绝执行"
            )

        try:
            result = {
                "fix_type": "restart_service",
                "target": service_name,
                "steps": [],
            }

            # 尝试使用 taskkill 终止进程（Windows）
            if os.name == 'nt':
                kill_cmd = f'taskkill /F /IM {service_name} 2>nul'
                try:
                    proc = subprocess.run(
                        ["cmd", "/c", kill_cmd],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=10,
                    )
                    result["steps"].append({
                        "action": "kill_process",
                        "command": kill_cmd,
                        "returncode": proc.returncode,
                        "output": (proc.stdout or "").strip()[:500],
                    })
                except subprocess.TimeoutExpired:
                    result["steps"].append({
                        "action": "kill_process",
                        "error": "超时",
                    })

            # 如果有重启命令，执行重启（restart_cmd 已在上方验证）
            if restart_cmd:
                try:
                    proc = subprocess.run(
                        ["cmd", "/c", restart_cmd],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,
                    )
                    result["steps"].append({
                        "action": "restart",
                        "command": restart_cmd,
                        "returncode": proc.returncode,
                        "output": (proc.stdout or "").strip()[:500],
                    })
                    result["success"] = proc.returncode == 0
                except subprocess.TimeoutExpired:
                    result["steps"].append({
                        "action": "restart",
                        "error": "重启超时",
                    })
                    result["success"] = False
            else:
                result["message"] = f"已终止进程 {service_name}，未提供重启命令"
                result["success"] = True

            return ToolResult(
                success=result.get("success", True),
                data=result
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"重启服务失败: {e}"
            )

    def _rollback_config(self, config_path: str, params: dict) -> ToolResult:
        """
        回滚配置文件到备份版本

        搜索 data/backups 目录下最新的备份文件
        """
        try:
            result = {
                "fix_type": "rollback_config",
                "target": config_path,
                "steps": [],
            }

            # 检查目标配置文件是否存在
            if not os.path.exists(config_path):
                return ToolResult(
                    success=False,
                    error=f"配置文件不存在: {config_path}"
                )

            # 搜索备份文件
            backup_name = os.path.basename(config_path)
            backup_dir = params.get("backup_dir", self._backup_dir)

            # 查找匹配的备份文件
            backups = []
            for f in os.listdir(backup_dir):
                if f.startswith(backup_name) and f.endswith('.bak'):
                    backup_path = os.path.join(backup_dir, f)
                    backups.append((backup_path, os.path.getmtime(backup_path)))

            if not backups:
                return ToolResult(
                    success=False,
                    error=f"未找到 {config_path} 的备份文件"
                )

            # 按时间排序，获取最新的备份
            backups.sort(key=lambda x: x[1], reverse=True)
            latest_backup = backups[0][0]

            # 先备份当前文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pre_rollback_backup = os.path.join(
                self._backup_dir,
                f"{backup_name}.pre_rollback_{timestamp}.bak"
            )
            shutil.copy2(config_path, pre_rollback_backup)
            result["steps"].append({
                "action": "backup_current",
                "path": pre_rollback_backup,
            })

            # 回滚
            shutil.copy2(latest_backup, config_path)
            result["steps"].append({
                "action": "rollback",
                "from": latest_backup,
                "to": config_path,
            })

            result["success"] = True
            result["message"] = f"已从备份 {latest_backup} 回滚配置"

            return ToolResult(success=True, data=result)

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"配置回滚失败: {e}"
            )

    def _retry_operation(self, operation_id: str, params: dict) -> ToolResult:
        """
        重试之前失败的操作

        从操作注册表中获取操作信息并重试。
        operation_id 格式: "fix_type:target"（如 "restart_service:myapp"）
        """
        try:
            max_retries = params.get("max_retries", 3)
            interval = params.get("interval", 1)

            # Look up the stored operation
            stored = self._operation_registry.get(operation_id)
            if not stored:
                return ToolResult(
                    success=False,
                    error=f"未找到操作 '{operation_id}'。可重试的操作: {list(self._operation_registry.keys())}"
                )

            # 检查重试次数
            retry_count = self._retry_history.get(operation_id, {}).get("count", 0)
            if retry_count >= max_retries:
                return ToolResult(
                    success=False,
                    error=f"操作 {operation_id} 已达到最大重试次数 ({max_retries})"
                )

            # 记录重试
            self._retry_history[operation_id] = {
                "count": retry_count + 1,
                "last_retry": datetime.now().isoformat(),
            }

            # 等待后重试（如果指定了间隔）
            if interval > 0 and retry_count > 0:
                time.sleep(min(interval, 5))  # 最多等5秒

            # Replay the stored operation
            fix_type, target, action_params = stored
            result = self.execute(
                fix_type=fix_type,
                target=target,
                fix_action=json.dumps(action_params) if action_params else "{}",
            )

            # Wrap the result with retry info
            if result.success:
                return ToolResult(
                    success=True,
                    data={
                        "fix_type": "retry_operation",
                        "target": operation_id,
                        "retry_count": retry_count + 1,
                        "max_retries": max_retries,
                        "replayed": fix_type,
                        "inner_result": result.data,
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"重试 {operation_id} 失败（第{retry_count + 1}次）: {result.error}",
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"重试操作失败: {e}"
            )

    def _run_command(self, command: str, params: dict) -> ToolResult:
        """
        运行修复命令
        """
        try:
            timeout = params.get("timeout", 30)
            cwd = params.get("cwd", None)

            result = {
                "fix_type": "run_command",
                "target": command,
                "steps": [],
            }

            # 安全加固：输出重定向检测（允许管道 |，禁止写入文件的重定向）
            # Also detect CMD escape char ^ used to bypass: ^>, ^>>
            if re.search(r'\^?>|>>', command):
                return ToolResult(success=False, error="安全限制：不允许输出重定向到文件")

            # 安全加固：命令链接检测（& && ||）—— 拆分后逐段验证
            chain_segments = re.split(r'\s*(?:&&|\|\||&)\s*', command)
            for segment in chain_segments:
                segment = segment.strip()
                if not segment:
                    continue
                if self._is_dangerous_command(segment):
                    return ToolResult(success=False, error="安全限制：不允许通过命令链接执行危险命令")

            # 安全加固：危险命令检测（对整体命令再检查一次）
            if self._is_dangerous_command(command):
                return ToolResult(success=False, error="安全限制：不允许执行危险命令")

            try:
                proc = subprocess.run(
                    ["cmd", "/c", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd,
                    timeout=timeout,
                )

                stdout = (proc.stdout or "").strip()
                stderr = (proc.stderr or "").strip()

                # 截断过长输出
                if len(stdout) > 5000:
                    stdout = stdout[:5000] + "\n... (已截断)"
                if len(stderr) > 5000:
                    stderr = stderr[:5000] + "\n... (已截断)"

                result["steps"].append({
                    "action": "run_command",
                    "command": command,
                    "returncode": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                })

                result["success"] = proc.returncode == 0
                if proc.returncode != 0:
                    result["error"] = f"命令返回非零状态码: {proc.returncode}"

            except subprocess.TimeoutExpired:
                result["steps"].append({
                    "action": "run_command",
                    "command": command,
                    "error": f"命令执行超时（>{timeout}秒）",
                })
                result["success"] = False

            return ToolResult(
                success=result.get("success", False),
                data=result,
                error=result.get("error")
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"运行命令失败: {e}"
            )
