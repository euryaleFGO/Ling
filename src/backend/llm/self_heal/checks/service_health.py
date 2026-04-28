"""Service-health check – pings external HTTP /health endpoints."""

import urllib.request
import urllib.error
from typing import Any, Dict, List, Tuple

from .base_check import CheckResult, HealthCheck

# Default services to probe (name -> base URL).
_DEFAULT_SERVICES: Dict[str, str] = {
    "tts": "http://127.0.0.1:8000/health",
    "asr": "http://127.0.0.1:8001/health",
}

_TIMEOUT_SECONDS = 5


class ServiceHealthCheck(HealthCheck):
    """Verify that dependent external services are reachable via HTTP."""

    def __init__(
        self,
        services: Dict[str, str] | None = None,
        failure_threshold: int = 2,
    ) -> None:
        self._services = services or dict(_DEFAULT_SERVICES)
        self._failure_threshold = failure_threshold
        # Tracks consecutive failures per service.
        self._consecutive_failures: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # HealthCheck interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "service_health"

    @property
    def interval(self) -> float:
        return 30.0

    def run(self) -> CheckResult:
        unhealthy_services: List[Dict[str, Any]] = []

        for svc_name, url in self._services.items():
            try:
                req = urllib.request.Request(
                    url, method="GET", headers={"User-Agent": "Liying-HealthCheck"}
                )
                with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                    if resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status}")
                # Success – reset failure counter.
                self._consecutive_failures.pop(svc_name, None)
            except (urllib.error.URLError, OSError, RuntimeError) as exc:
                count = self._consecutive_failures.get(svc_name, 0) + 1
                self._consecutive_failures[svc_name] = count
                if count >= self._failure_threshold:
                    unhealthy_services.append(
                        {
                            "service": svc_name,
                            "url": url,
                            "consecutive_failures": count,
                            "error": str(exc)[:300],
                        }
                    )

        if unhealthy_services:
            return CheckResult(
                is_unhealthy=True,
                event_type="service_unreachable",
                severity="high",
                data={"services": unhealthy_services},
            )

        return CheckResult(
            is_unhealthy=False,
            event_type="service_unreachable",
            severity="low",
            data={},
        )
