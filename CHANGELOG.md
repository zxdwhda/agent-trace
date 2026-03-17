# Changelog

所有版本的变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

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
