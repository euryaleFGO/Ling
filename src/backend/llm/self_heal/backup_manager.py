import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """A backup snapshot of files."""
    id: str
    timestamp: float
    reason: str
    file_paths: List[str]
    backup_dir: str


class BackupManager:
    """Creates file snapshots and rolls back on failure."""

    def __init__(self, backup_dir: str = "data/backups/snapshots"):
        self._backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        self._snapshots: List[Snapshot] = []
        self._index_path = os.path.join(os.path.dirname(backup_dir), "index.json")
        self._load_index()

    def _load_index(self):
        if os.path.exists(self._index_path):
            try:
                with open(self._index_path) as f:
                    data = json.load(f)
                self._snapshots = [Snapshot(**s) for s in data]
            except Exception:
                logger.warning("Failed to load backup index from %s, resetting snapshots", self._index_path, exc_info=True)
                self._snapshots = []

    def _save_index(self):
        data = [
            {"id": s.id, "timestamp": s.timestamp, "reason": s.reason,
             "file_paths": s.file_paths, "backup_dir": s.backup_dir}
            for s in self._snapshots
        ]
        os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
        with open(self._index_path, "w") as f:
            json.dump(data, f, indent=2)

    def create_snapshot(self, file_paths: List[str], reason: str = "") -> Snapshot:
        snap_id = str(int(time.time() * 1000))
        snap_dir = os.path.join(self._backup_dir, snap_id)
        os.makedirs(snap_dir, exist_ok=True)

        backed_up = []
        for fp in file_paths:
            if os.path.exists(fp):
                rel_path = fp.replace("\\", "/")
                if ":" in rel_path:
                    rel_path = rel_path.split(":", 1)[1]
                dest = os.path.join(snap_dir, rel_path.lstrip("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(fp, dest)
                backed_up.append(fp)

        snapshot = Snapshot(id=snap_id, timestamp=time.time(), reason=reason,
                           file_paths=backed_up, backup_dir=snap_dir)
        self._snapshots.append(snapshot)
        self._save_index()
        return snapshot

    def rollback(self, snapshot: Snapshot) -> bool:
        try:
            for fp in snapshot.file_paths:
                rel_path = fp.replace("\\", "/")
                if ":" in rel_path:
                    rel_path = rel_path.split(":", 1)[1]
                src = os.path.join(snapshot.backup_dir, rel_path.lstrip("/"))
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    shutil.copy2(src, fp)
            return True
        except Exception:
            logger.error("Failed to rollback snapshot %s", snapshot.id, exc_info=True)
            return False

    def list_snapshots(self) -> List[Snapshot]:
        return list(self._snapshots)

    def cleanup_old(self, keep: int = 20) -> int:
        if len(self._snapshots) <= keep:
            return 0
        to_remove = self._snapshots[:-keep]
        for snap in to_remove:
            try:
                shutil.rmtree(snap.backup_dir, ignore_errors=True)
            except Exception:
                logger.debug("Failed to remove backup directory %s", snap.backup_dir, exc_info=True)
        self._snapshots = self._snapshots[-keep:]
        self._save_index()
        return len(to_remove)
