# 数据库结构（基于当前代码使用点）

本文档用于让复刻者快速理解 **MongoDB + ChromaDB** 的数据结构与初始化约定。  
对应的一键初始化脚本为：`scripts/setup_database.py`（支持 `--print-schema` 输出同等信息）。

## MongoDB（默认库名：`liying_db`）

### `conversations`
- **用途**：对话会话与消息存储（GUI 的“对话记录”页）。
- **文档结构（示意）**：
  - `session_id`: `session_xxx`
  - `user_id`: `default_user`
  - `status`: `active | closed`
  - `messages`: `[{ role, content, timestamp, emotion?, extra? }, ...]`
  - `summary`: `str | null`
  - `metadata`: `dict`
  - `created_at`, `updated_at`: `datetime`
- **索引**：`session_id`(unique)、`user_id`、`status`、`created_at`

### `long_term_memory`
- **用途**：长期记忆（GUI 的“长期记忆”页）。
- **文档结构（示意）**：
  - `memory_id`: `mem_xxx`
  - `user_id`
  - `type`: `fact | event | preference | emotion | summary`
  - `content`: `str`
  - `importance`: `float(0..1)`
  - `source`: `{ session_id, message_index } | null`
  - `tags`: `[str]`
  - `extra`: `dict`
  - `access_count`: `int`
  - `last_accessed`: `datetime | null`
  - `created_at`, `updated_at`: `datetime`
- **索引**：`user_id`、`type`、`importance`、`created_at`、`content`(text)

### `knowledge_base`
- **用途**：知识库条目（RAG 与知识管理）。
- **文档结构（示意）**：
  - `knowledge_id`: `kb_xxx`
  - `type`: `character | world | reference | faq`
  - `title`: `str | null`
  - `content`: `str`
  - `tags`: `[str]`
  - `extra`: `dict`
  - `created_at`, `updated_at`: `datetime`
- **索引**：`type`、`tags`、`content`(text)

### `character_settings`
- **用途**：角色设定（GUI 的“角色设定”页）。
- **文档结构（示意）**：
  - `character_id`: `char_xxx`
  - `name`: `str`（unique）
  - `personality`: `dict`
  - `background`: `str`
  - `system_prompt`: `str`
  - `greeting`: `str`
  - `extra`: `{ nickname, user_name }`
  - `is_active`: `bool`
  - `created_at`, `updated_at`: `datetime`
- **索引**：`name`(unique)

### `user_profiles`
- **用途**：用户档案（称呼/偏好/统计）。
- **文档结构（示意）**：
  - `user_id`: `str`（unique）
  - `nickname`: `str`
  - `preferences`: `{ call_me, topics_like, topics_avoid }`
  - `stats`: `{ total_conversations, total_messages, first_chat }`
  - `created_at`, `updated_at`
- **索引**：`user_id`(unique)

### `reminders`
- **用途**：提醒/闹钟（工具：`reminder_tool`）。
- **文档结构（示意）**：
  - `reminder_id`: `str`
  - `content`: `str`
  - `trigger_time`: `datetime`
  - `status`: `pending | triggered | cancelled`
  - `label`: `str`
- **索引**：`trigger_time`、`status`

### `knowledge_graph`
- **用途**：知识图谱三元组持久化。
- **文档结构（示意）**：
  - `user_id`: `str`
  - `triple.subject.name`: `str`
  - `triple.relation.type`: `str`
  - `triple.object.name`: `str`
  - `created_at`: `datetime`
- **索引**：
  - `user_id`
  - 复合唯一：`(user_id, triple.subject.name, triple.relation.type, triple.object.name)`

## ChromaDB（本地持久化目录方式）

- **默认目录**：`data/chroma_data/`
- **collection**：
  - `knowledge_vectors`
  - `memory_vectors`
  - `conversation_vectors`

> 注：ChromaDB 在本项目中通过 `chromadb.PersistentClient(path=...)` 直接落盘，不需要单独起服务。

