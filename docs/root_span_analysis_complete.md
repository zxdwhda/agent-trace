# Root Span 缺失问题 - 完整分析报告

## 一、背景信息

### 1.1 参考实现对比

| 项目 | 技术栈 | Root Span 处理方式 |
|------|--------|-------------------|
| **OpenClaw 官方** | Node.js + OpenTelemetry | 延迟 100ms 结束 + flush() |
| **Kimi Code CLI** | Python (Wire 协议) | 无内置 trace，只有 wire.jsonl |
| **AgentTrace (我们)** | Python + CozeLoop SDK | 直接 finish()，无 flush |

### 1.2 Kimi Code CLI Wire 协议关键信息

从搜索到的 [Wire 协议文档](https://zhichai.net/htmlpages/topic_176922862.html) 了解到：

**事件类型**:
- `TurnBegin` - 轮次开始（对应我们的 Root Span 开始）
- `TurnEnd` - 轮次结束（v1.2+，对应 Root Span 结束）
- `StepBegin` - 步骤开始（对应 Model Span）
- `ToolCall` / `ToolResult` - 工具调用

**关键发现**:
- Kimi CLI 本身**不输出 trace 数据**，只输出 wire.jsonl 事件
- 我们需要将 wire.jsonl 转换为 CozeLoop Trace
- `TurnEnd` 事件在 v1.2+ 才添加，表示轮次真正结束

---

## 二、五个可能原因的深度分析

### 原因 1：span_type 设置不正确

**OpenClaw 做法**:
```javascript
// 通过 attribute 设置
attributes: {
    "cozeloop.span_type": "entry",
    "cozeloop.system_tag_runtime": JSON.stringify(runtimeTag),
}
```

**我们的做法**:
```python
# 通过 start_span 参数设置
self.entry_span = cozeloop.start_span(
    "session_entry",
    self.SPAN_TYPE_ENTRY  # "entry"
)
```

**分析**:
- ✅ Python SDK 的 `start_span` 第二个参数就是 span_type
- ✅ 应该会被正确转换
- ⚠️ 但 OpenClaw 同时设置了 `cozeloop.system_tag_runtime`，我们没有

**影响程度**: 低

---

### 原因 2：父子关系未正确建立

**OpenClaw 层级**:
```
openclaw_request (entry, Root Span, 无 parent)
└── agent (agent, child_of=Root)
    ├── model_provider/model_name (model, child_of=agent)
    ├── read (tool, child_of=agent)
    └── write (tool, child_of=agent)
```

**我们的层级**:
```
session_entry (entry, Root Span, 无 parent)  ← 问题！
└── agent_turn (agent, child_of=entry)
    ├── prompt_1 (prompt, child_of=agent)
    └── step_1 (model, child_of=agent)
        └── tool:name (tool, child_of=step)
```

**关键差异**:
- OpenClaw 的 **Root Span 是 entry 类型**
- 我们的 **Root Span 也是 entry 类型**，但多了一层 Agent

**可能问题**:
- CozeLoop 可能期望 Root Span 是某个特定类型（如 "custom" 或 "agent"）
- entry 类型可能被认为不应该有子节点

**验证建议**:
```python
# 尝试将 Agent Span 作为 Root
self.root_span = cozeloop.start_span(
    "agent_turn",
    "entry",  # 或 "custom"
)
# 不再创建单独的 entry_span
```

**影响程度**: 中

---

### 原因 3：Root Span 未正确 finish（关键）

**OpenClaw 关键代码** (`index.js:553-573`):
```javascript
// 1. Root Span 开始（使用 startSpan，记录 startTime）
await exporter.startSpan(rootSpanData, ctx.rootSpanId);

// 2. 延迟 100ms 后结束（确保所有子节点先上报）
setTimeout(async () => {
    // 使用 endSpanById 结束，传入完整数据
    exporter.endSpanById(rootSpanId, endTime, attrs, finalOutput, userInput);
    // 强制刷新队列
    await exporter.flush();
    // 清理上下文
    exporter.endTrace();
}, 100);
```

**我们的代码** (`session_state.py:680-683`):
```python
# 结束 entry span
if self.entry_span:
    self.entry_span.finish()
    self.entry_span = None
# ❌ 没有 flush
# ❌ 没有延迟
```

**关键差异**:

| 特性 | OpenClaw | 我们 |
|------|----------|------|
| 结束方式 | `endSpanById()` + 延迟 | `finish()` 立即 |
| 队列刷新 | `await flush()` | ❌ 无 |
| 输入输出 | 结束时才设置 | 创建时就设置 |
| 延迟时间 | 100ms | 0ms |

**为什么延迟很重要**:
1. CozeLoop 采用**逐步上报**机制
2. 子 Span（Model、Tool）先完成，先上报
3. Root Span 最后上报，作为"汇总"
4. 如果 Root Span 太早结束，可能**还没等到子 Span 上报完成**

**影响程度**: **高** ⭐⭐⭐

---

### 原因 4：Span 在队列中丢失（关键）

**OpenTelemetry BatchSpanProcessor 行为**:
- Span 调用 `finish()` / `end()` 后，进入队列
- 队列满或达到 `scheduledDelayMillis` 时才批量上报
- 如果程序退出前没有 `flush()`，队列中的 Span 可能丢失

**OpenClaw 保障机制**:
```javascript
// 1. 正常流程
await exporter.flush();

// 2. 程序退出时
api.on("gateway_stop", async () => {
    await exporter.dispose();  // 包含 flush
});
```

**我们的保障**:
```python
# 只有 finish，没有 flush
self.entry_span.finish()
```

**问题场景**:
1. Entry Span finish 后立即查看 CozeLoop
2. 此时 Span 还在 SDK 队列中，未发送到服务器
3. 看起来就像"没有 Root Span"

**影响程度**: **高** ⭐⭐⭐

---

### 原因 5：需要等待后台处理

**官方文档说明**:
> "扣子罗盘的 Trace 数据采用逐步上报机制：已完成的节点会先上报，根节点（Root Span）最后上报。"

**正常时序**:
```
t=0:   Model Span 完成 -> 上报
       Tool Span 完成 -> 上报
t=50:  Agent Span 完成 -> 上报
t=100: Root Span 完成 -> 上报（汇总）
t=150: 全部显示在 CozeLoop 仪表盘
```

**我们的时序**:
```
t=0:   Entry Span 创建
       Entry Span finish() -> 入队
       Model Span 创建
       Model Span finish() -> 入队
       ...
t=5:   用户查看 CozeLoop（缺少 Root Span）
t=500: 队列批量上报（可能包含 Root Span）
```

**关键问题**:
- 我们没有 `flush()`，队列等待时间可能长达 5 秒（默认配置）
- 如果用户在 5 秒内查看，Root Span 可能还未上报

**影响程度**: 中

---

## 三、Wire 协议与 Trace 的映射关系

基于 Kimi Code CLI 的 [Wire 协议文档](https://zhichai.net/htmlpages/topic_176922862.html)，正确的映射应该是：

```
Wire 事件                Trace Span
─────────────────────────────────────────
TurnBegin          →    entry (Root Span) 开始
StepBegin          →    model (Model Span) 开始
ToolCall           →    tool (Tool Span) 开始
ToolResult         →    tool (Tool Span) 结束
StepEnd            →    model (Model Span) 结束
TurnEnd            →    entry (Root Span) 结束  ← 关键！
```

**我们的问题**:
- 可能 TurnEnd 事件没有被正确处理
- 或者 TurnEnd 到达时，我们已经提前结束了 Root Span

---

## 四、修复方案（按优先级排序）

### 方案 1：添加 flush 调用（最高优先级）

```python
# session_state.py end_turn 方法修改

def end_turn(self, timestamp: float):
    # ... 结束其他 span ...
    
    # 结束 root span
    if self.root_span:
        self.root_span.finish()
        self.root_span = None
    
    # 结束 entry span 并刷新
    if self.entry_span:
        self.entry_span.finish()
        # 强制刷新队列（关键！）
        try:
            import cozeloop
            cozeloop.flush()
        except Exception as e:
            logger.warning(f"Failed to flush: {e}")
        self.entry_span = None
```

### 方案 2：延迟结束 Root Span（模仿 OpenClaw）

```python
import threading

def end_turn(self, timestamp: float):
    # ... 结束其他 span ...
    
    # 延迟结束 Root Span
    def delayed_finish():
        time.sleep(0.1)  # 100ms 延迟
        
        if self.root_span:
            self.root_span.finish()
            self.root_span = None
        
        if self.entry_span:
            self.entry_span.finish()
            try:
                import cozeloop
                cozeloop.flush()
            except:
                pass
            self.entry_span = None
    
    threading.Timer(0.1, delayed_finish).start()
```

### 方案 3：简化层级结构（如果 entry 类型不被支持）

```python
def start_turn(self, timestamp: float, user_input: str):
    # ...
    
    # 直接将 Agent Span 作为 Root，使用 "entry" 类型
    self.root_span = cozeloop.start_span(
        "agent_turn",
        "entry",  # 作为 Root Span 类型
    )
    
    # 不再创建单独的 entry_span
    # self.entry_span = ...  # 删除
```

### 方案 4：在 TurnEnd 事件时结束 Root Span

检查我们是否正确处理了 TurnEnd 事件：

```python
# event_handler.py

class TurnEndHandler(EventHandler):
    def handle(self, event: Dict[str, Any], state: SessionState):
        # 确保 TurnEnd 时才结束 Root Span
        state.end_turn(event.get("timestamp", time.time()))
```

---

## 五、验证步骤

1. **确认 TurnEnd 事件到达**
   ```bash
   tail -f /tmp/agent-trace.log | grep -i "turn.*end"
   ```

2. **检查 span_type 设置**
   ```bash
   # 在代码中添加调试日志
   logger.info(f"Entry span type: {self.SPAN_TYPE_ENTRY}")
   ```

3. **测试 flush 效果**
   - 修改代码添加 `cozeloop.flush()`
   - 重新启动服务
   - 发起一个对话
   - 等待 10 秒后查看 CozeLoop

4. **对比测试**
   - 测试 A：直接 finish，无 flush
   - 测试 B：finish + flush
   - 测试 C：延迟 100ms + finish + flush

---

## 六、推荐修复顺序

1. **第一步**：添加 `cozeloop.flush()`（最简单，最可能解决问题）
2. **第二步**：如果无效，尝试延迟 100ms 结束 Root Span
3. **第三步**：如果仍无效，检查 span_type 是否需要改为 "custom"
4. **第四步**：简化层级，直接用 Agent Span 作为 Root

---

## 七、相关代码位置

| 功能 | 文件 | 行号 |
|------|------|------|
| Entry Span 创建 | session_state.py | 263-272 |
| Agent Span 创建 | session_state.py | 275-296 |
| Root Span 结束 | session_state.py | 666-678 |
| Entry Span 结束 | session_state.py | 680-683 |
| TurnEnd 处理 | event_handler.py | 待确认 |
| flush 调用 | 无 | 需要添加 |

---

## 八、参考文档

1. [OpenClaw CozeLoop Trace 实现](file:///Users/zionxaviardamienang/Documents/GitHub/cozeloop-openclaw-trace-source/dist/index.js)
2. [Kimi Code CLI Wire 协议](https://zhichai.net/htmlpages/topic_176922862.html)
3. [CozeLoop Python SDK](file:///Users/zionxaviardamienang/Documents/GitHub/cozeloop-python-main/cozeloop/_client.py:519)
4. [OpenClaw Trace 上报官方文档](https://www.coze.cn/open/docs/cozeloop/openclaw_trace_report)

---

**分析完成时间**: 2026-03-18
**结论**: 最可能的原因是缺少 `flush()` 调用和延迟结束机制
