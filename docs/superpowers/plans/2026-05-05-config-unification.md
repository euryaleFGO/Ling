# Config System Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify 3 competing config systems (ConfigManager, AppSettings, direct .env) into a single `settings.json`-based configuration source.

**Architecture:** Extend `ConfigManager`'s `SystemConfig` with MongoDB, WebSocket, and Chroma fields. Migrate all `AppSettings` consumers to `ConfigManager`. Rewrite GUI `api_page.py` to write `settings.json` instead of `.env`. Delete `AppSettings` and redundant `.env` files.

**Tech Stack:** Python, dataclasses, JSON config, PyQt6 (GUI)

**Spec:** `docs/superpowers/specs/2026-05-05-config-unification-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/core/config_manager.py` | Modify | Add MongoDBConfig, WebSocketConfig, ASRConfig.remote_url, AdvancedConfig.chroma_dir |
| `config/settings.json` | Modify | Add mongodb, websocket sections with defaults |
| `src/backend/llm/api_infer/config.py` | Modify | Simplify to direct ConfigManager read |
| `src/gui/pages/api_page.py` | Modify | Write settings.json instead of .env; fix duplicated code |
| `src/core/launcher.py` | Modify | Replace AppSettings with ConfigManager |
| `src/backend/tts/remote_client.py` | Modify | Replace AppSettings with ConfigManager |
| `src/backend/asr/remote_client.py` | Modify | Replace AppSettings with ConfigManager |
| `src/gui/pages/speaker_page.py` | Modify | Replace AppSettings with ConfigManager |
| `src/core/conversation_component_init.py` | Modify | Remove AppSettings fallbacks |
| `src/backend/llm/database/mongo_client.py` | Modify | Replace AppSettings with ConfigManager |
| `src/gui/main_window.py` | Modify | Replace AppSettings with ConfigManager |
| `src/core/conversation/asr_handler.py` | Modify | Replace AppSettings with ConfigManager |
| `src/core/conversation/tts_handler.py` | Modify | Replace AppSettings with ConfigManager |
| `src/backend/tts/service.py` | Modify | Read from ConfigManager |
| `.env` | Modify | Remove non-secret config entries |
| `.env.example` | Modify | Update to reflect new structure |
| `.gitignore` | Modify | Ensure .env is ignored |
| `src/core/settings.py` | **Delete** | Replaced by ConfigManager |
| `src/backend/llm/api_infer/.env` | **Delete** | Replaced by settings.json |

---

## Task 1: Extend ConfigManager with new dataclasses

**Files:**
- Modify: `src/core/config_manager.py:31-193`

- [ ] **Step 1: Add MongoDBConfig and WebSocketConfig dataclasses**

After the existing `GeneralConfig` class (line 172), add:

```python
@dataclass
class MongoDBConfig:
    """MongoDB 配置"""
    uri: str = "mongodb://localhost:27017"
    db_name: str = "liying_db"
    timeout_ms: int = 5000


@dataclass
class WebSocketConfig:
    """WebSocket 消息服务配置"""
    host: str = "localhost"
    port: int = 8765
```

- [ ] **Step 2: Add `remote_url` to ASRConfig and `chroma_dir` to AdvancedConfig**

In `ASRConfig` (line 42-54), add after `cache_warmup`:

```python
    remote_url: str = ""
```

In `AdvancedConfig` (line 160-164), add after `auto_optimize`:

```python
    chroma_dir: str = ""
```

- [ ] **Step 3: Add mongodb and websocket fields to SystemConfig**

In `SystemConfig` (line 176-192), add after `general`:

```python
    mongodb: MongoDBConfig = field(default_factory=MongoDBConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
```

- [ ] **Step 4: Update _parse_config to parse new sections**

In `_parse_config` method (line 297-361), add after the `general` block:

```python
        # MongoDB
        if "mongodb" in data:
            config.mongodb = _parse_sub_config(data["mongodb"], MongoDBConfig)

        # WebSocket
        if "websocket" in data:
            config.websocket = _parse_sub_config(data["websocket"], WebSocketConfig)
```

- [ ] **Step 5: Update _apply_env_overrides for new fields**

In `_apply_env_overrides` (line 257-295), add after the `general` block:

