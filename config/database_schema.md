# Liying 数据库 Schema 定义
# 使用方法: 使用 MongoDB 客户端导入或参考此文件创建集合

## 数据库名称: liying_db

---

## 集合 1: conversations（对话记录）

```javascript
{
  "session_id": "session_xxxxxxxxxxxx",  // 会话ID，唯一索引
  "user_id": "default_user",             // 用户ID
  "status": "active",                    // 状态: active | closed
  "messages": [                          // 消息数组
    {
      "role": "user",                   // 角色: user | assistant | system
      "content": "消息内容",
      "timestamp": ISODate("2024-01-01T00:00:00.000Z"),
      "emotion": "happy",               // 可选，情感标签
      "extra": {}                       // 可选，额外信息
    }
  ],
  "summary": "对话摘要",                 // 可选，会话摘要
  "metadata": {},                        // 可选，元数据
  "created_at": ISODate("2024-01-01T00:00:00.000Z"),
  "updated_at": ISODate("2024-01-01T00:00:00.000Z")
}
```

### 索引
- `session_id`: 唯一索引
- `user_id`: 普通索引
- `status`: 普通索引
- `created_at`: 普通索引

---

## 集合 2: long_term_memory（长期记忆）

```javascript
{
  "memory_id": "mem_xxxxxxxxxxxx",       // 记忆ID
  "user_id": "default_user",             // 用户ID
  "type": "fact",                        // 记忆类型: fact | event | preference | emotion | summary
  "content": "用户喜欢编程",              // 记忆内容
  "importance": 0.8,                     // 重要程度 0.0-1.0
  "source": {                            // 可选，来源信息
    "session_id": "session_xxx",
    "message_index": 5
  },
  "tags": ["编程", "爱好"],              // 标签数组
  "extra": {},                           // 额外信息
  "access_count": 0,                     // 访问次数
  "last_accessed": ISODate("2024-01-01T00:00:00.000Z"),  // 最后访问时间
  "created_at": ISODate("2024-01-01T00:00:00.000Z"),
  "updated_at": ISODate("2024-01-01T00:00:00.000Z")
}
```

### 索引
- `user_id`: 普通索引
- `type`: 普通索引
- `importance`: 普通索引
- `created_at`: 普通索引
- `content`: 文本索引 (text index)

---

## 集合 3: character_settings（角色设定）

```javascript
{
  "character_id": "char_xxxxxxxx",       // 角色ID
  "name": "玲",                           // 角色名称，唯一索引
  "personality": {                       // 性格特征
    "description": "温柔可爱",
    "traits": ["活泼", "善良"]
  },
  "background": "背景故事",              // 背景故事
  "system_prompt": "你是玲...",          // 系统提示词
  "greeting": "你好呀~",                 // 打招呼语
  "extra": {                             // 额外信息
    "nickname": "小玲",
    "user_name": "用户"
  },
  "is_active": true,                     // 是否激活
  "created_at": ISODate("2024-01-01T00:00:00.000Z"),
  "updated_at": ISODate("2024-01-01T00:00:00.000Z")
}
```

### 索引
- `name`: 唯一索引

---

## 集合 4: user_profiles（用户档案）

```javascript
{
  "user_id": "default_user",            // 用户ID，唯一索引
  "nickname": "用户",                     // 昵称（角色如何称呼用户）
  "preferences": {                       // 偏好设置
    "call_me": "用户",
    "topics_like": [],
    "topics_avoid": []
  },
  "stats": {                             // 统计信息
    "total_conversations": 0,
    "total_messages": 0,
    "first_chat": ISODate("2024-01-01T00:00:00.000Z")
  },
  "created_at": ISODate("2024-01-01T00:00:00.000Z"),
  "updated_at": ISODate("2024-01-01T00:00:00.000Z")
}
```

### 索引
- `user_id`: 唯一索引

---

## 集合 5: knowledge_base（知识库）

```javascript
{
  "knowledge_id": "kb_xxxxxxxxxxxx",     // 知识ID
  "type": "character",                   // 知识类型: character | world | reference | faq
  "title": "知识标题",                    // 可选，标题
  "content": "知识内容...",               // 知识正文
  "tags": ["标签1", "标签2"],            // 标签数组
  "extra": {},                           // 额外信息
  "created_at": ISODate("2024-01-01T00:00:00.000Z"),
  "updated_at": ISODate("2024-01-01T00:00:00.000Z")
}
```

### 索引
- `type`: 普通索引
- `tags`: 普通索引
- `content`: 文本索引 (text index)

---

## 一键导入脚本 (MongoDB Shell)

```javascript
// 切换到 liying_db
use liying_db;

// 创建 conversations 集合索引
db.conversations.createIndex({ "session_id": 1 }, { unique: true });
db.conversations.createIndex({ "user_id": 1 });
db.conversations.createIndex({ "status": 1 });
db.conversations.createIndex({ "created_at": 1 });

// 创建 long_term_memory 集合索引
db.long_term_memory.createIndex({ "user_id": 1 });
db.long_term_memory.createIndex({ "type": 1 });
db.long_term_memory.createIndex({ "importance": 1 });
db.long_term_memory.createIndex({ "created_at": 1 });
db.long_term_memory.createIndex({ "content": "text" });

// 创建 character_settings 集合索引
db.character_settings.createIndex({ "name": 1 }, { unique: true });

// 创建 user_profiles 集合索引
db.user_profiles.createIndex({ "user_id": 1 }, { unique: true });

// 创建 knowledge_base 集合索引
db.knowledge_base.createIndex({ "type": 1 });
db.knowledge_base.createIndex({ "tags": 1 });
db.knowledge_base.createIndex({ "content": "text" });
```

## 一键导入脚本 (mongosh)

```javascript
// 保存为 setup_database.js 然后运行: mongosh < setup_database.js
use liying_db;

// conversations
db.conversations.createIndex({ "session_id": 1 }, { unique: true });
db.conversations.createIndex({ "user_id": 1 });
db.conversations.createIndex({ "status": 1 });
db.conversations.createIndex({ "created_at": 1 });

// long_term_memory
db.long_term_memory.createIndex({ "user_id": 1 });
db.long_term_memory.createIndex({ "type": 1 });
db.long_term_memory.createIndex({ "importance": 1 });
db.long_term_memory.createIndex({ "created_at": 1 });
db.long_term_memory.createIndex({ "content": "text" });

// character_settings
db.character_settings.createIndex({ "name": 1 }, { unique: true });

// user_profiles
db.user_profiles.createIndex({ "user_id": 1 }, { unique: true });

// knowledge_base
db.knowledge_base.createIndex({ "type": 1 });
db.knowledge_base.createIndex({ "tags": 1 });
db.knowledge_base.createIndex({ "content": "text" });

print("数据库初始化完成！");
```
