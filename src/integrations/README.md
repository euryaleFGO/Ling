# 集成模块 (Integrations)

本目录包含玲 (Liying) 项目与外部系统的集成模块。

---

## 📋 可用集成

### 1. 企业微信机器人

#### WebSocket 长连接版本（推荐）⭐

**文件**: `wework_bot_websocket.py`

**特性**:
- ✅ 无需公网 IP
- ✅ 无需域名和 SSL 证书
- ✅ 支持流式消息
- ✅ 支持主动推送
- ✅ 自动心跳和重连
- ✅ 低延迟（10-50ms）
- ✅ 高并发（500+ 用户）

**快速开始**:

```bash
# 1. 配置环境变量（.env）
WEWORK_BOT_ID=your_bot_id
WEWORK_SECRET=your_secret

# 2. 启动机器人
python scripts/start_wework_bot_websocket.py

# 或使用批处理（Windows）
启动企业微信机器人WebSocket.bat
```

**文档**:
- [完整使用指南](../../docs/WEWORK_WEBSOCKET_GUIDE.md)
- [快速开始](../../docs/WEWORK_QUICKSTART.md)
- [对比文档](../../docs/WEWORK_COMPARISON.md)

---

#### Webhook 短连接版本（旧版）

**文件**: `wework_bot.py`

**特性**:
- ⚠️ 需要公网 IP
- ⚠️ 需要域名和 SSL 证书
- ⚠️ 需要处理加解密
- ❌ 不支持流式消息
- ❌ 不支持主动推送

**快速开始**:

```bash
# 1. 配置环境变量（.env）
WEWORK_CORP_ID=your_corp_id
WEWORK_CORP_SECRET=your_corp_secret
WEWORK_AGENT_ID=your_agent_id
WEWORK_WEBHOOK_KEY=your_webhook_key

# 2. 启动机器人
python scripts/start_wework_bot.py

# 或使用批处理（Windows）
启动企业微信机器人.bat
```

**注意**: 推荐使用 WebSocket 长连接版本！

---

### 2. WebSocket 消息服务

**文件**: `websocket_bot.py`

**用途**: Python 后端与 Live2D 前端的 WebSocket 通信

**特性**:
- ✅ 实时消息推送
- ✅ 双向通信
- ✅ 连接管理
- ✅ 心跳保活

**使用**:

```python
from integrations.websocket_bot import WebSocketBot

bot = WebSocketBot(host="localhost", port=8765)
bot.run()
```

---

## 📊 功能对比

| 特性 | WebSocket 长连接 | Webhook 短连接 | WebSocket 消息服务 |
|------|-----------------|---------------|-------------------|
| 公网 IP | ❌ 不需要 | ✅ 必需 | ❌ 不需要 |
| 流式消息 | ✅ 支持 | ❌ 不支持 | ✅ 支持 |
| 主动推送 | ✅ 支持 | ❌ 不支持 | ✅ 支持 |
| 延迟 | 10-50ms | 200-500ms | <10ms |
| 并发 | 500+ | 50 | 100+ |
| 用途 | 企业微信 | 企业微信 | Live2D 通信 |

---

## 🚀 推荐方案

### 企业微信机器人

**推荐**: WebSocket 长连接版本

**理由**:
- 零成本部署（无需公网服务器）
- 功能更强大（流式消息、主动推送）
- 性能更好（10 倍延迟降低）
- 开发更简单（配置简单）

### Live2D 通信

**推荐**: WebSocket 消息服务

**理由**:
- 实时通信
- 低延迟
- 双向推送

---

## 📚 文档

### 企业微信机器人
- [WebSocket 长连接使用指南](../../docs/WEWORK_WEBSOCKET_GUIDE.md)
- [快速开始指南](../../docs/WEWORK_QUICKSTART.md)
- [长连接 vs 短连接对比](../../docs/WEWORK_COMPARISON.md)
- [完成报告](../../docs/WEWORK_WEBSOCKET_COMPLETE.md)

### 项目文档
- [项目 README](../../README.md)
- [快速开始](../../QUICKSTART.md)
- [部署指南](../../DEPLOYMENT.md)

---

## 🔧 开发指南

### 添加新集成

1. 在本目录创建新的 Python 文件
2. 实现集成逻辑
3. 添加配置支持（环境变量或配置文件）
4. 创建启动脚本（`scripts/start_xxx.py`）
5. 编写文档（`docs/XXX_GUIDE.md`）
6. 更新本 README

### 代码规范

- 使用类型注解
- 添加详细的文档字符串
- 实现错误处理和日志
- 支持配置化
- 提供使用示例

---

## 🐛 问题反馈

如有问题，请：

1. 查看相关文档
2. 检查日志输出
3. 提交 Issue
4. 联系开发者

---

**项目**: 玲 (Liying) - 智能虚拟助手  
**更新时间**: 2026-04-27
