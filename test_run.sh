#!/bin/bash
# AgentTrace v0.3.5 测试启动脚本

set -e

echo "=========================================="
echo "AgentTrace v0.3.5 测试启动"
echo "=========================================="

# 设置环境变量（请修改为你自己的值）
export COZELOOP_WORKSPACE_ID="${COZELOOP_WORKSPACE_ID:-请替换为你的workspace_id}"
export COZELOOP_API_TOKEN="${COZELOOP_API_TOKEN:-请替换为你的api_token}"
export COZELOOP_API_BASE="${COZELOOP_API_BASE:-https://api.coze.cn}"

# 检查环境变量
if [ "$COZELOOP_WORKSPACE_ID" = "请替换为你的workspace_id" ]; then
    echo "⚠️  请设置环境变量:"
    echo "  export COZELOOP_WORKSPACE_ID=xxx"
    echo "  export COZELOOP_API_TOKEN=yyy"
    exit 1
fi

echo "✅ 环境变量已设置"
echo "  WORKSPACE_ID: ${COZELOOP_WORKSPACE_ID:0:8}..."
echo "  API_TOKEN: ${COZELOOP_API_TOKEN:0:8}..."

# 停止旧进程
echo ""
echo "=== 清理旧进程 ==="
pkill -f "kimi_monitor" 2>/dev/null || true
pkill -f "agent_trace" 2>/dev/null || true
sleep 2
echo "✅ 旧进程已停止"

# 清理数据库（可选，用于测试）
echo ""
echo "=== 清理数据库（重置去重状态） ==="
rm -rf ~/.kimi/monitor ~/.agenttrace
echo "✅ 数据库已重置"

# 启动新版本
echo ""
echo "=== 启动 AgentTrace v0.3.5 ===="
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

# 使用 DEBUG 级别以便查看详细日志
python3 -m agent_trace --log-level DEBUG &
PID=$!
echo $PID > /tmp/agent-trace.pid

echo "✅ 监控已启动 (PID: $PID)"
echo "  日志文件: /tmp/agent-trace.log"
echo ""
echo "查看日志:"
echo "  tail -f /tmp/agent-trace.log"
echo ""
echo "停止监控:"
echo "  kill $PID"

# 等待几秒显示初始日志
sleep 3
echo ""
echo "=== 初始日志 ==="
tail -n 30 /tmp/agent-trace.log 2>/dev/null || echo "日志正在生成中..."
