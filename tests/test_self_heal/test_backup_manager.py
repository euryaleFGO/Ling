import os
import sys
import tempfile
import shutil

import pytest

# Ensure src is on the path so we can import the package under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.backend.llm.self_heal.backup_manager import BackupManager, Snapshot


@pytest.fixture
def tmp_backup_env():
    """Create an isolated temp directory for each test."""
    tmp = tempfile.mkdtemp(prefix="backup_test_")
    backup_dir = os.path.join(tmp, "data", "backups", "snapshots")
    yield backup_dir, tmp
    shutil.rmtree(tmp, ignore_errors=True)


class TestCreateSnapshot:
    def test_create_snapshot(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        # Create a test file
        test_file = os.path.join(tmp, "test.py")
        with open(test_file, "w") as f:
            f.write("print('hello')")

        snapshot = manager.create_snapshot([test_file], reason="pre-change")

        assert isinstance(snapshot, Snapshot)
        assert isinstance(snapshot.id, str)
        assert len(snapshot.id) > 0
        assert snapshot.reason == "pre-change"
        assert test_file in snapshot.file_paths
        assert snapshot.timestamp > 0
        assert os.path.isdir(snapshot.backup_dir)

        # Verify backup file exists
        backup_files = os.listdir(snapshot.backup_dir)
        assert len(backup_files) >= 1

    def test_create_snapshot_multiple_files(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        files = []
        for name in ["a.py", "b.py", "c.py"]:
            fp = os.path.join(tmp, name)
            with open(fp, "w") as f:
                f.write(f"# {name}")
            files.append(fp)

        snapshot = manager.create_snapshot(files, reason="multi")

        assert len(snapshot.file_paths) == 3


class TestRollback:
    def test_rollback_restores_file(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        # Create and backup
        test_file = os.path.join(tmp, "config.json")
        with open(test_file, "w") as f:
            f.write('{"version": 1}')

        snapshot = manager.create_snapshot([test_file], reason="before edit")

        # Modify the file
        with open(test_file, "w") as f:
            f.write('{"version": 999}')
        with open(test_file) as f:
            assert f.read() == '{"version": 999}'

        # Rollback
        success = manager.rollback(snapshot)
        assert success is True

        # Verify restored
        with open(test_file) as f:
            assert f.read() == '{"version": 1}'

    def test_rollback_nonexistent_snapshot_dir(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        test_file = os.path.join(tmp, "file.txt")
        with open(test_file, "w") as f:
            f.write("original")

        snapshot = manager.create_snapshot([test_file], reason="test")

        # Remove the backup dir to simulate corruption
        shutil.rmtree(snapshot.backup_dir, ignore_errors=True)

        # Rollback should not crash
        success = manager.rollback(snapshot)
        # It should still return True since the file wasn't in backup after removal
        # OR it could return False - either way, no exception


class TestListSnapshots:
    def test_list_snapshots(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        assert manager.list_snapshots() == []

        test_file = os.path.join(tmp, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")

        s1 = manager.create_snapshot([test_file], reason="first")
        s2 = manager.create_snapshot([test_file], reason="second")
        s3 = manager.create_snapshot([test_file], reason="third")

        snapshots = manager.list_snapshots()
        assert len(snapshots) == 3
        assert snapshots[0].reason == "first"
        assert snapshots[1].reason == "second"
        assert snapshots[2].reason == "third"

    def test_list_snapshots_returns_copy(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        test_file = os.path.join(tmp, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")

        manager.create_snapshot([test_file], reason="only")

        snapshots = manager.list_snapshots()
        snapshots.clear()  # Modify the returned list
        # Original should be unaffected
        assert len(manager.list_snapshots()) == 1


class TestCleanupOld:
    def test_cleanup_old(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        test_file = os.path.join(tmp, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")

        for i in range(25):
            manager.create_snapshot([test_file], reason=f"snap-{i}")

        assert len(manager.list_snapshots()) == 25

        removed = manager.cleanup_old(keep=10)
        assert removed == 15
        assert len(manager.list_snapshots()) == 10

        # Verify oldest were removed
        remaining = manager.list_snapshots()
        assert remaining[0].reason == "snap-15"
        assert remaining[-1].reason == "snap-24"

    def test_cleanup_old_noop(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        test_file = os.path.join(tmp, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")

        for i in range(5):
            manager.create_snapshot([test_file], reason=f"snap-{i}")

        removed = manager.cleanup_old(keep=10)
        assert removed == 0
        assert len(manager.list_snapshots()) == 5


class TestNonexistentFileSnapshot:
    def test_nonexistent_file_snapshot(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        missing = os.path.join(tmp, "does_not_exist.py")
        snapshot = manager.create_snapshot([missing], reason="missing file")

        # Snapshot should be created but with empty file_paths
        assert len(snapshot.file_paths) == 0
        assert snapshot.reason == "missing file"

    def test_mixed_existing_and_missing(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env
        manager = BackupManager(backup_dir=backup_dir)

        existing = os.path.join(tmp, "exists.py")
        with open(existing, "w") as f:
            f.write("# exists")

        missing = os.path.join(tmp, "missing.py")

        snapshot = manager.create_snapshot([existing, missing], reason="mixed")

        assert len(snapshot.file_paths) == 1
        assert existing in snapshot.file_paths
        assert missing not in snapshot.file_paths


class TestIndexPersistence:
    def test_index_persists_across_instances(self, tmp_backup_env):
        backup_dir, tmp = tmp_backup_env

        test_file = os.path.join(tmp, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1")

        # Create snapshots with first manager
        manager1 = BackupManager(backup_dir=backup_dir)
        manager1.create_snapshot([test_file], reason="first")
        manager1.create_snapshot([test_file], reason="second")

        # Load with new manager instance
        manager2 = BackupManager(backup_dir=backup_dir)
        snapshots = manager2.list_snapshots()
        assert len(snapshots) == 2
        assert snapshots[0].reason == "first"
        assert snapshots[1].reason == "second"
