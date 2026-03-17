# Changelog

所有版本的变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

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
