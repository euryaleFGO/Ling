"""
LLM API 配置 — 从统一 ConfigManager 读取

优先级：ConfigManager (JSON + 环境变量) > 直接环境变量
"""

import os
from dotenv import load_dotenv

# 加载环境变量（兜底，确保 .env 在 ConfigManager 之前加载）
load_dotenv()

try:
    from core.config_manager import get_config_manager
    _cfg = get_config_manager().llm
    DEEPSEEK_API_KEY = _cfg.api_key
    BASE_URL = _cfg.base_url
    MODEL = _cfg.model
except Exception:
    # 兜底：直接读环境变量（ConfigManager 不可用时）
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY') or os.getenv('LIYING_LLM_API_KEY') or ""
    BASE_URL = os.getenv('BASE_URL') or os.getenv('LIYING_LLM_BASE_URL') or ""
    MODEL = os.getenv('MODEL') or os.getenv('LIYING_LLM_MODEL') or ""
