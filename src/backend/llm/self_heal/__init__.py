"""Self-healing system for the Liying AI assistant.

Provides event-driven error detection, automatic repair strategies,
health monitoring, backup/rollback, and safety guards.
"""

from .event_bus import Event, EventBus
from .health_monitor import HealthMonitor
from .error_handler import ErrorHandler
from .backup_manager import BackupManager
from .rate_limiter import RateLimiter
from .emergency_stop import EmergencyStop, EmergencyStopError
from .checks import (
    CheckResult,
    HealthCheck,
    LogWatchCheck,
    ServiceHealthCheck,
    ConfigValidateCheck,
    PerformanceCheck,
)
from .strategies import (
    FixStrategy,
    FixResult,
    RetryStrategy,
    ServiceRestartStrategy,
    ConfigRollbackStrategy,
    NotifyUserStrategy,
)

__all__ = [
    "Event",
    "EventBus",
    "HealthMonitor",
    "ErrorHandler",
    "BackupManager",
    "RateLimiter",
    "EmergencyStop",
    "EmergencyStopError",
    "CheckResult",
    "HealthCheck",
    "LogWatchCheck",
    "ServiceHealthCheck",
    "ConfigValidateCheck",
    "PerformanceCheck",
    "FixStrategy",
    "FixResult",
    "RetryStrategy",
    "ServiceRestartStrategy",
    "ConfigRollbackStrategy",
    "NotifyUserStrategy",
]