```python
        # MongoDB
        if not c.mongodb.uri or c.mongodb.uri == "mongodb://localhost:27017":
            env_uri = os.environ.get("MONGODB_URI")
            if env_uri:
                c.mongodb.uri = env_uri
        if not c.mongodb.db_name or c.mongodb.db_name == "liying_db":
            env_db = os.environ.get("MONGODB_DB")
            if env_db:
                c.mongodb.db_name = env_db

        # WebSocket
        if not c.websocket.host or c.websocket.host == "localhost":
            env_host = os.environ.get("LIYING_WS_HOST")
            if env_host:
                c.websocket.host = env_host
        if c.websocket.port == 8765:
            env_port = os.environ.get("LIYING_WS_PORT")
            if env_port:
                c.websocket.port = int(env_port)

        # ASR remote URL
        if not c.asr.remote_url:
            env_asr = os.environ.get("LIYING_ASR_REMOTE_URL") or os.environ.get("REMOTE_ASR_URL")
            if env_asr:
                c.asr.remote_url = env_asr

        # Chroma
        if not c.advanced.chroma_dir:
            env_chroma = os.environ.get("LIYING_CHROMA_DIR")
            if env_chroma:
                c.advanced.chroma_dir = env_chroma
```

- [ ] **Step 6: Update save() to include new sections**

In `save()` method (line 403-527), add to the `data` dict after `"general"`:

```python
            "mongodb": {
                "uri": c.mongodb.uri,
                "db_name": c.mongodb.db_name,
                "timeout_ms": c.mongodb.timeout_ms,
            },
            "websocket": {
                "host": c.websocket.host,
                "port": c.websocket.port,
            },
```

Also add `"remote_url": c.asr.remote_url` to the `"asr"` dict and `"chroma_dir": c.advanced.chroma_dir` to the `"advanced"` dict.

- [ ] **Step 7: Commit**

```bash
git add src/core/config_manager.py
git commit -m "feat(config): add MongoDBConfig, WebSocketConfig, ASR.remote_url, Advanced.chroma_dir"
```

---

## Task 2: Update settings.json with new sections

**Files:**
- Modify: `config/settings.json`

- [ ] **Step 1: Add mongodb and websocket sections**

Read the current file, then add after the `"general"` section (before the closing `}`):

```json
  "mongodb": {
    "uri": "mongodb://localhost:27017",
    "db_name": "liying_db",
    "timeout_ms": 5000
  },
  "websocket": {
    "host": "localhost",
    "port": 8765
  }
```

Also update the `"asr"` section to include `"remote_url": ""` and the `"advanced"` section to include `"chroma_dir": ""`.

- [ ] **Step 2: Commit**

```bash
git add config/settings.json
git commit -m "feat(config): add mongodb and websocket sections to settings.json"
```

---

## Task 3: Simplify api_infer/config.py

**Files:**
- Modify: `src/backend/llm/api_infer/config.py`

- [ ] **Step 1: Rewrite the file**

Replace the entire file content with:

```python
"""
LLM API 配置 — 从统一 ConfigManager 读取

优先级：ConfigManager (JSON + 环境变量)
"""

import logging

logger = logging.getLogger(__name__)

try:
    from core.config_manager import get_config_manager
    _cfg = get_config_manager().config.llm
    DEEPSEEK_API_KEY = _cfg.api_key
    BASE_URL = _cfg.base_url
    MODEL = _cfg.model
except Exception as e:
    logger.warning(f"Failed to load LLM config from ConfigManager: {e}")
    DEEPSEEK_API_KEY = ""
    BASE_URL = ""
    MODEL = ""
```

- [ ] **Step 2: Verify no other file imports load_dotenv from this module**

Run: `grep -r "from backend.llm.api_infer.config import" src/`
Expected: Only agent.py, chat_service.py, openai_infer.py, __init__.py — none of which use load_dotenv.

- [ ] **Step 3: Commit**

```bash
git add src/backend/llm/api_infer/config.py
git commit -m "refactor(config): simplify api_infer config to direct ConfigManager read"
```

---

## Task 4: Rewrite api_page.py to write settings.json

**Files:**
- Modify: `src/gui/pages/api_page.py`

- [ ] **Step 1: Update imports**

Replace the imports section. Remove references to `.env` paths. Add ConfigManager import:

```python
import sys
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QComboBox,
    QFormLayout, QMessageBox, QScrollArea, QCheckBox,
    QInputDialog, QFrame, QDialog
)
from PyQt6.QtCore import Qt
import os
from pathlib import Path
from core.config_manager import get_config_manager
```

- [ ] **Step 2: Update __init__ to remove .env paths**

