"""Config-validate check – ensures JSON config files are present and parseable."""

import json
import os
from typing import Any, Dict, List

from .base_check import CheckResult, HealthCheck

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

_DEFAULT_CONFIGS: List[str] = [
    os.path.join(_PROJECT_ROOT, "config", "interrupt_config.json"),
]


class ConfigValidateCheck(HealthCheck):
    """Validate that required JSON configuration files exist and are well-formed."""

    def __init__(self, config_paths: List[str] | None = None) -> None:
        self._config_paths = config_paths or list(_DEFAULT_CONFIGS)

    # ------------------------------------------------------------------
    # HealthCheck interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "config_validate"

    @property
    def interval(self) -> float:
        return 60.0

    def run(self) -> CheckResult:
        problems: List[Dict[str, Any]] = []

        for path in self._config_paths:
            if not os.path.isfile(path):
                problems.append(
                    {"file": path, "reason": "missing"}
                )
                continue

            try:
                with open(path, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except json.JSONDecodeError as exc:
                problems.append(
                    {
                        "file": path,
                        "reason": "invalid_json",
                        "error": str(exc)[:300],
                    }
                )

        if problems:
            return CheckResult(
                is_unhealthy=True,
                event_type="config_invalid",
                severity="high",
                data={"problems": problems},
            )

        return CheckResult(
            is_unhealthy=False,
            event_type="config_invalid",
            severity="low",
            data={},
        )
