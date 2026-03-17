# AgentTrace 版本规划路线图

## 🎯 项目愿景

打造通用的 AI IDE 会话监控与 Trace 上报工具，支持所有主流 AI IDE（Kimi、Claude、Cursor、Windsurf 等），统一汇聚到 Coze 罗盘进行观测分析。

---

## 📅 版本规划

### v0.3.2 (2026-03-18) - 当前版本
**主题：现代化重构**

#### 已完成
- [x] 重构为现代 Python 开源项目结构（src/ layout）
- [x] 使用 pyproject.toml 替代 setup.py
- [x] 添加 Hatch 构建系统
- [x] 添加 CI/CD 工作流（GitHub Actions）
- [x] 完善文档（README, REFERENCES, ROADMAP）
- [x] 添加代码质量工具（black, ruff, mypy）

---

### v0.3.3 (进行中) - SDK 规范优化
**主题：对齐官方最佳实践**

基于官方 CozeLoop Python SDK 深度分析，优化 SDK 调用方式，提升数据格式规范性。

#### Phase 1: 代码规范优化 (P0)

- [x] **SDK 使用方式分析**
  - [x] 完成官方 SDK 深度调研
  - [x] 识别当前代码与官方规范的差异
  - [x] 制定优化方案

- [ ] **ModelInput/ModelOutput 结构改造** ⭐
  - [ ] 修改 `session_state.py`，model span 使用 `ModelInput`/`ModelOutput` 标准结构
  - [ ] 支持多模态输入格式（文本、图片、文件）
  - [ ] 使用 `ModelMessage` 构建标准化消息格式
  - [ ] 工作量: 2-3 小时

- [ ] **Client 实例管理优化**
  - [ ] 显式调用 `cozeloop.set_default_client(client)`
  - [ ] 或改为传递 client 引用到 SessionState
  - [ ] 工作量: 1-2 小时

#### Phase 2: 功能增强 (P1)

- [ ] **添加 @observe 装饰器支持**
  - [ ] 新增 `src/agent_trace/decorators.py`
  - [ ] 为工具函数提供简化追踪方式
  - [ ] 工作量: 3-4 小时

- [ ] **Prompt 功能集成**
  - [ ] 集成 CozeLoop 的 Prompt 管理能力
  - [ ] 支持 Prompt 获取与格式化
  - [ ] 工作量: 4-6 小时

#### Phase 3: 高级特性 (P2)

- [ ] **超大文本上报支持**
  - [ ] 开启 `ultra_large_report` 配置
  - [ ] 支持大文本内容上报
  - [ ] 工作量: 1 小时

- [ ] **跨服务 Trace 传递**
  - [ ] 支持通过 HTTP Header 传递 SpanContext
  - [ ] 实现 `to_header()` 和 `get_span_from_header()`
  - [ ] 工作量: 3-4 小时

#### SDK 优化详情

| 优化项 | 当前实现 | 官方推荐 | 优先级 | 状态 |
|--------|----------|----------|--------|------|
| Model Span 输入格式 | 字符串 | `ModelInput` 结构 | P0 | ⏳ |
| Client 管理 | 隐式全局 | 显式 `set_default_client` | P0 | ⏳ |
| Span 类型 | 自定义 `"agent"` | 参考官方类型定义 | P1 | ⏳ |
| 函数追踪 | 手动管理 | `@observe` 装饰器 | P1 | ⏳ |
| Prompt 管理 | 未使用 | `get_prompt()` 集成 | P2 | ⏳ |
| 超大文本 | 默认配置 | `ultra_large_report=True` | P2 | ⏳ |

#### 技术债务

- [ ] 完善类型注解（替换 `Any` 为具体类型）
- [ ] 补充单元测试覆盖
- [ ] 优化错误处理与重试机制

---

### v0.4.0 (开发中) - Claude Code 支持
**主题：双雄并立**

#### 功能开发
- [ ] **Claude Code 解析器**
  - [ ] `stream-json` 格式解析
  - [ ] 事件类型映射（Claude 到内部事件）
  - [ ] 会话文件监控（`~/.claude/projects/`）
  
- [ ] **双模式监控**
  - [ ] 自动检测 IDE 类型
  - [ ] 同时监控多个 IDE
  - [ ] 独立的状态管理
  
- [ ] **统一事件抽象层**
  - [ ] 定义通用事件协议
  - [ ] Kimi/Claude 适配器
  - [ ] 可扩展的解析器注册机制