In `__init__` (line 117-126), remove `self.env_path` and `self.backend_env_path`. Keep `self.profiles_path`:

```python
    def __init__(self):
        super().__init__()
        project_root = Path(__file__).parent.parent.parent.parent
        self.profiles_path = project_root / "config" / "llm_profiles.json"
        self._profiles: dict = {"active": "", "profiles": {}}
        self._loading = False
        self.init_ui()
        self.load_settings()
```

- [ ] **Step 3: Replace _apply_profile_to_envs with _apply_profile_to_config**

Replace the `_apply_profile_to_envs` method (line 504-527) with:

```python
    def _apply_profile_to_config(self, profile: dict):
        """Apply profile to ConfigManager and save settings.json"""
        cfg = get_config_manager()
        if profile.get("api_base"):
            cfg.config.llm.base_url = profile["api_base"]
        if profile.get("api_key"):
            cfg.config.llm.api_key = profile["api_key"]
        if profile.get("model"):
            cfg.config.llm.model = profile["model"]
        if profile.get("temperature"):
            try:
                cfg.config.llm.temperature = float(profile["temperature"])
            except ValueError:
                pass
        if profile.get("max_tokens"):
            try:
                cfg.config.llm.max_tokens = int(profile["max_tokens"])
            except ValueError:
                pass
        if profile.get("timeout"):
            try:
                cfg.config.llm.timeout = int(profile["timeout"])
            except ValueError:
                pass
        cfg.save()
```

- [ ] **Step 4: Update load_settings to read from ConfigManager**

Replace `load_settings` (line 566-591) with:

```python
    def load_settings(self):
        self.load_profiles()
        self._refresh_profile_combo()

        active = self._profiles.get("active", "")
        profiles = self._profiles.get("profiles", {})

        if active and active in profiles:
            self._apply_profile_to_form(profiles[active])
        else:
            try:
                llm = get_config_manager().config.llm
                self.api_base_edit.setText(llm.base_url)
                self.api_key_edit.setText(llm.api_key)
                if llm.model:
                    self.model_combo.setCurrentText(llm.model)
                if llm.temperature:
                    self.temperature_edit.setText(str(llm.temperature))
                if llm.max_tokens:
                    self.max_tokens_edit.setText(str(llm.max_tokens))
                if llm.timeout:
                    self.timeout_edit.setText(str(llm.timeout))
            except Exception as e:
                print(f"加载 API 设置失败: {e}")
```

- [ ] **Step 5: Update switch_to_selected_profile**

Replace line 705 `self._apply_profile_to_envs(profiles[name])` with `self._apply_profile_to_config(profiles[name])`.

- [ ] **Step 6: Update save_to_current_profile**

Replace line 725 `self._apply_profile_to_envs(profile_data)` with `self._apply_profile_to_config(profile_data)`.

- [ ] **Step 7: Fix duplicated code in create_new_profile**

Remove the duplicated block (lines 669-693). Keep only the first occurrence (lines 643-667).

- [ ] **Step 8: Commit**

```bash
git add src/gui/pages/api_page.py
git commit -m "refactor(gui): api_page writes settings.json instead of .env"
```

---

## Task 5: Migrate launcher.py from AppSettings to ConfigManager

**Files:**
- Modify: `src/core/launcher.py`

- [ ] **Step 1: Remove AppSettings import**

In `launcher.py` line 18, remove:
```python
from core.settings import AppSettings
```

Add if not present:
```python
from core.config_manager import get_config_manager
```

- [ ] **Step 2: Replace AppSettings.load() in ensure_mongodb_service**

In `_is_mongodb_running` (line 177-215), replace:
```python
        s = AppSettings.load()
```
with:
```python
        s = get_config_manager().config
```

Then update references:
- `s.mongodb_uri` → `s.mongodb.uri`

- [ ] **Step 3: Replace AppSettings in _start_message_server**

In `_start_message_server` (line 630-644), replace:
```python
            s = AppSettings.load()
            self._message_server = create_server(s.ws_port, host=s.ws_host)
```
with:
```python
            cfg = get_config_manager().config
            self._message_server = create_server(cfg.websocket.port, host=cfg.websocket.host)
```

- [ ] **Step 4: Commit**

```bash
git add src/core/launcher.py
git commit -m "refactor(launcher): replace AppSettings with ConfigManager"
```

---

## Task 6: Migrate tts/remote_client.py

