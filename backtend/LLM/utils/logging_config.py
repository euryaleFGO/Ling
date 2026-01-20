"""
日志配置
统一的日志管理
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志格式
CONSOLE_FORMAT = "%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-25s | %(funcName)-20s | %(message)s"
DATE_FORMAT = "%H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_file: bool = True,
    console: bool = False  # 默认不输出到主控制台
):
    """
    配置日志系统
    
    Args:
        level: 日志级别
        log_file: 是否写入文件
        console: 是否输出到控制台（主终端）
    """
    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 文件处理器
    if log_file:
        log_filename = LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(file_handler)
    
    # 控制台处理器（可选）
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(console_handler)
    
    # 设置第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器"""
    return logging.getLogger(name)


# 导出便捷方法
def log_tool_call(tool_name: str, params: dict, result: any):
    """记录工具调用"""
    logger = get_logger("tools")
    logger.info(f"🔧 调用工具: {tool_name}")
    logger.info(f"   参数: {params}")
    logger.info(f"   结果: {result}")


def log_llm_request(messages_count: int, has_tools: bool):
    """记录 LLM 请求"""
    logger = get_logger("llm")
    logger.info(f"📤 LLM请求: {messages_count}条消息, 工具={'启用' if has_tools else '禁用'}")


def log_llm_response(has_tool_calls: bool, content_preview: str = ""):
    """记录 LLM 响应"""
    logger = get_logger("llm")
    if has_tool_calls:
        logger.info(f"📥 LLM响应: 请求调用工具")
    else:
        preview = content_preview[:50] + "..." if len(content_preview) > 50 else content_preview
        logger.info(f"📥 LLM响应: {preview}")


def log_error(module: str, error: Exception, context: str = ""):
    """记录错误"""
    logger = get_logger(module)
    logger.error(f"❌ 错误: {error}")
    if context:
        logger.error(f"   上下文: {context}")
    logger.exception("详细堆栈:")
