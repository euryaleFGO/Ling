"""Self-healing fix strategies package.

Provides a chain-of-responsibility pattern for error recovery:
- FixStrategy: abstract base class
- RetryStrategy: retry with exponential backoff
- ServiceRestartStrategy: restart crashed services
- ConfigRollbackStrategy: rollback config to last known good snapshot
- NotifyUserStrategy: last resort user notification
"""

from .base_strategy import FixStrategy, FixResult
from .retry import RetryStrategy
from .service_restart import ServiceRestartStrategy
from .config_rollback import ConfigRollbackStrategy
from .notify_user import NotifyUserStrategy

__all__ = [
    "FixStrategy",
    "FixResult",
    "RetryStrategy",
    "ServiceRestartStrategy",
    "ConfigRollbackStrategy",
    "NotifyUserStrategy",
]