**Files:**
- Modify: `src/backend/tts/remote_client.py`

- [ ] **Step 1: Replace AppSettings with ConfigManager**

Find the two AppSettings blocks (lines 61-64 and 70-73). Replace both with:

```python
            from core.config_manager import get_config_manager
            cfg = get_config_manager().config
            base_url = cfg.tts.remote_url
```

Remove the `try/except` around the import since ConfigManager is always available.

- [ ] **Step 2: Commit**

```bash
git add src/backend/tts/remote_client.py
git commit -m "refactor(tts): replace AppSettings with ConfigManager in remote_client"
```

---

## Task 7: Migrate asr/remote_client.py

**Files:**
- Modify: `src/backend/asr/remote_client.py`

- [ ] **Step 1: Replace AppSettings with ConfigManager**

Find the two AppSettings blocks (lines 54-57 and 63-66). Replace both with:

```python
            from core.config_manager import get_config_manager
            cfg = get_config_manager().config
            base_url = cfg.asr.remote_url or "http://localhost:5002"
```

- [ ] **Step 2: Commit**

```bash
git add src/backend/asr/remote_client.py
git commit -m "refactor(asr): replace AppSettings with ConfigManager in remote_client"
```

---

## Task 8: Migrate remaining AppSettings consumers

**Files:**
- Modify: `src/gui/pages/speaker_page.py`
- Modify: `src/core/conversation_component_init.py`
- Modify: `src/backend/llm/database/mongo_client.py`
- Modify: `src/gui/main_window.py`
- Modify: `src/core/conversation/asr_handler.py`
- Modify: `src/core/conversation/tts_handler.py`

- [ ] **Step 1: Migrate speaker_page.py**

In `speaker_page.py` lines 53-55, replace:
```python
            from core.settings import AppSettings
            s = AppSettings.load()
            tts_model_dir = Path(s.tts_model_dir)
```
with:
```python
            from core.config_manager import get_config_manager
            cfg = get_config_manager().config
            tts_model_dir = Path(cfg.tts.model_dir) if cfg.tts.model_dir else None
```

Keep the fallback at line 58.

- [ ] **Step 2: Migrate conversation_component_init.py**

Remove all three AppSettings blocks (lines 146-149, 162-165, 236-239). The `self.config` is already `SystemConfig` from ConfigManager, so `self.config.asr.model_dir`, `self.config.asr.vad_model_dir`, and `self.config.tts.model_dir` already exist. The AppSettings fallback is redundant.

- [ ] **Step 3: Migrate mongo_client.py**

In `mongo_client.py` lines 168-169, replace:
```python
        from core.settings import AppSettings
        s = AppSettings.load()
        mongo_uri = s.mongodb_uri
        mongo_db = s.mongodb_db
```
with:
```python
        from core.config_manager import get_config_manager
        cfg = get_config_manager().config
        mongo_uri = cfg.mongodb.uri
        mongo_db = cfg.mongodb.db_name
```

- [ ] **Step 4: Migrate main_window.py**

In `main_window.py` lines 143-144, replace:
```python
        from core.settings import AppSettings
        s = AppSettings.load()
        mongo_uri = s.mongodb_uri
```
with:
```python
        from core.config_manager import get_config_manager
        cfg = get_config_manager().config
        mongo_uri = cfg.mongodb.uri
```

- [ ] **Step 5: Migrate conversation/asr_handler.py**

In `asr_handler.py` lines 113-114 and 130-131, replace:
```python
            from core.settings import AppSettings
            s = AppSettings.load()
            model_dir = s.asr_model_dir
```
with:
```python
            from core.config_manager import get_config_manager
            cfg = get_config_manager().config
            model_dir = cfg.asr.model_dir
```

Same pattern for vad_dir: `s.asr_vad_dir` → `cfg.asr.vad_model_dir`.

- [ ] **Step 6: Migrate conversation/tts_handler.py**

In `tts_handler.py` lines 99-100, replace:
```python
            from core.settings import AppSettings
            s = AppSettings.load()
            model_dir = s.tts_model_dir
```
with:
```python
            from core.config_manager import get_config_manager
            cfg = get_config_manager().config
            model_dir = cfg.tts.model_dir
```

- [ ] **Step 7: Migrate tts/service.py**

