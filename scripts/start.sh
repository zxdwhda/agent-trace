#!/bin/bash
# AgentTrace 启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PIDFILE="/tmp/agent-trace.pid"
LOGFILE="/tmp/agent-trace.log"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_env() {
    if [ -z "$COZELOOP_WORKSPACE_ID" ] || [ -z "$COZELOOP_API_TOKEN" ]; then
        echo -e "${RED}Error: 请设置环境变量${NC}"
        echo "  export COZELOOP_WORKSPACE_ID=your-workspace-id"
        echo "  export COZELOOP_API_TOKEN=your-api-token"
        exit 1
    fi
}

start() {
    check_env
    
    if [ -f "$PIDFILE" ]; then
        echo -e "${YELLOW}已经在运行中 (PID: $(cat $PIDFILE))${NC}"
        return
    fi
    
    echo -e "${GREEN}启动 AgentTrace...${NC}"
    cd "$PROJECT_ROOT"
    nohup python -m agent_trace > "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    
    sleep 1
    echo -e "${GREEN}启动成功 (PID: $!)${NC}"
    echo "日志: $LOGFILE"
}

stop() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        echo -e "${YELLOW}停止 AgentTrace (PID: $PID)...${NC}"
        kill "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null
        rm -f "$PIDFILE"
        echo -e "${GREEN}已停止${NC}"
    else
        echo -e "${YELLOW}没有在运行${NC}"
    fi
}

status() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}运行中 (PID: $PID)${NC}"
            echo "日志: $LOGFILE"
            tail -n 5 "$LOGFILE"
        else
            echo -e "${RED}进程不存在，清理 PID 文件${NC}"
            rm -f "$PIDFILE"
        fi
    else
        echo -e "${YELLOW}没有在运行${NC}"
    fi
}

logs() {
    tail -f "$LOGFILE"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    status) status ;;
    logs) logs ;;
    *) echo "Usage: $0 {start|stop|restart|status|logs}" ;;
esac
