#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键初始化/部署数据库结构（MongoDB + 可选 ChromaDB 目录）。

特点：
- 不硬编码路径：MongoDB 使用 --mongo-uri / 环境变量 MONGODB_URI 指定
- 自动创建集合索引（按当前代码中的 DAO/工具实际使用点）
- 可选写入最小默认数据（默认 user_profile + 角色设定）

用法示例：
  python scripts/setup_database.py
  python scripts/setup_database.py --mongo-uri "mongodb://localhost:27017" --db liying_db
  python scripts/setup_database.py --seed
  python scripts/setup_database.py --print-schema
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    db_name: str
    timeout_ms: int = 5000


def _now_utc() -> datetime:
    return datetime.utcnow()


def _get_mongo_config(args: argparse.Namespace) -> MongoConfig:
    uri = args.mongo_uri or os.environ.get("MONGODB_URI") or "mongodb://localhost:27017"
    db_name = args.db or os.environ.get("MONGODB_DB") or "liying_db"
    timeout_ms = int(args.timeout_ms or os.environ.get("MONGODB_TIMEOUT_MS") or 5000)
    return MongoConfig(uri=uri, db_name=db_name, timeout_ms=timeout_ms)


def _connect_mongo(cfg: MongoConfig):
    try:
        from pymongo import MongoClient
    except Exception as e:  # pragma: no cover
        raise RuntimeError("缺少依赖 pymongo，请先安装 requirements.txt") from e

    client = MongoClient(cfg.uri, serverSelectionTimeoutMS=cfg.timeout_ms)
    # 强制触发连接校验
    client.admin.command("ping")
    return client, client[cfg.db_name]


def _ensure_indexes(db) -> dict[str, list[str]]:
    """
    按当前代码（DAO/工具）创建索引。返回 {collection: [created index names...]}。
    """
    created: dict[str, list[str]] = {}

    def remember(col: str, names: Iterable[str]):
        created.setdefault(col, []).extend(list(names))

    # conversations（src/backend/llm/database/conversation_dao.py）
    conv = db["conversations"]
    remember(
        "conversations",
        [
            conv.create_index("session_id", unique=True),
            conv.create_index("user_id"),
            conv.create_index("status"),
            conv.create_index("created_at"),
        ],
    )

    # long_term_memory（src/backend/llm/database/memory_dao.py）
    mem = db["long_term_memory"]
    remember(
        "long_term_memory",
        [
            mem.create_index("user_id"),
            mem.create_index("type"),
            mem.create_index("importance"),
            mem.create_index("created_at"),
            mem.create_index([("content", "text")]),
        ],
    )

    # knowledge_base / character_settings / user_profiles（src/backend/llm/database/knowledge_dao.py）
    kb = db["knowledge_base"]
    remember(
        "knowledge_base",
        [
            kb.create_index("type"),
            kb.create_index("tags"),
            kb.create_index([("content", "text")]),
        ],
    )

    char = db["character_settings"]
    remember("character_settings", [char.create_index("name", unique=True)])

    user = db["user_profiles"]
    remember("user_profiles", [user.create_index("user_id", unique=True)])

    # reminders（src/backend/llm/tools/reminder_tool.py）
    reminders = db["reminders"]
    remember("reminders", [reminders.create_index("trigger_time"), reminders.create_index("status")])

    # knowledge_graph（src/backend/llm/memory/knowledge_graph.py）
    kg = db["knowledge_graph"]
    # 代码里用 upsert key: user_id + triple.subject.name + triple.relation.type + triple.object.name
    remember(
        "knowledge_graph",
        [
            kg.create_index("user_id"),
            kg.create_index(
                [
                    ("user_id", 1),
                    ("triple.subject.name", 1),
                    ("triple.relation.type", 1),
                    ("triple.object.name", 1),
                ],
                unique=True,
                name="uniq_user_triple",
            ),
        ],
    )

    return created


