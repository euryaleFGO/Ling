"""
LLM API 配置 — 从统一 ConfigManager 读取

优先级：ConfigManager (JSON + 环境变量)
"""

import logging

logger = logging.getLogger(__name__)

try:
    from core.config_manager import get_config_manager
    _cfg = get_config_manager().config.llm
    DEEPSEEK_API_KEY = _cfg.api_key
    BASE_URL = _cfg.base_url
    MODEL = _cfg.model
except Exception as e:
    logger.warning(f"Failed to load LLM config from ConfigManager: {e}")
    DEEPSEEK_API_KEY = ""
    BASE_URL = ""
    MODEL = ""
