# Task 2.2 实现总结：错误处理和降级策略

## 实现内容

已成功实现 DiarizationEngine 的错误处理和降级策略，满足需求 8.1-8.6。

### 1. 连续失败计数机制（需求 8.1）

**实现**：
- 添加 `_consecutive_failures` 计数器
- 添加 `_max_failures` 阈值（默认 3）
- 识别成功时重置计数器
- 识别失败时递增计数器

**代码位置**：`src/core/diarization_engine.py:103-107`

### 2. 临时禁用机制（需求 8.6）

**实现**：
- 添加 `_temporarily_disabled` 标志
- 当连续失败达到阈值时，设置为 True
- 禁用后直接返回上一次结果，不再尝试识别
- 提供 `reset_failure_counter()` 方法手动恢复

**代码位置**：`src/core/diarization_engine.py:107, 127-136, 217-221`

### 3. 超时控制（需求 8.4）

**实现**：
- 使用 `concurrent.futures.ThreadPoolExecutor` 实现超时控制
- 默认超时时间 500ms（可配置）
- 超时后取消识别，返回上一次结果
- 记录超时日志和失败次数

**代码位置**：`src/core/diarization_engine.py:149-169`

### 4. 降级到上一次识别结果（需求 8.2）

**实现**：
- 维护 `_last_speaker_id` 记录上一次成功识别的说话人
- 所有错误情况（超时、异常、临时禁用）都返回上一次结果
- 确保对话不中断

**代码位置**：`src/core/diarization_engine.py:101, 171-189`

### 5. 错误日志记录（需求 8.5）

**实现**：
- 使用 Python logging 模块记录所有错误
- 日志级别：
  - DEBUG: 正常识别、音频过短
  - WARNING: 超时
  - ERROR: 异常、临时禁用
- 日志包含详细信息：错误类型、失败次数、耗时等

**代码位置**：`src/core/diarization_engine.py:127, 166, 178, 282`

### 6. 用户通知机制（需求 8.6）

**实现**：
- 添加 `_user_notification_callback` 回调函数
- 提供 `set_notification_callback()` 方法设置回调
- 临时禁用时调用回调通知用户
- 回调失败不影响主流程

**代码位置**：`src/core/diarization_engine.py:108, 209-214, 276-286`

## 测试覆盖

创建了完整的单元测试套件 `tests/test_diarization_error_handling.py`，包含 9 个测试用例：

1. ✅ `test_consecutive_failure_counter` - 测试连续失败计数器
2. ✅ `test_fallback_to_last_speaker_on_error` - 测试降级到上一次结果
3. ✅ `test_database_access_failure` - 测试数据库访问失败
4. ✅ `test_timeout_control` - 测试超时控制
5. ✅ `test_error_logging` - 测试错误日志记录
6. ✅ `test_temporary_disable_after_max_failures` - 测试临时禁用
7. ✅ `test_reset_failure_counter` - 测试重置失败计数器
8. ✅ `test_short_audio_skips_identification` - 测试音频过短跳过识别
9. ✅ `test_successful_identification_resets_counter` - 测试成功识别重置计数器

**测试结果**：9 passed in 0.30s ✅

## 新增 API

### 公共方法

1. **`set_notification_callback(callback: callable)`**
   - 设置用户通知回调函数
   - 用于在临时禁用时通知用户

2. **`reset_failure_counter()`**
   - 重置失败计数器
   - 恢复识别功能
   - 用于手动恢复

3. **`is_temporarily_disabled() -> bool`**
   - 检查是否临时禁用
   - 用于外部状态查询

### 构造函数新增参数

- `timeout_ms: int = 500` - 识别超时时间（毫秒）
- `max_failures: int = 3` - 最大连续失败次数

## 需求映射

| 需求 | 实现内容 | 状态 |
|------|---------|------|
| 8.1 | 连续失败计数和重置机制 | ✅ 完成 |
| 8.2 | 降级到上一次识别结果 | ✅ 完成 |
| 8.3 | 数据库访问失败处理 | ✅ 完成 |
| 8.4 | 识别超时控制（500ms） | ✅ 完成 |
| 8.5 | 错误日志记录 | ✅ 完成 |
| 8.6 | 连续失败临时禁用和通知 | ✅ 完成 |

## 使用示例

```python
from src.core.diarization_engine import DiarizationEngine
from src.core.sv_engine import SVEngine

# 创建引擎
sv_engine = SVEngine()
voiceprint_db = VoiceprintDatabase(storage_path)

engine = DiarizationEngine(
    sv_engine=sv_engine,
    voiceprint_db=voiceprint_db,
    threshold=0.75,
    min_audio_sec=0.8,
    timeout_ms=500,  # 超时时间
    max_failures=3   # 最大失败次数
)

# 设置通知回调
def on_error_notification(message):
    print(f"[通知] {message}")

engine.set_notification_callback(on_error_notification)

# 识别说话人
result = engine.identify(audio, sample_rate=16000)

# 检查状态
if engine.is_temporarily_disabled():
    print("识别功能已临时禁用")
    # 手动恢复
    engine.reset_failure_counter()
```

## 日志示例

```
[2025-03-16 10:30:15] DEBUG [说话人识别] 成功: speaker_id=speaker_001, score=0.87, 耗时=145ms
[2025-03-16 10:30:20] WARNING [说话人识别] 超时 (520ms > 500ms)，使用上一次结果 (失败次数: 1/3)
[2025-03-16 10:30:25] ERROR [说话人识别] 失败: ValueError: Invalid audio (失败次数: 2/3)
[2025-03-16 10:30:30] ERROR [说话人识别] 说话人识别连续失败 3 次，已临时禁用。系统已切换到单用户模式。
```

## 向后兼容性

- 所有新增参数都有默认值，不影响现有代码
- 错误处理是透明的，不改变正常识别流程
- 降级策略确保对话不中断

## 性能影响

- 超时控制使用线程池，开销极小（<1ms）
- 缓存机制减少重复计算
- 临时禁用后避免无效尝试，提高性能
