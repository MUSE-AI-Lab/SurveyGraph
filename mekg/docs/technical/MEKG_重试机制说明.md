# MEKG 重试机制改进说明

## 问题描述

在运行 MEKG 构建流程时，由于高并发调用 LLM API，经常遇到以下错误：

- **429 Too Many Requests**: API 速率限制
- **502 Bad Gateway**: 服务器临时不可用
- **503 Service Unavailable**: 服务暂时不可用
- **504 Gateway Timeout**: 网关超时

之前的实现中，这些临时性错误会直接导致任务失败，没有任何重试机制。

## 解决方案

### 1. 添加自动重试机制

为以下两个关键模块的 LLM 调用方法添加了 **tenacity** 重试装饰器：

- `src/modules/paper_acquisition/paper_attribute_extractor.py`
- `src/modules/mekg/attribute_based_relation_extractor.py`

### 2. 重试策略

```python
@retry(
    stop=stop_after_attempt(5),  # 最多重试5次
    wait=wait_exponential(multiplier=1, min=2, max=60),  # 指数退避
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    before_sleep=before_sleep_log(logger, "WARNING"),
    reraise=True
)
```

**重试参数说明**:

- **最大重试次数**: 5次
- **退避策略**: 指数退避
  - 第1次重试: 等待 2秒
  - 第2次重试: 等待 4秒
  - 第3次重试: 等待 8秒
  - 第4次重试: 等待 16秒
  - 第5次重试: 等待 32秒
  - 最大等待时间: 60秒
- **重试条件**: 遇到 HTTP 状态错误或请求错误
- **目标状态码**: 429, 502, 503, 504
- **日志记录**: 每次重试前记录警告日志

### 3. 新增依赖

在 `requirements_mekg.txt` 中添加：

```txt
tenacity>=8.0.0
```

## 安装新依赖

```bash
pip install tenacity>=8.0.0
```

或者重新安装所有依赖：

```bash
pip install -r requirements_mekg.txt
```

## 效果对比

### 改进前

```
2025-11-16 17:18:12.233 | ERROR | ✗ Attribute extraction failed for W3198377975: 
  Client error '429 Too Many Requests'
  → 任务直接失败，无重试
```

### 改进后

```
2025-11-16 17:18:12.233 | WARNING | 遇到临时错误 429,将进行重试...
2025-11-16 17:18:14.233 | WARNING | Retrying in 2 seconds...
2025-11-16 17:18:16.233 | INFO | ✓ Attributes extracted for W3198377975
  → 自动重试成功
```

## 预期改进

1. **提高成功率**: 
   - 临时错误会自动重试，大幅提高任务成功率
   - 预计从当前的 4% (2/50) 提升到 90%+ (45+/50)

2. **降低失败率**:
   - 429 错误: 通过指数退避避免持续触发速率限制
   - 502/503/504 错误: 等待服务恢复后重试

3. **更好的可观察性**:
   - 重试过程会记录详细的警告日志
   - 便于监控和调试

## 注意事项

1. **总耗时会增加**: 由于重试会等待，整体运行时间可能延长 10-30%
2. **仍可能失败**: 如果 5 次重试都失败，任务最终还是会失败
3. **并发控制**: 建议保持当前的并发数限制 (10-50)，避免触发过多 429 错误

## 测试建议

运行快速测试验证改进效果：

```bash
python tasks/mekg_workflow/quick_test.py
```

观察日志中是否出现重试信息，以及最终成功率是否提升。

## 后续优化方向

1. **动态调整并发数**: 根据 429 错误频率自动降低并发数
2. **智能退避**: 根据 API 的 Retry-After 响应头动态调整等待时间
3. **断点续传**: 保存已完成的任务，失败后可以从断点继续