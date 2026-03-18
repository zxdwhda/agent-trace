#!/usr/bin/env python3
"""
AgentTrace - CLI 入口

命令行接口，支持多种运行模式。
"""

import os
import sys
import argparse
import signal
import tempfile
from pathlib import Path

from .core.monitor import AgentTraceMonitor
from .utils.config import Config
from .utils.logging_config import setup_logging
from .utils.singleton import SingleInstanceLock, get_running_instance_info


def mask_sensitive(value: str, visible: int = 4) -> str:
    """脱敏敏感信息，显示前后各visible个字符，中间用***代替"""
    if not value:
        return "***"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return value[:visible] + "***" + value[-visible:]


def _check_cli_security(args):
    """
    检查命令行参数安全风险
    
    警告用户如果通过命令行传递敏感信息（这些信息可能在 ps aux 中暴露）
    """
    import warnings
    
    # 检查是否通过命令行（而非环境变量）传递敏感信息
    # 注意：argparse 的 default 会从环境变量读取，所以如果 args 值等于环境变量值，
    # 说明用户可能通过环境变量设置的
    workspace_from_env = os.getenv('COZELOOP_WORKSPACE_ID', '')
    token_from_env = os.getenv('COZELOOP_API_TOKEN', '')
    
    cli_exposed = []
    
    if args.workspace_id and args.workspace_id != workspace_from_env:
        cli_exposed.append('--workspace-id')
    
    if args.api_token and args.api_token != token_from_env:
        cli_exposed.append('--api-token')
    
    if cli_exposed:
        warnings.warn(
            f"\n{'='*60}\n"
            f"⚠️  安全警告：你正在通过命令行参数传递敏感信息：{', '.join(cli_exposed)}\n"
            f"   这些信息可能会在以下位置暴露：\n"
            f"   - 进程列表 (ps aux)\n"
            f"   - Shell 历史记录 (history)\n"
            f"   - 系统日志\n\n"
            f"   建议改用环境变量配置：\n"
            f"     export COZELOOP_WORKSPACE_ID=your-workspace-id\n"
            f"     export COZELOOP_API_TOKEN=your-api-token\n"
            f"     agent-trace\n"
            f"{'='*60}\n",
            UserWarning,
            stacklevel=3
        )


