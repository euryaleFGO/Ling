"""
深度诊断工具
分析错误原因并给出修复建议
"""
from typing import List, Optional
import os
import glob
from datetime import datetime

from .base_tool import BaseTool, ToolParameter, ToolResult


class DiagnoseTool(BaseTool):
    """
    深度诊断工具

    收集日志、系统状态，并调用 LLM 分析错误根因。
    用于工具执行失败、服务报错、配置异常或代码出错时的诊断。
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 推理客户端（需支持 infer 方法）
        """
        self._llm = llm_client
        self._log_dir = "logs"

    @property
    def name(self) -> str:
        return "diagnose"

    @property
    def description(self) -> str:
        return """深度诊断工具，分析错误原因并给出修复建议。
当工具执行失败、服务报错、配置异常或代码出错时使用。"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="error_type",
                type="string",
                description="错误类型",
                required=True,
                enum=["tool_error", "service_error", "config_error", "code_error"]
            ),
            ToolParameter(
                name="error_message",
                type="string",
                description="错误信息",
                required=True
            ),
            ToolParameter(
                name="context",
                type="string",
                description="额外上下文（可选）",
                required=False,
                default=""
            ),
        ]

    def execute(
        self,
        error_type: str,
        error_message: str,
        context: str = "",
        **kwargs
    ) -> ToolResult:
        """
        执行深度诊断

        1. 收集匹配的错误日志
        2. 收集系统状态
        3. 调用 LLM 分析根因（如果配置了 LLM）
        4. 返回诊断结果
        """
        try:
            # 1. 收集日志
            logs = self._collect_logs(error_type, error_message)

            # 2. 收集系统状态
            status = self._collect_status()

            # 3. 调用 LLM 分析
            if self._llm:
                analysis = self._analyze_with_llm(
                    error_type=error_type,
                    error_message=error_message,
                    context=context,
                    logs=logs,
                    status=status
                )
            else:
                analysis = (
                    f"未配置 LLM 客户端，无法进行智能分析。\n"
                    f"错误类型: {error_type}\n"
                    f"错误信息: {error_message}\n"
                    f"请手动检查日志和系统状态。"
                )

            # 4. 构建诊断结果
            diagnosis = {
                "error_type": error_type,
                "error_message": error_message,
                "context": context,
                "analysis": analysis,
                "recent_logs": logs[:10],  # 最多返回10条日志
                "system_status": status,
                "timestamp": datetime.now().isoformat(),
            }

            return ToolResult(success=True, data=diagnosis)

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"诊断工具执行失败: {e}"
            )

    def _collect_logs(self, error_type: str, error_message: str) -> List[str]:
        """
        收集匹配错误的日志行

        从 logs 目录下最近的日志文件中搜索相关内容
        """
        collected = []

        try:
            if not os.path.exists(self._log_dir):
                return ["日志目录不存在"]

            # 获取所有日志文件，按修改时间排序（最新的在前）
            log_files = glob.glob(os.path.join(self._log_dir, "*.log"))
            log_files.sort(key=os.path.getmtime, reverse=True)

            # 提取关键词用于匹配
            keywords = self._extract_keywords(error_type, error_message)

            # 从最新的日志文件开始搜索
            for log_file in log_files[:3]:  # 最多搜索3个文件
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()

                    # 从后往前搜索（最新的在后面）
                    for line in reversed(lines):
                        if any(kw.lower() in line.lower() for kw in keywords):
                            collected.append(line.strip())
                            if len(collected) >= 20:  # 最多收集20条
                                break
                except Exception:
                    continue

            if not collected:
                collected = ["未找到匹配的日志记录"]

        except Exception as e:
            collected = [f"日志收集失败: {e}"]

        return collected

    def _extract_keywords(self, error_type: str, error_message: str) -> List[str]:
        """从错误信息中提取关键词"""
        keywords = []

        # 根据错误类型添加通用关键词
        type_keywords = {
            "tool_error": ["ERROR", "Tool", "tool", "执行失败"],
            "service_error": ["ERROR", "Service", "service", "连接失败", "超时"],
            "config_error": ["ERROR", "Config", "config", "配置", "找不到"],
            "code_error": ["ERROR", "Traceback", "Exception", "异常"],
        }
        keywords.extend(type_keywords.get(error_type, ["ERROR"]))

        # 从错误信息中提取有意义的词
        if error_message:
            # 提取引号中的内容
            import re
            quoted = re.findall(r'["\']([^"\']+)["\']', error_message)
            keywords.extend(quoted[:3])

            # 提取错误信息的关键部分（去除常见的连接词）
            words = error_message.split()
            for word in words:
                if len(word) > 3 and word.lower() not in ('the', 'this', 'that', 'with', 'from', 'and', 'for', '异常'):
                    keywords.append(word)
                    if len(keywords) > 10:
                        break

        return keywords[:10]  # 最多10个关键词

    def _collect_status(self) -> dict:
        """收集系统状态信息"""
        status = {}

        try:
            import psutil
            status["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            status["memory_percent"] = psutil.virtual_memory().percent
            status["disk_usage"] = psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:').percent
        except ImportError:
            status["psutil"] = "未安装"
        except Exception as e:
            status["error"] = str(e)

        # Python 版本
        import sys
        status["python_version"] = sys.version

        # 当前工作目录
        status["cwd"] = os.getcwd()

        return status

    def _analyze_with_llm(
        self,
        error_type: str,
        error_message: str,
        context: str,
        logs: List[str],
        status: dict
    ) -> str:
        """使用 LLM 分析错误根因"""
        try:
            # 构建分析提示
            logs_text = "\n".join(logs[:10]) if logs else "无日志"
            status_text = "\n".join(f"{k}: {v}" for k, v in status.items())

            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的系统诊断专家。"
                        "请分析以下错误信息、日志和系统状态，给出：\n"
                        "1. 错误根因分析\n"
                        "2. 可能的修复建议（具体操作步骤）\n"
                        "3. 预防措施\n"
                        "请用中文回答，简洁明了。"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"## 错误类型\n{error_type}\n\n"
                        f"## 错误信息\n{error_message}\n\n"
                        f"## 额外上下文\n{context or '无'}\n\n"
                        f"## 相关日志\n{logs_text}\n\n"
                        f"## 系统状态\n{status_text}"
                    )
                }
            ]

            response = self._llm.infer(messages=messages, stream=False)
            return response.choices[0].message.content

        except Exception as e:
            return f"LLM 分析失败: {e}。请手动检查错误信息和日志。"
