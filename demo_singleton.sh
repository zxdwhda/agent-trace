#!/bin/bash
# 单实例锁功能演示脚本

echo "=========================================="
echo "AgentTrace v0.3.2 单实例锁演示"
echo "=========================================="
echo ""

# 设置环境变量
export COZELOOP_WORKSPACE_ID="${COZELOOP_WORKSPACE_ID:-test}"
export COZELOOP_API_TOKEN="${COZELOOP_API_TOKEN:-test}"
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

echo "1. 检查当前状态..."
python3 -m agent_trace --status
echo ""

echo "2. 启动第一个实例（后台运行）..."
nohup python3 -m agent_trace --log-level INFO > /tmp/agent-trace-demo.log 2>&1 &
PID1=$!
echo "   第一个实例 PID: $PID1"
echo ""

sleep 2

echo "3. 再次检查状态..."
python3 -m agent_trace --status
echo ""

echo "4. 尝试启动第二个实例（应该失败）..."
python3 -m agent_trace --log-level INFO 2>&1 | head -5
echo ""

echo "5. 使用 --force 强制启动（会杀死旧进程）..."
nohup python3 -m agent_trace --force --log-level INFO > /tmp/agent-trace-demo.log 2>&1 &
PID2=$!
echo "   新实例 PID: $PID2"
echo ""

sleep 1

echo "6. 检查最终状态..."
python3 -m agent_trace --status
echo ""

echo "7. 清理..."
kill $PID2 2>/dev/null || true
rm -f /tmp/agent_trace.pid
sleep 1
python3 -m agent_trace --status
echo ""

echo "=========================================="
echo "演示完成"
echo "=========================================="
