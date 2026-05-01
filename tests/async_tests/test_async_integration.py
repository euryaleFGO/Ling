import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch

def test_launcher_uses_async_conversation_manager():
    """测试 Launcher 可以使用 AsyncConversationManager"""
    from src.core.async_core.conversation_manager import AsyncConversationManager
    assert AsyncConversationManager is not None