In `tts/service.py`, replace raw env var reads (lines 38-39) with:
```python
from core.config_manager import get_config_manager
_cfg = get_config_manager().config
DEFAULT_MODEL_PATH = _cfg.tts.model_dir or os.path.join(BASE_DIR, '..', '..', '..', '..', 'Model', 'CosyVoice2-0.5B')
DEFAULT_REF_AUDIO = os.getenv('COSYVOICE_REF_AUDIO', os.path.join(BASE_DIR, '..', '..', '..', '..', 'Model', 'zjj.wav'))
```

- [ ] **Step 8: Commit**

```bash
git add src/gui/pages/speaker_page.py src/core/conversation_component_init.py \
        src/backend/llm/database/mongo_client.py src/gui/main_window.py \
        src/core/conversation/asr_handler.py src/core/conversation/tts_handler.py \
        src/backend/tts/service.py
git commit -m "refactor: migrate all AppSettings consumers to ConfigManager"
```

---

## Task 9: Delete AppSettings and redundant .env

**Files:**
- Delete: `src/core/settings.py`
- Delete: `src/backend/llm/api_infer/.env`

- [ ] **Step 1: Verify no remaining imports of AppSettings**

Run: `grep -rn "from core.settings import\|import core.settings\|AppSettings" src/`
Expected: No results.

- [ ] **Step 2: Delete settings.py**

```bash
rm src/core/settings.py
```

- [ ] **Step 3: Delete api_infer/.env**

```bash
rm src/backend/llm/api_infer/.env
```

- [ ] **Step 4: Verify project still starts**

Run: `python main.py --no-voice` (or appropriate test command)
Expected: Starts without ImportError for core.settings.

- [ ] **Step 5: Commit**

```bash
git add -u src/core/settings.py src/backend/llm/api_infer/.env
git commit -m "chore: delete AppSettings and redundant api_infer/.env"
```

---

## Task 10: Update .env, .env.example, and .gitignore

**Files:**
- Modify: `.env`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Clean up .env**

Remove non-secret entries that are now in settings.json:
- Remove `MONGODB_URI`, `MONGODB_DB`
- Remove `LIYING_WS_HOST`, `LIYING_WS_PORT`
- Remove `REMOTE_TTS_URL` (keep `LIYING_TTS_REMOTE_URL` as it's used by TTS remote client)
- Remove `LIYING_TTS_SPK_ID` (now in settings.json tts section)

Keep secrets:
- `OPENAI_API_BASE`, `OPENAI_API_KEY`, `OPENAI_MODEL`
- `WEWORK_*` credentials
- `MONGOD_EXE`, `MONGOD_CFG`

- [ ] **Step 2: Update .env.example**

Update to reflect the new structure. Add comments explaining that LLM, MongoDB, WebSocket configs are now in `config/settings.json`.

- [ ] **Step 3: Update .gitignore**

Ensure `.env` is properly ignored. Add:
```
.env
.env.local
.env.*.local
src/backend/llm/api_infer/.env
```

- [ ] **Step 4: Commit**

```bash
git add .env .env.example .gitignore
git commit -m "chore: clean up .env, update .env.example and .gitignore"
```

---

## Task 11: Verify and test

- [ ] **Step 1: Run syntax check on all modified files**

```bash
python -m py_compile src/core/config_manager.py
python -m py_compile src/backend/llm/api_infer/config.py
python -m py_compile src/gui/pages/api_page.py
python -m py_compile src/core/launcher.py
python -m py_compile src/backend/tts/remote_client.py
python -m py_compile src/backend/asr/remote_client.py
python -m py_compile src/gui/pages/speaker_page.py
python -m py_compile src/core/conversation_component_init.py
python -m py_compile src/backend/llm/database/mongo_client.py
python -m py_compile src/gui/main_window.py
python -m py_compile src/core/conversation/asr_handler.py
python -m py_compile src/core/conversation/tts_handler.py
python -m py_compile src/backend/tts/service.py
```

Expected: All pass with no errors.

- [ ] **Step 2: Run existing tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: Same pass rate as before (215/219, 4 pre-existing failures).

- [ ] **Step 3: Verify startup**

Run: `python main.py --no-voice`
Expected: Starts without errors, no AppSettings import errors.

- [ ] **Step 4: Verify ConfigManager loads all new fields**

Run: `python -c "from core.config_manager import get_config_manager; c = get_config_manager().config; print(c.mongodb.uri, c.mongodb.db_name, c.websocket.host, c.websocket.port)"`
Expected: `mongodb://localhost:27017 liying_db localhost 8765`
