# Changelog

所有版本的变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [0.3.5] - 2026-03-18

### 🐛 关键修复 - Root Span 问题

**问题描述**: 
- 上报内容只有 All Span、Model Span，没有 Root Span
- All Span 运行轨迹混乱，层级关系不正确

**根本原因**:
- SDK 全局函数 `cozeloop.start_span()` 不支持 `start_new_trace` 参数
- Entry Span 创建时未正确设置 `parent_span_id="0"`，导致不被识别为 Root Span
- 延迟时间 100ms 可能不足以确保所有子 Span 先上报

**修复内容**:
1. **使用 Client 实例调用**: 所有 `cozeloop.start_span()` 改为 `client.start_span()`，以支持 `start_new_trace` 参数
2. **强制开启新 Trace**: Entry Span 创建时添加 `start_new_trace=True`，确保 `parent_span_id="0"`
3. **增加延迟时间**: 延迟结束时间从 100ms 增加到 500ms，确保所有子 Span 先上报完成

**技术细节**:
```python
# 修复前 - 不支持 start_new_trace
cozeloop.start_span("session_entry", "entry")

# 修复后 - 使用 client 实例
from cozeloop._client import get_default_client
client = get_default_client()
client.start_span("session_entry", "entry", start_new_trace=True)
```

**验证结果**:
- ✅ Root Span 正确创建：日志显示 `Entry span (Root) finished (delayed)`
- ✅ 层级结构正确：`session_entry` → `agent_turn` → `step_N` → `tool:N`
- ✅ 队列刷新正常：`CozeLoop queue flushed`
- ✅ TraceContext 管理正确：`TraceContext ended (delayed)`

**修改文件**:
- `src/agent_trace/core/session_state.py` - 所有 start_span 调用改为 client 实例方式
- `src/agent_trace/core/monitor.py` - Gateway Span 同样改为 client 实例方式
- `~/.agenttrace/start.sh` - 补充 `KIMI_SESSIONS_DIR` 环境变量

---

## [0.3.4] - 2026-03-18

### 🎯 核心优化 - 对标 OpenClaw 官方实现

