# AgentTrace 常见问题解答 (FAQ)

## 目录

- [安装问题](#安装问题)
- [配置问题](#配置问题)
- [运行问题](#运行问题)
- [故障排查](#故障排查)
- [性能问题](#性能问题)

---

## 安装问题

### Q: 安装 `cozeloop` 失败怎么办？

**A:** 尝试以下方法：

```bash
# 方法 1: 使用国内镜像
pip install cozeloop -i https://pypi.tuna.tsinghua.edu.cn/simple

# 方法 2: 升级 pip 后重试
pip install --upgrade pip
pip install cozeloop

# 方法 3: 从源码安装
git clone https://github.com/coze-dev/cozeloop-python.git
cd cozeloop-python
pip install -e .
```

### Q: Python 版本要求是什么？

**A:** 
- 最低要求：Python 3.8+
- 推荐版本：Python 3.10 或 3.11

```bash
# 检查 Python 版本
python --version

# 如果系统 Python 版本过低，可以使用 pyenv
pyenv install 3.11.0
pyenv local 3.11.0
```

### Q: 需要安装哪些系统依赖？

**A:** 通常不需要额外的系统依赖。如果遇到 SQLite 相关问题：

```bash
# macOS
brew install sqlite3

# Ubuntu/Debian
sudo apt-get install sqlite3 libsqlite3-dev

# CentOS/RHEL
sudo yum install sqlite sqlite-devel
```

---

## 配置问题

### Q: 如何获取 Coze 罗盘的工作空间 ID 和 API Token？

**A:**

1. 访问 [Coze 罗盘控制台](https://loop.coze.cn/console)
2. 右上角查看 **Workspace ID**
3. 进入「设置 > API 密钥」
4. 点击「创建密钥」，生成 PAT Token

```bash
# 配置环境变量
export COZELOOP_WORKSPACE_ID="your-workspace-id"
export COZELOOP_API_TOKEN="your-pat-token"
```

### Q: 环境变量配置后不生效？

**A:** 检查以下几点：

```bash
# 1. 检查环境变量是否设置
echo $COZELOOP_WORKSPACE_ID
echo $COZELOOP_API_TOKEN

# 2. 如果为空，检查配置文件
# ~/.zshrc (macOS)
# ~/.bashrc (Linux)
cat ~/.zshrc | grep COZELOOP

# 3. 重新加载配置
source ~/.zshrc

# 4. 在 Python 中验证
python -c "import os; print(os.getenv('COZELOOP_WORKSPACE_ID'))"
```

### Q: 可以修改默认的会话目录吗？

**A:** 可以，通过环境变量修改：

```bash
# 修改会话目录
export KIMI_SESSIONS_DIR="/custom/path/to/sessions"

# 修改轮询间隔
export KIMI_POLL_INTERVAL=5.0

# 修改日志级别
export KIMI_LOG_LEVEL="DEBUG"
```

### Q: 如何配置开机自启动？

**A:** 使用内置命令：

```bash
# 安装自启动（macOS/Linux）
./src/start_monitor_v3.sh autostart install

# 检查状态
./src/start_monitor_v3.sh autostart status

# 卸载自启动
./src/start_monitor_v3.sh autostart uninstall
```

详见 [DEPLOYMENT_OPTIONS.md](DEPLOYMENT_OPTIONS.md)

---

## 运行问题

### Q: 启动后没有数据上报？

**A:** 按以下步骤排查：

```bash
# 1. 检查监控服务是否运行
./src/start_monitor_v3.sh status

# 2. 检查日志
tail -f /tmp/kimi-cozeloop-v3.log

# 3. 检查会话目录是否存在
ls -la ~/.kimi/sessions/

# 4. 检查是否有新的会话产生
# 启动一个新的 Kimi CLI 会话
kimi --yolo

# 5. 检查 wire.jsonl 文件
find ~/.kimi/sessions -name "wire.jsonl" -mtime -1
```

### Q: 日志显示 "duplicate event ignored" 是什么意思？

**A:** 这是正常行为，表示去重机制在工作：

```
[DEBUG] duplicate StepBegin ignored: step=1, event_id=abc123...
```

这说明同一个事件被检测到多次，但只处理了一次。这是 v0.3.0 的新特性，用于防止重复上报。

如果要查看统计：
```bash
./src/start_monitor_v3.sh stats
```

### Q: 如何停止监控服务？

**A:**

```bash
# 方法 1: 使用启动脚本
./src/start_monitor_v3.sh stop

# 方法 2: 查找并杀死进程
ps aux | grep kimi_monitor
kill <pid>

# 方法 3: 如果是自启动服务
# macOS
launchctl stop com.kimicode.monitor

# Linux
systemctl --user stop kimi-monitor
```

### Q: 监控服务占用 CPU/内存过高？

**A:** 

这是正常现象，因为监控服务需要：
1. 定期轮询检查文件变化
2. 处理事件并上报

**优化建议：**

```bash
# 1. 增加轮询间隔（降低 CPU 使用）
export KIMI_POLL_INTERVAL=5.0

# 2. 降低日志级别
export KIMI_LOG_LEVEL="WARNING"

# 3. 限制内存缓存大小（代码中配置）
# 在 dedup.py 中修改 memory_cache_size
```

正常情况下的资源占用：
- CPU: < 5%（轮询间隔 2 秒）
- 内存: < 100MB

---

## 故障排查

### Q: 进程崩溃后数据会丢失吗？

**A:** 不会。v0.3.0 引入了 Offset 持久化机制：

- 文件读取位置保存在 SQLite 中
- 进程重启后会从上次位置继续
- 可能重复最后几条记录，但不会丢失数据

```bash
# 查看 offset 统计
./src/start_monitor_v3.sh stats
```

### Q: 如何清理历史数据？

**A:**

```bash
# 方法 1: 使用启动脚本
./src/start_monitor_v3.sh clean

# 方法 2: 手动清理数据库
rm -rf ~/.kimi/monitor/

# 方法 3: 仅清理过期数据（自动）
# 系统会定期清理 24 小时前的去重记录和 7 天前的 offset 记录
```

### Q: SQLite 数据库损坏怎么办？

**A:**

```bash
# 1. 停止监控服务
./src/start_monitor_v3.sh stop

# 2. 备份损坏的数据库
mv ~/.kimi/monitor/dedup.db ~/.kimi/monitor/dedup.db.bak
mv ~/.kimi/monitor/offsets.db ~/.kimi/monitor/offsets.db.bak

# 3. 重启服务（会自动创建新数据库）
./src/start_monitor_v3.sh start

# 注意：数据库重建后，offset 会重置，可能重复处理部分数据
```

### Q: 文件权限错误？

**A:**

```bash
# 1. 检查会话目录权限
ls -la ~/.kimi/sessions/

# 2. 检查监控数据库目录权限
ls -la ~/.kimi/monitor/

# 3. 修复权限
chmod 755 ~/.kimi/sessions
chmod 755 ~/.kimi/monitor
chmod 644 ~/.kimi/monitor/*.db
```

### Q: 网络问题导致上报失败？

**A:** 系统会自动重试，您也可以检查：

```bash
# 1. 检查网络连接
ping api.coze.cn

# 2. 检查 API Token 是否有效
curl -H "Authorization: Bearer $COZELOOP_API_TOKEN" \
     https://api.coze.cn/v1/workspace

# 3. 查看日志中的错误信息
tail -f /tmp/kimi-cozeloop-v3.log | grep -i error
```

### Q: 如何调试事件处理流程？

**A:**

```bash
# 1. 启用 DEBUG 日志
export KIMI_LOG_LEVEL="DEBUG"

# 2. 运行监控
python -m kimi_monitor

# 3. 查看详细日志
# 您会看到类似：
# [DEBUG] Processing record: {"type": "TurnBegin", ...}
# [DEBUG] Event ID: abc123..., duplicate: False
# [INFO] TurnBegin: "分析代码..."
```

### Q: Span 层级结构不正确？

**A:** 这可能是已知问题。检查：

```bash
# 1. 确保使用的是 v0.2.1+
python -m kimi_monitor --version

# 2. 检查 TurnEnd 事件是否存在
# Kimi CLI 的 --print 模式下可能不写入 TurnEnd
# 建议使用正常模式：kimi --yolo

# 3. 查看 Coze 罗盘中的 Trace 详情
# 访问 https://loop.coze.cn/console
```

---

## 性能问题

### Q: 如何优化监控性能？

**A:**

```bash
# 1. 增加轮询间隔（减少 CPU 使用）
export KIMI_POLL_INTERVAL=5.0  # 默认 2.0

# 2. 限制同时监控的会话数
# 修改代码中的 MAX_ACTIVE_SESSIONS

# 3. 使用更快的存储（SSD）
# 数据库存放在 ~/.kimi/monitor/

# 4. 降低日志级别
export KIMI_LOG_LEVEL="WARNING"
```

### Q: 数据库文件越来越大？

**A:** 这是正常的，系统会自动清理：

```bash
# 查看数据库大小
ls -lh ~/.kimi/monitor/

# 手动清理过期数据
sqlite3 ~/.kimi/monitor/dedup.db \
    "DELETE FROM processed_events WHERE processed_at < $(date -v-7d +%s);"

# 清理 WAL 文件
sqlite3 ~/.kimi/monitor/dedup.db "VACUUM;"
```

**自动清理策略：**
- 去重记录：24 小时后自动清理
- Offset 记录：7 天后自动清理
- WAL 文件：SQLite 自动管理

### Q: 内存使用持续增长？

**A:** 

```bash
# 检查内存缓存大小限制
# 在 dedup.py 中，默认是 10000 条
memory_cache_size = 10000

# 如果内存仍然过高，可以：
# 1. 降低缓存大小
# 2. 缩短 TTL 时间
# 3. 更频繁地调用 cleanup_expired()
```

---

## 其他问题

### Q: 支持 Windows 吗？

**A:** 支持！v0.3.0 起支持跨平台：

```powershell
# Windows 安装自启动（需要管理员权限）
python -m kimi_monitor autostart install

# 查看状态
python -m kimi_monitor autostart status
```

### Q: 如何贡献代码？

**A:** 请参考 [CONTRIBUTING.md](CONTRIBUTING.md)

### Q: 如何报告 Bug？

**A:** 请提供以下信息：

1. 操作系统和版本
2. Python 版本
3. AgentTrace 版本
4. 复现步骤
5. 相关日志（`~/.kimi/monitor/` 和 `/tmp/kimi-cozeloop-v3.log`）

### Q: 有 Discord/微信群吗？

**A:** 暂未有官方社区，请在 GitHub Issue 中交流。

---

## 快速诊断清单

如果遇到问题，请按以下顺序检查：

```bash
# 1. 检查环境变量
echo $COZELOOP_WORKSPACE_ID
echo $COZELOOP_API_TOKEN

# 2. 检查服务状态
./src/start_monitor_v3.sh status

# 3. 查看日志
tail -n 100 /tmp/kimi-cozeloop-v3.log

# 4. 查看统计
./src/start_monitor_v3.sh stats

# 5. 检查数据库
ls -lh ~/.kimi/monitor/
sqlite3 ~/.kimi/monitor/dedup.db "SELECT COUNT(*) FROM processed_events;"

# 6. 检查会话文件
find ~/.kimi/sessions -name "wire.jsonl" -mtime -1 | head -5
```

---

*文档版本: v0.3.5*  
*最后更新: 2026-03-18*
