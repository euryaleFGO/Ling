"""Log-watch health check – scans log files for ERROR / Exception patterns."""

import glob
import os
from typing import Any, Dict, List

from .base_check import CheckResult, HealthCheck

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")

# Patterns that indicate a problem when found in log lines.
_ERROR_PATTERNS = ("ERROR", "Exception", "Traceback")


class LogWatchCheck(HealthCheck):
    """Monitor log files for error patterns using file-position tracking."""

    def __init__(self, log_dir: str | None = None) -> None:
        self._log_dir = log_dir or _LOG_DIR
        # Maps file path -> last read position (bytes)
        self._positions: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # HealthCheck interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "log_watch"

    @property
    def interval(self) -> float:
        return 2.0

    def run(self) -> CheckResult:
        """Read only the new portion of every *.log file and look for errors."""
        hits: List[Dict[str, Any]] = []

        for log_path in glob.glob(os.path.join(self._log_dir, "*.log")):
            try:
                file_size = os.path.getsize(log_path)
                last_pos = self._positions.get(log_path, 0)

                # If the file was truncated / rotated, start from the beginning.
                if file_size < last_pos:
                    last_pos = 0

                if file_size == last_pos:
                    continue  # nothing new to read

                with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                    fh.seek(last_pos)
                    new_content = fh.read()
                    self._positions[log_path] = fh.tell()

                for line in new_content.splitlines():
                    if any(pat in line for pat in _ERROR_PATTERNS):
                        hits.append(
                            {
                                "file": os.path.basename(log_path),
                                "line": line.strip()[:500],
                            }
                        )
            except OSError:
                # File might have been deleted between glob and open – skip it.
                continue

        if hits:
            return CheckResult(
                is_unhealthy=True,
                event_type="log_error_detected",
                severity="medium",
                data={"errors": hits[:20]},  # cap to avoid huge payloads
            )

        return CheckResult(
            is_unhealthy=False,
            event_type="log_error_detected",
            severity="low",
            data={},
        )
