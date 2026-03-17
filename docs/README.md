# AgentTrace 文档中心

欢迎使用 AgentTrace 文档！这里包含了项目的完整文档，帮助您快速上手和深入理解。

## 📚 文档目录

### 入门指南

| 文档 | 说明 | 适合人群 |
|------|------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构设计 | 架构师、开发者 |
| [DESIGN.md](DESIGN.md) | 详细设计文档 | 核心开发者 |
| [API.md](API.md) | API 参考手册 | 开发者 |

### 开发指南

| 文档 | 说明 | 适合人群 |
|------|------|----------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南 | 贡献者 |

### 运维支持

| 文档 | 说明 | 适合人群 |
|------|------|----------|
| [FAQ.md](FAQ.md) | 常见问题解答 | 所有用户 |

---

## 🚀 快速开始

### 1. 安装

```bash
pip install cozeloop
```

### 2. 配置

```bash
export COZELOOP_WORKSPACE_ID="your-workspace-id"
export COZELOOP_API_TOKEN="your-api-token"
```

### 3. 启动

```bash
agent-trace
```

---

## 📖 阅读建议

### 新用户

1. 先阅读 [FAQ.md](FAQ.md) 了解基本概念
2. 按照快速开始步骤体验
3. 遇到问题再查 FAQ

### 开发者

1. 阅读 [ARCHITECTURE.md](ARCHITECTURE.md) 了解系统架构
2. 阅读 [DESIGN.md](DESIGN.md) 深入理解核心设计
3. 参考 [API.md](API.md) 进行开发
4. 阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 参与贡献

### 运维人员

1. 参考 [FAQ.md](FAQ.md) 进行故障排查
2. 查看日志和统计信息定位问题

---

## 🔍 关键特性

### v0.3.0 新特性

- ✅ **事件去重**：三层去重机制，彻底解决重复上报
- ✅ **Offset 持久化**：进程重启不丢数据
- ✅ **文件指纹**：检测 inode 复用，避免错误读取
- ✅ **开机自启动**：跨平台支持（macOS/Linux/Windows）

### 架构特点

- 模块化设计，易于扩展
- 分层去重，高效可靠
- SQLite 持久化，零配置
- 异步处理，低资源占用

---

## 📞 获取帮助

- **GitHub Issues**: 报告 Bug 或提出功能建议
- **FAQ**: 查看常见问题解答
- **日志文件**: `/tmp/agent-trace.log`

---

## 📝 文档版本

- **当前版本**: v0.3.2
- **最后更新**: 2026-03-18
- **兼容版本**: AgentTrace >= v0.3.0

---

*AgentTrace - AI IDE 会话监控与 Trace 上报工具*
