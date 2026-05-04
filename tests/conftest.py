# -*- coding: utf-8 -*-
"""
pytest 配置和共享 fixtures
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


@pytest.fixture
def sample_text():
    """示例文本"""
    return "你好，我是玲，一个智能虚拟助手。"


@pytest.fixture
def sample_audio():
    """示例音频数据（1秒静音）"""
    import numpy as np
    return np.zeros(16000, dtype=np.float32)


@pytest.fixture
def mock_config():
    """模拟配置"""
    from core.config_manager import SystemConfig
    return SystemConfig()