#### Claude 事件映射

| Claude 事件 | 映射到 | 说明 |
|------------|--------|------|
| `assistant` 开始 | `TurnBegin` | 对话开始 |
| `text_delta` | `ContentPart(text)` | 文本流 |
| `tool_use` | `ToolCall` | 工具调用 |
| `tool_result` | `ToolResult` | 工具结果 |
| `result` | `TurnEnd` | 对话结束 |

#### 工作量评估
- 解析器开发: 6-8 小时
- 事件映射: 3-4 小时
- 集成测试: 4-6 小时
- 文档更新: 2 小时
- **总计**: 15-20 小时

---

### v0.5.0 (规划中) - 扩展生态
**主题：海纳百川**

#### 新 IDE 支持
- [ ] **Cursor 支持**
  - 调研 Cursor 的日志格式
  - 开发 Cursor 解析器
  
- [ ] **Windsurf 支持**
  - 调研 Windsurf 的日志格式
  - 开发 Windsurf 解析器

- [ ] **其他 IDE**
  - GitHub Copilot Chat
  - Continue.dev

#### 可观测性增强
- [ ] **Web Dashboard**
  - 实时监控面板
  - 会话列表与详情
  - Trace 可视化
  - 性能指标图表

- [ ] **自定义指标**
  - Token 使用量趋势
  - 工具调用频率
  - 响应延迟统计
  - 错误率监控

#### 告警与通知
- [ ] **告警规则**
  - Token 超限告警
  - 错误率告警
  - 响应延迟告警
  
- [ ] **通知渠道**
  - 飞书通知
  - 钉钉通知
  - 邮件通知
  - Webhook

---

### v0.6.0 (规划中) - 企业级特性
**主题：生产就绪**

#### 高可用
- [ ] 集群部署支持
- [ ] 配置中心集成
- [ ] 健康检查端点
- [ ] Prometheus 指标导出

#### 安全增强
- [ ] 配置加密存储
- [ ] API Token 轮换
- [ ] 审计日志
- [ ] 访问控制

#### 数据管理
- [ ] 数据归档与清理
- [ ] 数据导出（CSV/JSON）
- [ ] 数据备份与恢复
- [ ] 多工作区支持

---

### v1.0.0 (规划中) - 正式发布
**主题：成熟稳定**

#### 发布标准
- [ ] 支持 5+ 种 AI IDE
- [ ] 99.9% 数据完整性
- [ ] 完善的中文文档
- [ ] 100+ 单元测试
- [ ] 生产环境验证

---

## 🏗️ 架构演进

### 当前架构 (v0.3.x)
```
Kimi CLI → Wire JSONL → WireParser → EventHandler → CozeLoop
```

### 目标架构 (v0.5.0)
```
                    ┌─────────────────┐
Kimi CLI ──Wire──▶│                 │
                    │   统一事件层   │──▶ EventHandler ──▶ CozeLoop
Claude Code ─JSON▶│   GenericEvent │
                    │                 │
Cursor ───────?──▶│                 │
                    └─────────────────┘
```

---

## 📊 优先级矩阵

| 功能 | 价值 | 难度 | 优先级 | 版本 |
|------|------|------|--------|------|
| Claude 支持 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | P0 | v0.4.0 |
| Web Dashboard | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | P1 | v0.5.0 |
| Cursor 支持 | ⭐⭐⭐ | ⭐⭐⭐ | P2 | v0.5.0 |
| 告警通知 | ⭐⭐⭐ | ⭐⭐ | P2 | v0.5.0 |
| 集群部署 | ⭐⭐ | ⭐⭐⭐⭐⭐ | P3 | v0.6.0 |

---

## 🤝 如何参与

### 贡献方式
1. **提交 Issue** - 报告 bug 或提出需求
2. **提交 PR** - 实现新功能或修复问题
3. **完善文档** - 补充使用说明和示例
4. **分享经验** - 在社区分享使用心得

### 当前急需帮助
- [ ] Claude Code 的 stream-json 格式样本收集
- [ ] Windows 平台的自启动测试
- [ ] 性能测试与优化建议
- [ ] 中文文档翻译

---

## 📞 反馈渠道

- GitHub Issues: https://github.com/agenttrace/agent-trace/issues
- 讨论区: https://github.com/agenttrace/agent-trace/discussions

---

*最后更新: 2026-03-18*
*规划版本: v0.3.3 - v1.0.0*
