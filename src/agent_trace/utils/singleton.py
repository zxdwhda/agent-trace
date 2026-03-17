#!/usr/bin/env python3
"""
单实例运行管理器

确保同一时间只有一个 AgentTrace 进程在运行
防止多个进程同时监控导致的重复上报问题

支持平台：Unix/Linux/macOS/Windows
"""

import os
import sys
import atexit
import signal
import logging
import tempfile
import socket
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent_trace")

# 判断是否为 Windows 平台
IS_WINDOWS = sys.platform == 'win32'

# 仅在非 Windows 平台导入 fcntl
if not IS_WINDOWS:
    import fcntl


class SingleInstanceLock:
    """
    单实例锁
    
    使用 PID 文件 + 文件锁/socket 机制确保单实例运行
    支持跨平台（Unix/Linux/macOS/Windows）
    """
    
    def __init__(self, lock_name: str = "agent_trace"):
        """
        初始化单实例锁
        
        Args:
            lock_name: 锁名称，用于生成 PID 文件名
        """
        self.lock_name = lock_name
        # 使用系统临时目录，支持所有平台
        self.pid_file = Path(tempfile.gettempdir()) / f"{lock_name}.pid"
        self.lock_file: Optional[int] = None
        self._lock_socket: Optional[socket.socket] = None
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
            
            if IS_WINDOWS:
                # Windows 平台：使用 socket 绑定到特定端口作为锁
                return self._acquire_windows()
            else:
                # Unix/Linux/macOS 平台：使用 fcntl 文件锁
                return self._acquire_unix()
            
        except Exception as e:
            logger.error(f"[SINGLETON] Error acquiring lock: {e}")
            self.release()
            return False
    
    def _acquire_windows(self) -> bool:
        """
        Windows 平台获取锁的实现
        
        使用 socket 绑定到特定端口作为锁机制
        如果绑定失败（端口被占用），说明已有实例在运行
        """
        try:
            # 生成一个基于锁名称的固定端口号
            # 使用高位端口（>1024），避免与系统服务冲突
            port = self._get_lock_port()
            
            # 创建 socket 并尝试绑定
            self._lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._lock_socket.bind(('127.0.0.1', port))
            self._lock_socket.listen(1)
            
            # 写入当前 PID 到文件
            self._write_pid_file()
            
            self._acquired = True
            
            # 注册退出时清理
            atexit.register(self.release)
            
            # 设置信号处理器
            self._setup_signal_handlers()
            
            logger.info(f"[SINGLETON] Lock acquired: {self.pid_file} (PID: {os.getpid()}, Port: {port})")
            return True
            
        except socket.error as e:
            # 端口被占用，说明已有实例在运行
            if self._lock_socket:
                try:
                    self._lock_socket.close()
                except:
                    pass
                self._lock_socket = None
            logger.error(f"[SINGLETON] Another instance is already running (socket lock on port {self._get_lock_port()})")
            return False
        except Exception as e:
            logger.error(f"[SINGLETON] Error acquiring Windows lock: {e}")
            return False
    
    def _acquire_unix(self) -> bool:
        """
        Unix/Linux/macOS 平台获取锁的实现
        
        使用 fcntl 文件锁机制
        """
        try:
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
            logger.error(f"[SINGLETON] Error acquiring Unix lock: {e}")
            return False
    
    def _get_lock_port(self) -> int:
        """
        根据锁名称生成固定的端口号
        
        Returns:
            1025-65535 范围内的端口号
        """
        # 使用哈希生成固定端口号
        import hashlib
        hash_value = int(hashlib.md5(self.lock_name.encode()).hexdigest(), 16)
        # 确保端口在高位范围内（1025-65535）
        return 1025 + (hash_value % 64511)
    
    def _write_pid_file(self):
        """写入当前 PID 到文件"""
        try:
            self.pid_file.write_text(str(os.getpid()))
        except Exception as e:
            logger.warning(f"[SINGLETON] Failed to write PID file: {e}")
    
    def release(self):
        """释放单实例锁"""
        if not self._acquired:
            return
        
        try:
            if IS_WINDOWS:
                # Windows: 关闭 socket
                if self._lock_socket is not None:
                    try:
                        self._lock_socket.close()
                    except:
                        pass
                    self._lock_socket = None
            else:
                # Unix: 释放文件锁
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
            if IS_WINDOWS:
                # Windows: 使用 ctypes 检查进程
                return self._is_process_running_windows(pid)
            else:
                # Unix: 使用 os.kill 发送信号 0
                os.kill(pid, 0)
                return True
        except ProcessLookupError:
            # 进程不存在
            return False
        except PermissionError:
            # 有权限问题，但进程存在
            return True
        except Exception:
            return False
    
    def _is_process_running_windows(self, pid: int) -> bool:
        """Windows 平台检查进程是否运行"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            
            # 尝试打开进程
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            
            if handle:
                # 获取退出代码
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    kernel32.CloseHandle(handle)
                    # STILL_ACTIVE = 259
                    return exit_code.value == 259
                kernel32.CloseHandle(handle)
                return False
            else:
                # 打开失败，进程可能不存在或没有权限
                # 检查错误码
                error_code = kernel32.GetLastError()
                # ERROR_ACCESS_DENIED = 5，说明进程存在但没有权限
                return error_code == 5
        except Exception:
            # 如果 ctypes 方法失败，回退到 socket 检查
            return self._check_socket_lock()
    
    def _check_socket_lock(self) -> bool:
        """检查 socket 锁是否存在（Windows 备用方法）"""
        try:
            port = self._get_lock_port()
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(1)
            result = test_socket.connect_ex(('127.0.0.1', port))
            test_socket.close()
            # 如果连接成功 (0)，说明有进程在监听
            return result == 0
        except:
            return False
    
    def _kill_process(self, pid: int):
        """终止进程"""
        try:
            if IS_WINDOWS:
                self._kill_process_windows(pid)
            else:
                self._kill_process_unix(pid)
        except Exception as e:
            logger.error(f"[SINGLETON] Error killing process {pid}: {e}")
    
    def _kill_process_unix(self, pid: int):
        """Unix 平台终止进程"""
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
    
    def _kill_process_windows(self, pid: int):
        """Windows 平台终止进程"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            
            # 尝试优雅终止
            PROCESS_TERMINATE = 0x0001
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            
            if handle:
                # 发送退出信号（通过 Console 控制）
                # 首先尝试 GenerateConsoleCtrlEvent
                try:
                    if kernel32.GenerateConsoleCtrlEvent(0, pid):  # CTRL_C_EVENT
                        import time
                        for _ in range(10):
                            if not self._is_process_running(pid):
                                kernel32.CloseHandle(handle)
                                return
                            time.sleep(0.5)
                except:
                    pass
                
                # 强制终止
                kernel32.TerminateProcess(handle, 1)
                kernel32.CloseHandle(handle)
            else:
                # 如果无法打开进程，尝试使用 taskkill
                import subprocess
                subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                              capture_output=True, check=False)
        except Exception:
            # 回退到 taskkill
            try:
                import subprocess
                subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                              capture_output=True, check=False)
            except:
                pass
    
    def _setup_signal_handlers(self):
        """设置信号处理器，确保异常退出时也能释放锁"""
        def signal_handler(signum, frame):
            logger.info(f"[SINGLETON] Received signal {signum}, releasing lock...")
            self.release()
            # 恢复默认处理并重新触发信号
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        
        # 处理常见的终止信号
        signals_to_handle = [signal.SIGTERM, signal.SIGINT]
        
        # SIGHUP 在 Windows 上不存在
        if hasattr(signal, 'SIGHUP'):
            signals_to_handle.append(signal.SIGHUP)
        
        for sig in signals_to_handle:
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
    pid_file = Path(tempfile.gettempdir()) / "agent_trace.pid"
    if not pid_file.exists():
        return None
    
    try:
        pid = int(pid_file.read_text().strip())
        # 检查进程是否存在
        try:
            os.kill(pid, 0)
            return {
                "pid": pid,
                "pid_file": str(pid_file),
                "running": True
            }
        except ProcessLookupError:
            return None
        except PermissionError:
            # 有权限问题但进程存在
            return {
                "pid": pid,
                "pid_file": str(pid_file),
                "running": True
            }
    except:
        return None
