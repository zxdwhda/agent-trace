# Root Span 缺失问题排查指南

## 问题描述
在 CozeLoop 仪表盘中，可以看到 All Span 和 Model Span，但看不到 Root Span。

## 参考：OpenClaw 官方实现的关键机制

通过分析 `/Users/zionxaviardamienang/Documents/GitHub/cozeloop-openclaw-trace-source`，发现以下关键实现细节：

### 1. Root Span 的特殊处理
```javascript
// 1. 创建 Root Span（使用 startSpan，不立即结束）
await exporter.startSpan(rootSpanData, ctx.rootSpanId);

// 2. 延迟 100ms 后结束 Root Span
setTimeout(async () => {
    exporter.endSpanById(rootSpanId, endTime, attributes, output, input);
    await exporter.flush();
    exporter.endTrace();
}, 100);
```

### 2. 关键属性设置
```javascript
// cozeloop.span_type 必须设置
attributes: {
    "cozeloop.span_type": "entry",
    "cozeloop.system_tag_runtime": JSON.stringify(runtimeTag),
    // ...
}
```

### 3. Span 类型映射
| span_type | SpanKind | 说明 |
|-----------|----------|------|
| entry | SERVER | 请求入口 |
| gateway | SERVER | 网关 |
| model | CLIENT | 模型调用 |
| tool | CLIENT | 工具调用 |
| agent | INTERNAL | Agent 执行 |

### 4. 上下文管理
- 维护 `currentRootContext` 和 `currentAgentContext`
- Child Span 使用 `currentAgentContext || currentRootContext` 作为 parent

---

## 排查方案

### 排查 1：span_type 设置是否正确

**OpenClaw 代码**：
```javascript
const rootSpanData = {
    name: "openclaw_request",
    type: "entry",  // <-- 关键
    // ...
};
```

**我们的代码** (`session_state.py:263-266`)：
```python
self.entry_span = cozeloop.start_span(
    "session_entry",
    self.SPAN_TYPE_ENTRY  # "entry"
)
```

**状态**: ✅ 正确设置了 "entry" 类型

**可能问题**: 
- OpenClaw 使用 `cozeloop.span_type` attribute，而不是 start_span 的 span_type 参数
- 需要检查 Python SDK 是否会自动转换

---

### 排查 2：父子关系是否正确建立

**OpenClaw 代码**：
```javascript
// Root Span 没有 parentSpanId（isRoot = true）
const isRoot = !spanData.parentSpanId;

// Agent Span 的 parent 是 Root
const isAgent = spanData.type === "agent";
parentContext = this.currentRootContext || context.active();

// Model/Tool Span 的 parent 是 Agent
parentContext = this.currentAgentContext || this.currentRootContext || context.active();
```

**我们的代码** (`session_state.py:275-279`)：
```python
# Entry Span 没有 child_of（应该是 Root）
self.entry_span = cozeloop.start_span(
    "session_entry",
    self.SPAN_TYPE_ENTRY
)

# Agent Span 的 child_of 是 entry_span
self.root_span = cozeloop.start_span(
    "agent_turn",
    self.SPAN_TYPE_AGENT,
    child_of=self.entry_span,
)
```

**状态**: ⚠️ **可能有问题**

**问题分析**:
- 我们创建了 Entry Span 作为 Root，然后 Agent Span 作为其子节点
- 但 OpenClaw 直接创建 Root Span 作为 entry 类型，然后 agent 类型作为其子节点
- 可能 CozeLoop 认为 "entry" 类型的 span 不应该有子节点？或者需要特定的处理方式？

**建议测试**:
1. 直接将 Agent Span 作为 Root（不创建 Entry Span）
2. 或者检查 Entry Span 是否需要设置 `start_new_trace=True`

---

### 排查 3：Root Span 是否正确 finish

**OpenClaw 代码**：
```javascript
// 1. 延迟结束
setTimeout(async () => {
    exporter.endSpanById(rootSpanId, endTime, attrs, output, input);
    await exporter.flush();  // <-- 强制刷新
    exporter.endTrace();
}, 100);
```