参考扣子官方 [OpenClaw CozeLoop Trace 插件](https://www.coze.cn/docs/developer_guides/openclaw_cozeloop_trace) 架构，对核心追踪逻辑进行深度重构，实现与官方 OpenClaw 同等级别的 Trace 上报能力。

**设计对齐**:
- 遵循 OpenClaw 的 Span 层级结构: `entry` → `agent` → `model` → `tool`
- 支持 OpenTelemetry 标准属性 (`gen_ai.*`)
- 实现类似的 TraceContext 管理机制 (`trace_id`, `run_id`, `turn_id`)
- 提供 Runtime 信息自动检测
- 新增 Gateway Span 服务级监控

**应用价值**:
- 利用 CozeLoop 分析与可视化能力，深入洞察 Kimi CLI 的使用成本、性能与行为
- 支持 Token 消耗统计、模型性能分析、工具调用链路追踪
- 逐步上报机制：已完成的节点先上报，实时跟进请求执行情况

#### 1. TraceContext 管理机制（新增）

借鉴 OpenClaw 的上下文管理设计，新增完整的 TraceContext 体系，实现跨系统 Trace 关联：

- **全局唯一追踪 ID**: 32 位十六进制 `trace_id`，支持跨系统关联
- **运行实例标识**: `run_id` + `turn_id` 明确单次执行边界
- **双向索引**: 支持通过 `session_id` 或 `run_id` 快速查找上下文
- **Span 栈管理**: 支持并发场景下的 Span 层级追踪
- **Hook 状态追踪**: 记录已处理的 Hook，防止重复处理

**新增文件**:
- `src/agent_trace/core/trace_context.py` - TraceContext 和 TraceContextManager 实现

#### 2. Span 类型体系补充

补充 6 种 Span 类型，完整对标 OpenClaw 的数据结构：

| 类型 | 用途 | 使用位置 | OpenClaw 对应 |
|------|------|----------|---------------|
| `entry` | 请求入口，作为根 Span | `start_turn()` 时创建 | `openclaw_request` |
| `prompt` | 记录提示词信息 | `start_step()` 时创建 | `user_message` |
| `message` | 消息记录（预留） | 未来扩展 | - |
| `rag` | 检索增强生成（预留） | 未来扩展 | - |
| `session` | 会话生命周期（预留） | 未来扩展 | - |
| `gateway` | 网关层面监控 | `monitor.py` 启动时 | 服务级监控 |

**与 OpenClaw 对齐的 Trace 结构**:
```
entry (root)                    ← 对应 openclaw_request
└── agent (agent_turn)
    ├── prompt (prompt_1)       ← 对应 user_message
    └── model (step_n)          ← 对应 model_provider/model_name
        ├── tool:read           ← 对应 read tool
        ├── tool:write          ← 对应 write tool
        └── tool:shell          ← 对应其他 tools
```

**OpenClaw 兼容性**: 结构设计与官方 OpenClaw Trace 插件保持一致，便于在 CozeLoop 中进行对比分析。

#### 3. Token 追踪增强（OpenTelemetry 标准）

重写 `update_token_usage()` 方法，支持 `gen_ai.*` 标准属性，实现 OpenClaw 同等级别的 Token 消耗统计：

**新增属性**:
- `gen_ai.usage.input_tokens` - 输入 Token 数
- `gen_ai.usage.output_tokens` - 输出 Token 数
- `gen_ai.usage.cache_read_tokens` - 缓存读取 Token 数
- `gen_ai.usage.cache_write_tokens` - 缓存写入 Token 数
- `gen_ai.usage.total_tokens` - 总 Token 数
- `gen_ai.provider.name` - 模型提供商
- `gen_ai.request.model` - 模型名称

**应用场景**（对标 OpenClaw 文档）:
- **统计 Token 消耗**: 在 CozeLoop 观测 > 统计页面查看不同模型的 Token 消耗
- **成本控制**: 分析各模型调用成本，优化使用策略
- **缓存效率分析**: 通过 cache_read/write 评估缓存命中率

**与 OpenClaw 兼容**:
- 缓存 Token 映射对齐 OpenClaw 格式 (`cacheRead`/`cacheWrite`)
- 支持官方文档描述的 `usage` 字段结构

#### 4. Runtime 信息设置

新增动态 Runtime 信息检测和设置，自动识别 AI IDE 类型：

- **动态 Agent 类型检测**: 
  - 优先级 1: `AGENT_TYPE` 环境变量
  - 优先级 2: 父进程名称检测（区分 Kimi CLI / Claude Code）
  - 优先级 3: 默认 `kimi_cli`
- **Runtime 对象设置**: 在 Root Span 上设置 `language/library/scene`

**新增方法**:
- `_detect_agent_type()` - 三层检测机制
- `_create_runtime()` - 创建 Runtime 对象

**使用场景**:
- 多 AI IDE 环境（同时安装 Kimi CLI 和 Claude Code）时自动区分来源
- 在 CozeLoop 中按 Agent 类型过滤和分析 Trace 数据

#### 5. Gateway Span 实现

在 Monitor 启动时创建 Gateway Span，提供服务级可观测性（类似于 OpenClaw 网关监控）：

**包含属性**:
- `gateway.version` - agent-trace 版本号
- `gateway.working_dir` - 工作目录
- `gateway.sessions_dir` - 会话目录
- `gateway.poll_interval` - 轮询间隔
- `gateway.deduplication` - 去重启用状态
- `gateway.persistent_offset` - Offset 持久化状态
- `gateway.hostname` - 主机名
- `gateway.pid` - 进程 ID

**生命周期**: 服务启动时创建，停止时结束（记录运行时长和统计信息）

**监控价值**:
- 追踪 AgentTrace 服务本身的运行状态
- 统计服务运行时长、处理的 Session 数量
- 在 CozeLoop 中独立查看 Gateway 维度指标

#### 6. Bug 修复

**修复 ToolCall/ToolResult 解析错误**:
- **问题**: `parse_tool_call()` 方法错误地期望嵌套格式 `{"tool_call": {...}}`，但 Kimi CLI v1.17.0 实际输出直接格式 `{"type": "function", "function": {...}}`
- **影响**: 所有工具名称显示为 "unknown"，Tool Span 无法正确关联到 Model Span
- **修复**: 更新解析逻辑，同时支持直接格式和嵌套格式
  ```python
  if 'tool_call' in payload:
      tool_call = payload.get('tool_call', {})
  else:
      tool_call = payload  # 直接格式（Kimi CLI v1.17.0）
  ```
- **验证**: 修复后工具名称正确显示（如 `Tool Shell started`、`Tool Glob started`）

**修复 Tool Span 上报问题**:
- **问题**: 由于 Token 认证错误（HTTP 401）和缓存代码，Tool Span 实际上报失败
- **修复**: 
  1. 清除 Python 缓存 (`__pycache__`, `*.pyc`)
  2. 使用正确的 `COZELOOP_API_TOKEN`
  3. 验证 Tool Span 正确关联到父级 Model Span
- **结果**: Tool Span 现在正确显示在 CozeLoop 仪表盘中

#### 7. 其他改进

- **版本号更新**: v0.3.3 → v0.3.4
- **Entry Span 集成**: 作为真正的根节点，Agent Span 作为子节点
- **Prompt Span 自动创建**: 在每个 Step 开始前记录用户输入
- **Trace 标签增强**: Root Span 自动附加 `trace_id` 和 `run_id` 标签
- **逐步上报机制**: 已完成的 Span 立即上报，实时查看执行状态

**修改文件**:
- `src/agent_trace/core/session_state.py` - 核心优化（Span 类型、Token 追踪、Runtime）
- `src/agent_trace/core/monitor.py` - Gateway Span
- `src/agent_trace/core/trace_context.py` - 新增 TraceContext 管理
- `src/agent_trace/core/__init__.py` - 导出新增模块
- `src/agent_trace/parsers/wire_parser.py` - ToolCall/ToolResult 解析修复

---

### 📊 在 CozeLoop 中查看 Trace 数据

完成上述更新后，启动 AgentTrace 并发起一次 Kimi CLI 对话：

1. **访问 CozeLoop 工作空间**: https://www.coze.cn/loop/
2. **进入观测 > Trace 页面**
3. **设置上报类型为 SDK 上报**
4. **查看 Trace 数据**:
   - 点击任意 Trace 查看详细的 Span 调用链
   - 切换到 "All Span" 视图查看实时执行状态
   - 查看 Tool Span 的输入/输出和耗时信息

**排查问题**:
- 如果 Tool Span 未显示，检查日志中是否有 `Tool started` 和 `Tool finished`
- 如果有 HTTP 401 错误，确认 `COZELOOP_API_TOKEN` 是否正确
- 使用 `agent-trace --status` 检查服务运行状态

---

## [0.3.3] - 2026-03-18

### 🔧 核心 Bug 修复（13+ 项）

#### 🔴 高优先级修复

1. **修复事件 ID 生成问题**
   - **问题**: 事件 ID 仅基于 `session_id + turn_index + step_n + event_type` 生成，导致同一 turn 内的重复事件无法区分
   - **修复**: 在 `EventID` 类中添加 `timestamp` 字段，确保每个事件 ID 全局唯一

2. **修复 TurnBegin 多轮对话处理**
   - **问题**: 多轮对话时，新的 TurnBegin 没有正确处理已有 root_span
   - **修复**: 检测到已有 root_span 时，先结束当前 turn，自动递增 `turn_index`

3. **修复工具调用 event_id 非确定性**
   - **问题**: `hash(tool_call_id)` 在 Python 重启后值不同，导致去重失效
   - **修复**: 使用 `hashlib.sha256(str(tool_call_id).encode()).hexdigest()` 生成确定性哈希

4. **修复 LRU 缓存实现错误**
   - **问题**: `list + set` 实现的是 FIFO 而非真正的 LRU
   - **修复**: 使用 `OrderedDict` 实现真正的 LRU 缓存，`move_to_end()` + `popitem(last=False)`

5. **修复 KeyboardInterrupt 被捕获**
   - **问题**: `retry.py` 中 `except Exception` 兜底拦截了 `KeyboardInterrupt`
   - **修复**: 移除 `Exception` 兜底，防止拦截 `Ctrl+C`

6. **修复 Windows 完全不兼容**
   - **问题**: `fcntl` 是 Unix 特有模块，Windows 导入失败
   - **修复**: 添加平台检测，Windows 使用 socket 绑定作为锁机制

#### 🔶 中优先级修复

7. **修复数据库路径不一致**
   - **修复**: `~/.kimi/monitor/` → `~/.agenttrace/`

8. **修复日志文件名不一致**
   - **修复**: `/tmp/kimi-cozeloop.log` → `/tmp/agent-trace.log`

9. **修复项目名称残留**
   - **修复**: "Kimi Monitor" → "AgentTrace"

10. **修复条件表达式优先级**
    - **修复**: `wire_parser.py` 添加括号 `(str(return_value) if return_value else '')`

11. **修复延迟导入问题**
    - **修复**: `hashlib`, `os` 移到文件顶部

#### 🟢 低优先级修复

12. **修复未使用的导入**
    - **修复**: 移除 `monitor.py`, `config.py`, `wire_parser.py` 中的未使用导入

13. **修复 tool_call_id 类型问题**
    - **修复**: `str(tool_call_id)[:16]` 确保字符串类型

14. **修复 step_n 不一致**
    - **修复**: `_mark_processed` 使用正确的 `step_n` 变量

15. **修复 PID 文件路径不一致**
    - **修复**: `/tmp/agent-trace.pid` → `/tmp/agent_trace.pid`

16. **修复 API Token 泄露风险**
    - **问题**: API Token 被直接写入系统服务配置文件
    - **修复**: 
      - 使用独立的 `~/.agenttrace/.env` 文件存储敏感信息
      - 设置文件权限 `0o600`（仅所有者可读写）
      - 服务配置使用 `EnvironmentFile` 加载

#### 代码质量改进

17. **修复文件读取 tell() 问题**
    - **修复**: 使用 `readline()` 替代 `for line in f` 循环

18. **添加路径遍历防护**
    - **修复**: `jsonl_reader.py` 添加 `_sanitize_path()` 方法

19. **添加 incomplete_line 长度限制**
    - **修复**: 限制最大 1MB，防止内存耗尽

#### 安全改进

20. **添加命令行敏感信息警告**
    - 检测用户是否通过命令行参数传递敏感信息
    - 警告信息会显示在 `ps aux` 和 shell history 中的风险

21. **日志自动脱敏**
    - Token 和 Workspace ID 在日志中自动脱敏显示
    - 短字符串完全隐藏，长字符串显示前后各4字符

#### 日志改进

22. **添加日志轮转**
    - 使用 `RotatingFileHandler`
    - 单个文件最大 10MB，保留 5 个备份

23. **添加详细日志前缀**
    - `[WIRE]` - Wire 协议事件解析
    - `[EVENT:xxx]` - 事件处理状态
    - `[DEDUP]` - 去重检查
    - 状态指示器：`root_span=✓`, `current_step=✗`

### 🧪 新增测试文档

- 新增 `docs/TESTING.md` 完整测试指南
  - 手动测试流程（使用 kimi 命令）
  - 单元测试、集成测试、端到端测试
  - CI/CD 配置示例
  - 测试最佳实践

### 📦 修改文件统计

共修改 **15+ 个文件**：
- `src/agent_trace/core/dedup.py`
- `src/agent_trace/core/session_state.py`
- `src/agent_trace/core/persistent_offset.py`
- `src/agent_trace/core/__init__.py`
- `src/agent_trace/core/monitor.py`
- `src/agent_trace/utils/config.py`
- `src/agent_trace/utils/retry.py`
- `src/agent_trace/utils/logging_config.py`
- `src/agent_trace/utils/singleton.py`
- `src/agent_trace/parsers/wire_parser.py`
- `src/agent_trace/parsers/jsonl_reader.py`
- `src/agent_trace/cli.py`
- `src/agent_trace/autostart/__init__.py`
- `src/agent_trace/autostart/*/ *.template`
- `docs/TESTING.md` (新增)

---

## [0.3.2] - 2026-03-18

### 🛡️ 重要修复 - 单实例运行

**问题**: 发现多个旧版本进程同时运行导致 Trace 重复上报

**解决方案**: 新增单实例锁机制

#### 新增功能
- **单实例锁** (`--force` 选项)
  - 使用 PID 文件 + 文件锁确保只有一个实例运行
  - 自动检测已有进程并阻止重复启动
  - 支持 `--force` 强制启动（杀死旧进程）
  - 支持 `--status` 查看运行状态

- **新增工具模块** (`utils/singleton.py`)
  - `SingleInstanceLock`: 单实例锁管理器
  - `get_running_instance_info()`: 获取运行中实例信息
  - 自动清理机制（异常退出时释放锁）

#### 命令行更新
```bash
# 检查是否已有实例在运行
agent-trace --status

# 如果已有实例，会报错并提示 PID
agent-trace
# ❌ Error: Another instance is already running (PID: 12345)

# 强制启动（杀死旧进程）
agent-trace --force

# 停止旧进程后启动
kill 12345
agent-trace
```

#### 日志增强
- `[SINGLETON]` - 单实例锁相关日志
- `[DEDUP]` - 去重检查日志（v0.3.1 新增）
- `[SESSION:xxx]` - Session 事件日志（v0.3.1 新增）

---

## [0.3.1] - 2026-03-18

### 新增功能

- **项目重构**：完整重构为现代 Python 开源项目结构
  - 采用 `src/` layout 标准结构
  - 使用 `pyproject.toml` 替代 `setup.py`
  - 使用 Hatch 作为构建工具
  - 添加完整的 CI/CD 工作流

- **CLI 入口优化**
  - 新增 `agent-trace` 命令
  - 新增 `atrace` 简写命令
  - 改进命令行参数解析

- **文档完善**
  - 新增 REFERENCES.md 参考资料文档
  - 完善 README 文档
  - 新增 ROADMAP.md 版本规划

### 改进

- 统一包名：`kimi_monitor` 改为 `agent_trace`
- 统一类名：`KimiSessionMonitor` 改为 `AgentTraceMonitor`
- 改进日志路径：从 `/tmp/kimi-cozeloop.log` 改为 `/tmp/agent-trace.log`
- 优化导入结构

### 构建

- 配置 Hatch 构建系统
- 配置 Trusted Publishing 到 PyPI
- 添加 GitHub Actions CI/CD
- 添加代码质量检查（black, ruff, mypy）

---

## [0.3.0] - 2026-03-18

### 新增功能 - Span 重复上报问题彻底解决 + 开机自启动

基于对 6 个开源项目的深度调研，实现了完整的事件去重、增量读取方案和跨平台自启动支持：

#### 1. 事件去重机制（借鉴 LangSmith run_id 幂等性）
- **分层去重策略**：
  - L0: 当前会话内存缓存（Set）
  - L1: 全局内存缓存（LRU，默认 10000 条）
  - L2: SQLite 持久化存储（WAL 模式）
- **确定性事件 ID**：使用 SHA256 生成 32 位事件 ID
- **TTL 自动清理**：过期记录自动清理（默认 24 小时）

#### 2. Offset 持久化（借鉴 OTel FileLog Receiver + Fluent Bit）
- **SQLite 存储**：使用 WAL 模式保证数据安全
- **文件指纹**：检测 inode 复用问题
- **截断检测**：文件被截断时自动从头读取
- **Offset 验证**：启动时验证 offset 有效性

#### 3. 跨平台开机自启动
- **macOS**: launchd (用户级服务，登录即启动)
- **Linux**: systemd (支持用户级和系统级)
- **Windows**: Windows Service (后台服务)
- **自动重启**: 崩溃后自动重启

---

## [0.2.3] - 2026-03-18

### 关键修复
- **修复 SDK 上报失败问题**: 
  - 原因：`set_output()` 接收 ModelOutput 对象时报错
  - 解决：改用字符串方式 `set_output("模型输出")`

### 架构改进
- **显式创建 SDK 客户端**: 配置大队列避免队列满载
- **增大队列容量**: 从默认 1024 增加到 10000
- **优化历史数据处理**: 启动时只扫描最近 5 分钟内的会话

---

## [0.2.2] - 2026-03-17

### 安全修复
- **移除敏感信息硬编码**: 从代码中移除硬编码的 API Token

### Bug 修复
- **修复内存泄漏**: 文件删除时正确清理 session_states
- **修复 Token 累计逻辑**: 每个 step 独立计算

### 新功能
- **添加缺失的事件处理器**: ApprovalRequestHandler 和 ApprovalResponseHandler
- **添加重试机制**: 指数退避自动重试

---

## [0.2.1] - 2026-03-17

### 初始版本
- V2 架构重构版本
- 模块化设计
- 完整的 Wire 协议支持

---

## 版本说明

### 版本号规则
- **主版本号（MAJOR）**: 不兼容的 API 修改
- **次版本号（MINOR）**: 向下兼容的功能性新增
- **修订号（PATCH）**: 向下兼容的问题修正