def daemonize():
    """
    将进程转为守护进程（Unix only）
    """
    import os
    
    # 第一次 fork
    try:
        pid = os.fork()
        if pid > 0:
            # 父进程退出
            sys.exit(0)
    except OSError as e:
        print(f"Fork #1 failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 脱离终端
    os.chdir("/")
    os.setsid()
    os.umask(0)
    
    # 第二次 fork
    try:
        pid = os.fork()
        if pid > 0:
            # 第一个子进程退出
            sys.exit(0)
    except OSError as e:
        print(f"Fork #2 failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 重定向标准输入输出
    sys.stdout.flush()
    sys.stderr.flush()
    
    stdin = open(os.devnull, 'r')
    stdout = open(os.devnull, 'a+')
    stderr = open(os.devnull, 'a+')
    
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())
    
    # 写入 PID 文件（与 singleton.py 保持一致）
    pid_file = Path(tempfile.gettempdir()) / "agent_trace.pid"
    pid_file.write_text(str(os.getpid()))


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        prog="agent-trace",
        description="AI IDE 会话监控与 Trace 上报工具 - 支持 Kimi、Claude 等",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    # 使用环境变量配置
    export COZELOOP_WORKSPACE_ID=xxx
    export COZELOOP_API_TOKEN=yyy
    agent-trace

    # 指定参数
    agent-trace --workspace-id xxx --api-token yyy

    # 调试模式
    agent-trace --log-level DEBUG

    # 开机自启动管理
    agent-trace autostart install
    agent-trace autostart status
    agent-trace autostart uninstall
        """
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'%(prog)s {get_version()}'
    )
    
    parser.add_argument(
        '--workspace-id',
        default=os.getenv('COZELOOP_WORKSPACE_ID', ''),
        help='CozeLoop Workspace ID (env: COZELOOP_WORKSPACE_ID)'
    )
    parser.add_argument(
        '--api-token',
        default=os.getenv('COZELOOP_API_TOKEN', ''),
        help='CozeLoop API Token (env: COZELOOP_API_TOKEN)'
    )
    parser.add_argument(
        '--api-base',
        default=os.getenv('COZELOOP_API_BASE', 'https://api.coze.cn'),
        help='CozeLoop API Base URL (env: COZELOOP_API_BASE)'
    )
    parser.add_argument(
        '--sessions-dir',
        default=os.getenv('KIMI_SESSIONS_DIR', '~/.kimi/sessions/'),
        help='Kimi sessions directory (env: KIMI_SESSIONS_DIR)'
    )
    parser.add_argument(
        '--poll-interval',
        type=float,
        default=float(os.getenv('KIMI_POLL_INTERVAL', '2.0')),
        help='Polling interval in seconds (env: KIMI_POLL_INTERVAL)'
    )
    parser.add_argument(
        '--log-level',
        default=os.getenv('KIMI_LOG_LEVEL', 'INFO'),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Log level (env: KIMI_LOG_LEVEL)'
    )
    parser.add_argument(
        '--log-file',
        default=os.getenv('KIMI_LOG_FILE', '/tmp/agent-trace.log'),
        help='Log file path (env: KIMI_LOG_FILE)'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run in daemon mode (background)'
    )
    parser.add_argument(
        '--disable-dedup',
        action='store_true',
        default=os.getenv('KIMI_DISABLE_DEDUP', '').lower() in ('1', 'true', 'yes'),
        help='Disable event deduplication (env: KIMI_DISABLE_DEDUP)'
    )
    parser.add_argument(
        '--disable-offset',
        action='store_true',
        default=os.getenv('KIMI_DISABLE_OFFSET', '').lower() in ('1', 'true', 'yes'),
        help='Disable persistent offset storage (env: KIMI_DISABLE_OFFSET)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force start even if another instance is running (kill old process)'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Check if AgentTrace is running and show status'
    )
    
    return parser.parse_args()


def get_version():
    """获取版本号"""
    try:
        from ._version import __version__
        return __version__
    except ImportError:
        return "0.3.5"


def main():
    """主入口"""
    args = parse_args()
    
    # 处理状态检查
    if args.status:
        info = get_running_instance_info()
        if info:
            print(f"✅ AgentTrace is running (PID: {info['pid']})")
            print(f"   PID file: {info['pid_file']}")
            print(f"   Log file: /tmp/agent-trace.log")
        else:
            print("❌ AgentTrace is not running")
        return
    
    # 处理 autostart 子命令
    if len(sys.argv) > 1 and sys.argv[1] == 'autostart':
        from .autostart import main as autostart_main
        autostart_main()
        return
    
    # 尝试获取单实例锁
    lock = SingleInstanceLock()
    if not lock.acquire(force=args.force):
        # 获取锁失败，已有实例在运行
        info = get_running_instance_info()
        if info:
            print(f"❌ Error: Another instance is already running (PID: {info['pid']})")
            print(f"   Use --force to override, or run 'agent-trace --status' to check status")
            print(f"   Or stop the existing instance: kill {info['pid']}")
        else:
            print("❌ Error: Cannot acquire lock. Try removing /tmp/agent_trace.pid")
        sys.exit(1)
    
    # 获取锁成功，继续运行
    try:
        _run_monitor(args)
    finally:
        lock.release()


def _run_monitor(args):
    """运行监控服务的内部函数"""
    # 检查敏感信息是否通过命令行传递（安全风险警告）
    _check_cli_security(args)
    
    # 设置日志
    logger = setup_logging(args.log_level, args.log_file)
    
    # 创建配置
    config = Config(
        workspace_id=args.workspace_id,
        api_token=args.api_token,
        api_base=args.api_base,
        sessions_dir=args.sessions_dir,
        poll_interval=args.poll_interval,
        log_level=args.log_level,
        log_file=args.log_file,
    )
    
    # 设置 SDK 环境变量
    config.setup_env()
    
    # 验证 SDK 并创建显式客户端
    try:
        import cozeloop
        from cozeloop.internal.trace.model.model import QueueConf
        logger.info(f"CozeLoop SDK version: {cozeloop.__version__}")
        
        # 显式创建客户端，配置更大的队列避免队列满载
        queue_conf = QueueConf(
            span_queue_length=10000,
            span_max_export_batch_length=100
        )
        client = cozeloop.new_client(
            workspace_id=config.workspace_id,
            api_token=config.api_token,
            api_base_url=config.api_base,
            trace_queue_conf=queue_conf,
        )
        logger.info(f"Created CozeLoop client with queue size 10000")
    except AttributeError:
        logger.info("CozeLoop SDK loaded")
    except ImportError:
        logger.error("CozeLoop SDK not installed. Install with: pip install cozeloop")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to create CozeLoop client: {e}")
        sys.exit(1)
    
    # 显示配置（脱敏）
    logger.info(f"Workspace ID: {mask_sensitive(config.workspace_id)}")
    logger.info(f"API Token: {mask_sensitive(config.api_token)}")
    logger.info(f"API Base: {config.api_base}")
    
    # 处理 daemon 模式
    if args.daemon:
        daemonize()
    
    # 创建监控服务
    enable_deduplication = not args.disable_dedup
    enable_persistent_offset = not args.disable_offset
    
    monitor = AgentTraceMonitor(
        sessions_dir=config.sessions_dir,
        poll_interval=config.poll_interval,
        enable_deduplication=enable_deduplication,
        enable_persistent_offset=enable_persistent_offset,
    )
    
    # 信号处理
    _shutdown_requested = False
    
    def signal_handler(signum, frame):
        nonlocal _shutdown_requested
        if _shutdown_requested:
            logger.warning("Force shutdown requested, exiting immediately")
            sys.exit(1)
        _shutdown_requested = True
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        try:
            monitor.stop()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            sys.exit(0)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 忽略 SIGPIPE
    if hasattr(signal, 'SIGPIPE'):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    
    # 启动监控
    try:
        monitor.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        monitor.stop()
        sys.exit(1)


if __name__ == '__main__':
    main()
