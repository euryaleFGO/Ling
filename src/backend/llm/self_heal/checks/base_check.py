"""Base classes for health checks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CheckResult:
    """Result returned by a health check."""

    is_unhealthy: bool
    event_type: str
    severity: str  # low, medium, high, critical
    data: Dict[str, Any]


class HealthCheck(ABC):
    """Abstract base class for all health checks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name identifying this check."""
        ...

    @property
    @abstractmethod
    def interval(self) -> float:
        """Seconds to wait between consecutive runs of this check."""
        ...

    @abstractmethod
    def run(self) -> CheckResult:
        """Execute the check and return a CheckResult."""
        ...