def _seed_minimal_data(db, *, user_id: str, character_name: str) -> dict[str, Any]:
    """
    写入最小可运行的默认数据（幂等 upsert）。
    """
    now = _now_utc()

    # user_profiles
    user_doc = {
        "user_id": user_id,
        "nickname": "用户",
        "preferences": {"call_me": "用户", "topics_like": [], "topics_avoid": []},
        "stats": {"total_conversations": 0, "total_messages": 0, "first_chat": now},
        "created_at": now,
        "updated_at": now,
    }
    db["user_profiles"].update_one({"user_id": user_id}, {"$setOnInsert": user_doc}, upsert=True)

    # character_settings：保持和 KnowledgeDAO.create_character 的字段形状一致
    char_doc = {
        "character_id": f"char_bootstrap_{character_name}",
        "name": character_name,
        "personality": {"description": "", "traits": []},
        "background": "",
        "system_prompt": (
            f"你是{character_name}，一个温柔活泼的虚拟助手。\n"
            "重要规则：全程使用中文回复。"
        ),
        "greeting": "你好~",
        "extra": {"nickname": "", "user_name": "用户"},
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    db["character_settings"].update_one({"name": character_name}, {"$setOnInsert": char_doc}, upsert=True)
    # 设为唯一激活
    db["character_settings"].update_many({"name": {"$ne": character_name}}, {"$set": {"is_active": False}})

    return {"user_id": user_id, "character_name": character_name}


def _schema_snapshot() -> dict[str, Any]:
    """
    返回“结构快照”（用于打印/导出），信息来源为当前代码使用点。
    """
    return {
        "mongodb": {
            "collections": {
                "conversations": {
                    "doc_shape": {
                        "session_id": "session_xxx",
                        "user_id": "default_user",
                        "status": "active|closed",
                        "messages": [
                            {"role": "user|assistant|system", "content": "str", "timestamp": "datetime", "emotion?": "str", "extra?": "dict"},
                        ],
                        "summary": "str|null",
                        "metadata": "dict",
                        "created_at": "datetime",
                        "updated_at": "datetime",
                    },
                    "indexes": ["session_id(unique)", "user_id", "status", "created_at"],
                },
                "long_term_memory": {
                    "doc_shape": {
                        "memory_id": "mem_xxx",
                        "user_id": "default_user",
                        "type": "fact|event|preference|emotion|summary",
                        "content": "str",
                        "importance": "float(0..1)",
                        "source": "dict|null（{session_id, message_index}）",
                        "tags": ["str"],
                        "extra": "dict",
                        "access_count": "int",
                        "last_accessed": "datetime|null",
                        "created_at": "datetime",
                        "updated_at": "datetime",
                    },
                    "indexes": ["user_id", "type", "importance", "created_at", "content(text)"],
                },
                "knowledge_base": {
                    "doc_shape": {
                        "knowledge_id": "kb_xxx",
                        "type": "character|world|reference|faq",
                        "title": "str|null",
                        "content": "str",
                        "tags": ["str"],
                        "extra": "dict",
                        "created_at": "datetime",
                        "updated_at": "datetime",
                    },
                    "indexes": ["type", "tags", "content(text)"],
                },
                "character_settings": {
                    "doc_shape": {
                        "character_id": "char_xxx",
                        "name": "str(unique)",
                        "personality": "dict",
                        "background": "str",
                        "system_prompt": "str",
                        "greeting": "str",
                        "extra": {"nickname": "str", "user_name": "str"},
                        "is_active": "bool",
                        "created_at": "datetime",
                        "updated_at": "datetime",
                    },
                    "indexes": ["name(unique)"],
                },
                "user_profiles": {
                    "doc_shape": {
                        "user_id": "str(unique)",
                        "nickname": "str",
                        "preferences": {"call_me": "str", "topics_like": ["str"], "topics_avoid": ["str"]},
                        "stats": {"total_conversations": "int", "total_messages": "int", "first_chat": "datetime"},
                        "created_at": "datetime",
                        "updated_at": "datetime",
                    },
                    "indexes": ["user_id(unique)"],
                },
                "reminders": {
                    "doc_shape": {"reminder_id": "str", "content": "str", "trigger_time": "datetime", "status": "pending|triggered|cancelled", "label": "str"},
                    "indexes": ["trigger_time", "status"],
                },
                "knowledge_graph": {
                    "doc_shape": {"user_id": "str", "triple": {"subject": {"name": "str"}, "relation": {"type": "str"}, "object": {"name": "str"}}, "created_at": "datetime"},
                    "indexes": ["user_id", "uniq_user_triple(user_id, triple.subject.name, triple.relation.type, triple.object.name)"],
                },
            }
        },
        "chromadb": {
            "persist_dir_default": "data/chroma_data",
            "collections": ["knowledge_vectors", "memory_vectors", "conversation_vectors"],
            "note": "ChromaDB 在本项目中以本地持久化目录方式使用（非独立服务）。",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 Liying 数据库结构（不硬编码）")
    parser.add_argument("--mongo-uri", dest="mongo_uri", default=None, help="MongoDB 连接串（或设置环境变量 MONGODB_URI）")
    parser.add_argument("--db", dest="db", default=None, help="MongoDB 数据库名（或设置环境变量 MONGODB_DB）")
    parser.add_argument("--timeout-ms", dest="timeout_ms", default=None, help="连接超时毫秒（或环境变量 MONGODB_TIMEOUT_MS）")
    parser.add_argument("--seed", action="store_true", help="写入最小默认数据（user_profile + 角色设定）")
    parser.add_argument("--user-id", default="default_user", help="seed 时的 user_id")
    parser.add_argument("--character-name", default="玲", help="seed 时的角色名")
    parser.add_argument("--print-schema", action="store_true", help="打印数据库结构快照并退出")
    args = parser.parse_args()

    if args.print_schema:
        print(json.dumps(_schema_snapshot(), ensure_ascii=False, indent=2))
        return 0

    cfg = _get_mongo_config(args)
    print(f"[MongoDB] uri={cfg.uri} db={cfg.db_name}")

    client = None
    try:
        client, db = _connect_mongo(cfg)
        created = _ensure_indexes(db)
        print("[OK] 索引已确保存在：")
        for col, idxs in created.items():
            print(f"  - {col}: {len(idxs)}")

        if args.seed:
            seeded = _seed_minimal_data(db, user_id=args.user_id, character_name=args.character_name)
            print(f"[OK] 已写入最小默认数据：{seeded}")
        else:
            print("[跳过] 未写入默认数据（可加 --seed）")

        return 0
    except Exception as e:
        print(f"[错误] 初始化失败：{e}")
        return 1
    finally:
        try:
            if client is not None:
                client.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

