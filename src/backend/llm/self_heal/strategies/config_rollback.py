"""ConfigRollbackStrategy — rollback configuration to a known-good snapshot."""

import logging
from typing import Optional

from ..event_bus import Event
from ..backup_manager import BackupManager
from .base_strategy import FixStrategy, FixResult

logger = logging.getLogger(__name__)


class ConfigRollbackStrategy(FixStrategy):
    """Rollback configuration files to the last known-good snapshot.

    Requires a :class:`BackupManager` instance.  The event's
    ``data["snapshot"]`` key may provide a specific
    :class:`~backend.llm.self_heal.backup_manager.Snapshot` to restore;
    otherwise the most recent snapshot is used.
    """

    def __init__(self, backup_manager: Optional[BackupManager] = None):
        self._backup_manager = backup_manager

    def set_backup_manager(self, backup_manager: BackupManager) -> None:
        """Set or replace the backup manager instance."""
        self._backup_manager = backup_manager

    def can_handle(self, event: Event) -> bool:
        """Handle events that indicate config corruption or are explicitly
        marked as config-related."""
        if event.data.get("config_files"):
            return True
        return event.type in ("config_error", "config_corruption", "config_invalid")

    def fix(self, event: Event) -> FixResult:
        """Attempt to rollback config to the last snapshot."""
        if self._backup_manager is None:
            return FixResult(
                success=False,
                message="No BackupManager configured for rollback",
            )

        # Use explicit snapshot if provided, else take the most recent
        snapshot = event.data.get("snapshot")
        if snapshot is None:
            snapshots = self._backup_manager.list_snapshots()
            if not snapshots:
                return FixResult(
                    success=False,
                    message="No snapshots available for rollback",
                )
            snapshot = snapshots[-1]

        try:
            ok = self._backup_manager.rollback(snapshot)
            if ok:
                logger.info("Config rolled back to snapshot %s", snapshot.id)
                return FixResult(
                    success=True,
                    message=f"Rolled back to snapshot {snapshot.id}",
                    data={"snapshot_id": snapshot.id},
                )
            return FixResult(
                success=False,
                message=f"Rollback returned False for snapshot {snapshot.id}",
            )
        except Exception as exc:
            return FixResult(
                success=False,
                message=f"Rollback failed: {exc}",
            )
