#!/usr/bin/env python3
"""
单实例运行管理器

确保同一时间只有一个 AgentTrace 进程在运行
防止多个进程同时监控导致的重复上报问题
"""

import os
import sys
import atexit
import signal
import fcntl
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent_trace")


class SingleInstanceLock:
    """
    单实例锁
    
    使用 PID 文件 + 文件锁机制确保单实例运行
    支持跨平台（Unix/Linux/macOS）
    """
    
    def __init__(self, lock_name: str = "agent_trace"):
        """
        初始化单实例锁
        
        Args:
            lock_name: 锁名称，用于生成 PID 文件名
        """
        self.lock_name = lock_name
        self.pid_file = Path(f"/tmp/{lock_name}.pid")
        self.lock_file: Optional[int] = None
        self._acquired = False
    
    def acquire(self, force: bool = False) -> bool:
        """
        获取单实例锁
        
        Args:
            force: 是否强制获取（杀死旧进程）
            
        Returns:
            True 表示成功获取锁，False 表示已有实例在运行
        """
        try:
            # 检查是否已有进程在运行
            if self.pid_file.exists():
                old_pid = self._read_pid_file()
                if old_pid and self._is_process_running(old_pid):
                    if force:
                        logger.warning(f"[SINGLETON] Killing old process (PID: {old_pid})")
                        self._kill_process(old_pid)
                    else:
                        logger.error(f"[SINGLETON] Another instance is already running (PID: {old_pid})")
                        logger.error(f"[SINGLETON] PID file: {self.pid_file}")
                        logger.error("[SINGLETON] Use --force to override, or stop the existing instance first")
                        return False
            
            # 创建 PID 文件并获取文件锁
            self.lock_file = os.open(str(self.pid_file), os.O_CREAT | os.O_RDWR)
            try:
                # 尝试获取排他锁（非阻塞）
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                # 锁已被占用
                os.close(self.lock_file)
                self.lock_file = None
                logger.error("[SINGLETON] Another instance is already running (file lock)")
                return False
            
            # 写入当前 PID
            os.ftruncate(self.lock_file, 0)
            os.write(self.lock_file, str(os.getpid()).encode())
            os.fsync(self.lock_file)
            
            self._acquired = True
            
            # 注册退出时清理
            atexit.register(self.release)
            
            # 处理信号，确保异常退出时也能释放锁
            self._setup_signal_handlers()
            
            logger.info(f"[SINGLETON] Lock acquired: {self.pid_file} (PID: {os.getpid()})")
            return True
            
        except Exception as e:
            logger.error(f"[SINGLETON] Error acquiring lock: {e}")
            self.release()
            return False
    
    def release(self):
        """释放单实例锁"""
        if not self._acquired:
            return
        
        try:
            # 释放文件锁
            if self.lock_file is not None:
                try:
                    fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                    os.close(self.lock_file)
                except:
                    pass
                self.lock_file = None
            
            # 删除 PID 文件
            if self.pid_file.exists():
                try:
                    self.pid_file.unlink()
                except:
                    pass
            
            self._acquired = False
            logger.info(f"[SINGLETON] Lock released: {self.pid_file}")
            
        except Exception as e:
            logger.error(f"[SINGLETON] Error releasing lock: {e}")
    
    def _read_pid_file(self) -> Optional[int]:
        """读取 PID 文件中的进程 ID"""
        try:
            content = self.pid_file.read_text().strip()
            return int(content) if content else None
        except:
            return None
    
    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否正在运行"""
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # 进程不存在
            return False
        except PermissionError:
            # 有权限问题，但进程存在
            return True
    
    def _kill_process(self, pid: int):
        """终止进程"""
        try:
            # 先尝试优雅终止
            os.kill(pid, signal.SIGTERM)
            # 等待进程结束
            import time
            for _ in range(10):  # 最多等待 5 秒
                if not self._is_process_running(pid):
                    break
                time.sleep(0.5)
            else:
                # 强制终止
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # 进程已经不存在
        except Exception as e:
            logger.error(f"[SINGLETON] Error killing process {pid}: {e}")
    
    def _setup_signal_handlers(self):
        """设置信号处理器，确保异常退出时也能释放锁"""
        def signal_handler(signum, frame):
            logger.info(f"[SINGLETON] Received signal {signum}, releasing lock...")
            self.release()
            # 恢复默认处理并重新触发信号
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        
        # 处理常见的终止信号
        for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
            try:
                signal.signal(sig, signal_handler)
            except:
                pass
    
    def __enter__(self):
        """上下文管理器入口"""
        if not self.acquire():
            raise RuntimeError("Another instance is already running")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.release()
        return False


def check_single_instance(force: bool = False) -> bool:
    """
    检查单实例
    
    这是一个便捷函数，用于快速检查是否可以运行
    
    Args:
        force: 是否强制运行（杀死旧进程）
        
    Returns:
        True 表示可以运行，False 表示已有实例在运行
    """
    lock = SingleInstanceLock()
    return lock.acquire(force=force)


def get_running_instance_info() -> Optional[dict]:
    """
    获取正在运行的实例信息
    
    Returns:
        包含 PID 和启动时间的字典，如果没有实例在运行则返回 None
    """
    pid_file = Path("/tmp/agent_trace.pid")
    if not pid_file.exists():
        return None
    
    try:
        pid = int(pid_file.read_text().strip())
        # 检查进程是否存在
        try:
            os.kill(pid, 0)
            # 获取进程启动时间（通过 /proc 文件系统）
            stat_file = Path(f"/proc/{pid}/stat")
            if stat_file.exists():
                # 简单返回 PID，详细状态可以后续扩展
                return {
                    "pid": pid,
                    "pid_file": str(pid_file),
                    "running": True
                }
            return {"pid": pid, "pid_file": str(pid_file), "running": True}
        except ProcessLookupError:
            return None
    except:
        return None