**我们的代码** (`session_state.py:680-683`)：
```python
# 结束 entry span
if self.entry_span:
    self.entry_span.finish()
    self.entry_span = None
```

**状态**: ⚠️ **可能有问题**

**问题分析**:
- 我们直接调用 `finish()`，没有延迟
- 我们没有调用 `flush()` 强制刷新队列
- Span 可能还在 SDK 的队列中，没有被发送到 CozeLoop

**建议测试**:
```python
import cozeloop

# 在 end_turn 最后添加
if self.entry_span:
    self.entry_span.finish()
    # 添加 flush
    cozeloop.flush()  # 或 client.flush()
    self.entry_span = None
```

---

### 排查 4：Span 是否在队列中丢失

**问题**: Span 被创建并 `finish()` 后，放入异步队列。如果程序提前退出或队列满，Span 可能丢失。

**OpenClaw 处理**:
- 调用 `flush()` 强制刷新
- 使用 `endTrace()` 清理上下文

**我们的代码**: 缺少 flush 机制

**建议**: 在关键位置添加 flush

---

### 排查 5：是否需要等待后台处理

**OpenClaw 文档说明**:
> "扣子罗盘的 Trace 数据采用逐步上报机制：已完成的节点会先上报，根节点（Root Span）最后上报。"

**问题**:
- Root Span 确实会最后上报
- 但如果我们在 Root Span finish 后立即查看，可能还需要等待几秒

**建议**:
1. 在 turn 结束后等待 5-10 秒再查看 CozeLoop
2. 或者添加 flush 机制

---

## 修复方案

### 方案 1：添加 flush 机制（推荐先尝试）

```python
# session_state.py end_turn 方法

def end_turn(self, timestamp: float):
    # ... 现有代码 ...
    
    # 结束 entry span
    if self.entry_span:
        self.entry_span.finish()
        # 强制刷新队列
        try:
            import cozeloop
            # 尝试获取 client 并 flush
            client = cozeloop.get_client()  # 或类似的获取方式
            if client:
                client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush cozeloop: {e}")
        self.entry_span = None
    
    # ...
```

### 方案 2：简化层级结构（如果不支持 Entry Span）

```python
# 直接将 Agent Span 作为 Root（无 Entry Span）
self.root_span = cozeloop.start_span(
    "agent_turn",
    self.SPAN_TYPE_ENTRY,  # 使用 "entry" 类型
)
```

### 方案 3：延迟结束 Root Span（模仿 OpenClaw）

```python
import threading

def end_turn(self, timestamp: float):
    # ... 结束其他 span ...
    
    # 延迟结束 Root Span
    def delayed_finish():
        time.sleep(0.1)  # 100ms 延迟
        if self.entry_span:
            self.entry_span.finish()
            try:
                import cozeloop
                client = cozeloop.get_client()
                if client:
                    client.flush()
            except:
                pass
    
    threading.Timer(0.1, delayed_finish).start()
```

---

## 验证步骤

1. **查看日志确认 Root Span 创建**
   ```bash
   tail -f /tmp/agent-trace.log | grep -E "(Entry|Root|entry|turn)"
   ```

2. **确认 finish 被调用**
   ```bash
   tail -f /tmp/agent-trace.log | grep -E "(finish|end_turn)"
   ```

3. **等待 10 秒后查看 CozeLoop**
   - 切换到 "All Span" 视图
   - 检查 Root Span 是否出现

4. **如果仍未出现，尝试添加 flush 后重测**

---

## 相关代码位置

| 功能 | 文件位置 | 行号 |
|------|---------|------|
| Entry Span 创建 | session_state.py | 263-272 |
| Agent Span 创建 | session_state.py | 275-296 |
| Entry Span 结束 | session_state.py | 680-683 |
| Root Span 结束 | session_state.py | 666-678 |

## 参考文档

- OpenClaw 实现：`/Users/zionxaviardamienang/Documents/GitHub/cozeloop-openclaw-trace-source/dist/index.js`
- OpenClaw Exporter：`/Users/zionxaviardamienang/Documents/GitHub/cozeloop-openclaw-trace-source/dist/cozeloop-exporter.js`
