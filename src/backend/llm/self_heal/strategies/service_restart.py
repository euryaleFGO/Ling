"""ServiceRestartStrategy — restart crashed services via subprocess."""

import logging
import subprocess
import time
from typing import Dict, List, Optional

from ..event_bus import Event
from .base_strategy import FixStrategy, FixResult

logger = logging.getLogger(__name__)

# Default service commands — extend as needed
SERVICE_COMMANDS: Dict[str, List[str]] = {
    "llm_server": ["python", "-m", "backend.llm.server"],
    "asr_server": ["python", "-m", "backend.asr.server"],
    "tts_server": ["python", "-m", "backend.tts.server"],
    "redis": ["redis-server"],
}


class ServiceRestartStrategy(FixStrategy):
    """Restart a service that has crashed or become unresponsive.

    The event's ``data["service"]`` key identifies which service to
    restart.  The strategy looks up the command in ``SERVICE_COMMANDS``
    (or a custom mapping supplied at construction time) and spawns it
    via ``subprocess.Popen``.
    """

    def __init__(
        self,
        service_commands: Optional[Dict[str, List[str]]] = None,
        startup_timeout: float = 5.0,
    ):
        self._commands = service_commands or SERVICE_COMMANDS
        self._startup_timeout = startup_timeout

    def can_handle(self, event: Event) -> bool:
        """Only handle events that reference a known service."""
        service = event.data.get("service", "")
        return service in self._commands

    def fix(self, event: Event) -> FixResult:
        """Attempt to restart the specified service."""
        service = event.data.get("service", "")
        if not service:
            return FixResult(success=False, message="No service name in event data")

        cmd = self._commands.get(service)
        if cmd is None:
            return FixResult(
                success=False,
                message=f"No command registered for service '{service}'",
            )

        try:
            logger.info("Restarting service '%s': %s", service, cmd)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Brief wait to detect immediate crash
            time.sleep(self._startup_timeout)

            if proc.poll() is not None:
                return FixResult(
                    success=False,
                    message=(
                        f"Service '{service}' exited immediately "
                        f"(exit code {proc.returncode})"
                    ),
                    data={"exit_code": proc.returncode},
                )

            return FixResult(
                success=True,
                message=f"Service '{service}' restarted (pid={proc.pid})",
                data={"pid": proc.pid},
            )

        except FileNotFoundError as exc:
            return FixResult(
                success=False,
                message=f"Command not found for '{service}': {exc}",
            )
        except Exception as exc:
            return FixResult(
                success=False,
                message=f"Failed to restart '{service}': {exc}",
            )
