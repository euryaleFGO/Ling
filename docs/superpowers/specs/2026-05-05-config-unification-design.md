# Configuration System Unification Design

**Date**: 2026-05-05
**Status**: Approved
**Scope**: Unify 3 competing config systems into one

## Problem

The project has 3 independent configuration systems that don't communicate:

1. **ConfigManager** — reads `config/settings.json`, used by GUI general_page, launcher, conversation_manager
2. **AppSettings** — reads only environment variables, used by launcher (MongoDB, WebSocket), remote clients (TTS/ASR URLs), speaker_page
3. **Direct `.env` reads** — `load_dotenv()` in multiple files, GUI api_page writes to `.env` files

**Result**: GUI changes to LLM config (via api_page.py) write to `.env`, but the backend reads from `settings.json` via ConfigManager. Changes don't take effect. MongoDB, WebSocket, and TTS URL configs live only in AppSettings, disconnected from the main config system.

## Goal

- `settings.json` becomes the single configuration source for all settings
- `.env` is only for secrets (API keys, passwords) that shouldn't be in git
- GUI reads and writes `settings.json` consistently
- Delete AppSettings and redundant `.env` files

## Design

### 1. Extended SystemConfig

Add new dataclasses for MongoDB and WebSocket configs that were previously in AppSettings:

```python
@dataclass
class MongoDBConfig:
    uri: str = "mongodb://localhost:27017"
    db_name: str = "liying_db"
    timeout_ms: int = 5000

@dataclass
class WebSocketConfig:
    host: str = "localhost"
    port: int = 8765
```

Update `SystemConfig` to include:

```python
@dataclass
class SystemConfig:
    # ... existing fields ...
    mongodb: MongoDBConfig = field(default_factory=MongoDBConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
```

### 2. Delete AppSettings

**Delete**: `src/core/settings.py`

**Migration mapping** (AppSettings field → SystemConfig field):

| AppSettings | SystemConfig | Consumers |
|---|---|---|
| `mongodb_uri` | `mongodb.uri` | launcher, asr_client |
| `mongodb_db` | `mongodb.db_name` | knowledge_dao |
| `mongodb_timeout_ms` | `mongodb.timeout_ms` | db_client |
| `ws_host` | `websocket.host` | launcher |
| `ws_port` | `websocket.port` | launcher |
| `remote_tts_url` | `tts.remote_url` | tts_remote_client |
| `remote_asr_url` | `asr.remote_url` (new) | asr_remote_client |
| `tts_model_dir` | `tts.model_dir` | speaker_page, component_init |
| `asr_model_dir` | `asr.model_dir` | component_init |
| `asr_vad_model_dir` | `asr.vad_model_dir` | component_init |
| `chroma_dir` | `advanced.chroma_dir` (new) | chroma_client |

All `AppSettings.load()` call sites → `get_config_manager().config`

### 3. GUI api_page.py writes settings.json

**Current**: writes to `.env` + `src/backend/llm/api_infer/.env`
**Target**: writes to `settings.json` via ConfigManager

Changes:
- `_apply_profile_to_envs()` → `_apply_profile_to_config()`: set `get_config_manager().config.llm.*` fields, then `get_config_manager().save()`
- `load_settings()`: read from `get_config_manager().config.llm` instead of `.env` files
- Keep `llm_profiles.json` for multi-profile management (independent storage)
- Profile switch: read profile → apply to ConfigManager config → save settings.json

### 4. Delete redundant files

- **Delete**: `src/backend/llm/api_infer/.env` — completely redundant
- **Delete**: `src/core/settings.py` — replaced by ConfigManager

### 5. Simplify api_infer/config.py

**Before** (complex fallback chain):
```python
load_dotenv()
try:
    _cfg = get_config_manager().config.llm
except:
    # 3-level env var fallback
```

**After** (direct read):
```python
from core.config_manager import get_config_manager
_cfg = get_config_manager().config.llm
DEEPSEEK_API_KEY = _cfg.api_key
BASE_URL = _cfg.base_url
MODEL = _cfg.model
```

If values are empty, that's a configuration error — log a warning, don't silently fallback.

### 6. `.env` scope: secrets only

**Keep in `.env`**:
- `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` (optional, if user prefers not in settings.json)
- `WEWORK_CORP_SECRET`, `WEWORK_SECRET`
- `MONGOD_EXE`, `MONGOD_CFG` (local paths)

**Move to `settings.json`** (no longer in `.env`):
- `MONGODB_URI`, `MONGODB_DB`
- `LIYING_WS_HOST`, `LIYING_WS_PORT`
- `LIYING_TTS_REMOTE_URL`, `REMOTE_TTS_URL`
- All LLM base_url, model, temperature, etc.

### 7. Fix known bugs during migration

- `api_page.py` `create_new_profile()` duplicated code block (lines 643-693)
- `asr_remote_client.py` missing `remote_asr_url` attribute on AppSettings
- `config_manager.py` env var names don't match `.env` variable names

### 8. Update .gitignore

```
# secrets
.env
src/backend/llm/api_infer/.env

# templates (keep in git)
# config/settings.json → provide settings.example.json
# config/llm_profiles.json → provide llm_profiles.example.json
```

## Files to modify

| File | Action |
|---|---|
| `src/core/config_manager.py` | Add MongoDBConfig, WebSocketConfig; update _apply_env_overrides |
| `src/core/settings.py` | **Delete** |
| `src/backend/llm/api_infer/config.py` | Simplify to direct ConfigManager read |
| `src/backend/llm/api_infer/.env` | **Delete** |
| `src/gui/pages/api_page.py` | Rewrite to write settings.json; fix duplicated code |
| `src/core/launcher.py` | Replace AppSettings with ConfigManager |
| `src/backend/tts/remote_client.py` | Replace AppSettings with ConfigManager |
| `src/backend/asr/remote_client.py` | Replace AppSettings with ConfigManager |
| `src/gui/pages/speaker_page.py` | Replace AppSettings with ConfigManager |
| `src/core/conversation_component_init.py` | Replace AppSettings with ConfigManager |
| `src/backend/tts/service.py` | Read from ConfigManager instead of raw env vars |
| `config/settings.json` | Add mongodb, websocket sections |
| `.env` | Remove non-secret config entries |
| `.env.example` | Update to reflect new structure |
| `.gitignore` | Add settings.json template pattern |

## Out of scope

- LLM profile hot-reload (still requires restart)
- Config validation UI in GUI
- Remote config sync
- Config migration tool for existing users
