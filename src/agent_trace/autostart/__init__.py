#!/usr/bin/env python3
"""
Auto-start management for Kimi Monitor

Supports:
- macOS: launchd (user level)
- Linux: systemd (user or system level)
- Windows: Windows Service
"""

import os
import sys
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from string import Template


class AutoStartManager:
    """跨平台自启动管理器"""
    
    def __init__(self):
        self.system = platform.system()
        self.project_root = Path(__file__).parent.parent.parent.parent
        self.template_dir = Path(__file__).parent
        self.config = self._get_config()
    
    def _get_config(self) -> Dict[str, str]:
        """获取配置信息"""
        import getpass
        
        # 尝试导入 grp 模块（Unix 特有，Windows 上不存在）
        try:
            import grp
            has_grp = True
        except ImportError:
            has_grp = False
        
        # 获取 Python 路径
        python_path = sys.executable
        
        # 获取项目路径
        working_dir = str(self.project_root)
        
        # 日志目录
        log_dir = str(Path.home() / ".agenttrace" / "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 获取用户名
        user = getpass.getuser()
        
        # 获取组名：Unix/Linux 使用 grp 模块，Windows 使用用户名作为组名
        if has_grp and hasattr(os, 'getgid'):
            try:
                group = grp.getgrgid(os.getgid()).gr_name
            except (KeyError, OSError):
                group = user
        else:
            group = user
        
        # 环境变量（非敏感配置）
        # 注意：敏感信息（API Token等）通过 EnvironmentFile 从 ~/.agenttrace/.env 加载
        env_vars = {
            "PYTHON_PATH": python_path,
            "WORKING_DIR": working_dir,
            "LOG_DIR": log_dir,
            "USER": user,
            "GROUP": group,
            "PYTHONPATH": working_dir,
            # 敏感信息不再直接写入服务配置
            "ENV_FILE_PATH": str(Path.home() / ".agenttrace" / ".env"),
        }
        
        return env_vars
    
    def _ensure_env_file(self) -> bool:
        """确保 .env 文件存在，如果不存在则创建模板"""
        env_dir = Path.home() / ".agenttrace"
        env_file = env_dir / ".env"
        
        # 创建目录
        env_dir.mkdir(parents=True, exist_ok=True)
        
        if not env_file.exists():
            # 创建模板文件
            template_content = """# Agent Trace Environment Configuration
# 请填写你的 CozeLoop API 配置
# 注意：此文件包含敏感信息，请勿共享或提交到版本控制

# CozeLoop API Token（从 CozeLoop 控制台获取）
COZELOOP_API_TOKEN=your_api_token_here

# CozeLoop Workspace ID（从 CozeLoop 控制台获取）
COZELOOP_WORKSPACE_ID=your_workspace_id_here

# CozeLoop API Base URL（可选，默认使用官方地址）
COZELOOP_API_BASE=https://api.coze.cn

# Kimi 会话目录（可选，默认使用系统默认路径）
KIMI_SESSIONS_DIR=

# 轮询间隔（秒，可选）
KIMI_POLL_INTERVAL=2.0

# 日志文件路径（可选）
KIMI_LOG_FILE=
"""
            try:
                with open(env_file, 'w', encoding='utf-8') as f:
                    f.write(template_content)
                # 设置文件权限，仅所有者可读写 (Unix/Linux/macOS)
                if self.system != "Windows":
                    os.chmod(env_file, 0o600)
                print(f"[INFO] 已创建环境变量模板文件: {env_file}")
                print("[WARN] 请先编辑此文件，填写你的 COZELOOP_API_TOKEN 和 COZELOOP_WORKSPACE_ID")
                return False
            except Exception as e:
                print(f"[ERROR] 创建 .env 文件失败: {e}")
                return False
        
        # 检查文件是否包含有效的 API Token
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否有占位符
            if "your_api_token_here" in content or "your_workspace_id_here" in content:
                print(f"[WARN] .env 文件包含未配置的占位符: {env_file}")
                print("[WARN] 请先编辑此文件，填写你的 COZELOOP_API_TOKEN 和 COZELOOP_WORKSPACE_ID")
                return False
            
            # 检查是否有 API Token
            if "COZELOOP_API_TOKEN=" not in content:
                print(f"[WARN] .env 文件缺少 COZELOOP_API_TOKEN: {env_file}")
                return False
            
            return True
        except Exception as e:
            print(f"[ERROR] 读取 .env 文件失败: {e}")
            return False
    
    def install(self) -> bool:
        """安装自启动"""
        # 首先检查/创建 .env 文件
        if not self._ensure_env_file():
            return False
            
        if self.system == "Darwin":
            return self._install_macos()
        elif self.system == "Linux":
            return self._install_linux()
        elif self.system == "Windows":
            return self._install_windows()
        else:
            print(f"Unsupported platform: {self.system}")
            return False
    
    def uninstall(self) -> bool:
        """卸载自启动"""
        if self.system == "Darwin":
            return self._uninstall_macos()
        elif self.system == "Linux":
            return self._uninstall_linux()
        elif self.system == "Windows":
            return self._uninstall_windows()
        else:
            print(f"Unsupported platform: {self.system}")
            return False
    
    def status(self) -> Dict[str, Any]:
        """获取自启动状态"""
        if self.system == "Darwin":
            return self._status_macos()
        elif self.system == "Linux":
            return self._status_linux()
        elif self.system == "Windows":
            return self._status_windows()
        else:
            return {"installed": False, "running": False, "error": f"Unsupported platform: {self.system}"}
    
    # ==================== macOS ====================
    
    def _install_macos(self) -> bool:
        """安装 macOS launchd 服务"""
        try:
            # 读取模板
            template_path = self.template_dir / "macos" / "com.kimicode.monitor.plist.template"
            with open(template_path, 'r') as f:
                template = Template(f.read())
            
            # 填充模板
            plist_content = template.safe_substitute(self.config)
            
            # 写入 LaunchAgents
            launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
            launch_agents_dir.mkdir(parents=True, exist_ok=True)
            
            plist_path = launch_agents_dir / "com.kimicode.monitor.plist"
            with open(plist_path, 'w') as f:
                f.write(plist_content)
            
            # 加载服务
            subprocess.run(["launchctl", "load", str(plist_path)], check=True)
            subprocess.run(["launchctl", "start", "com.kimicode.monitor"], check=False)
            
            print(f"[OK] macOS auto-start installed")
            print(f"     Plist: {plist_path}")
            print(f"     Logs: {self.config['LOG_DIR']}")
            print(f"     Env File: {self.config['ENV_FILE_PATH']}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to install macOS auto-start: {e}")
            return False
    
    def _uninstall_macos(self) -> bool:
        """卸载 macOS launchd 服务"""
        try:
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.kimicode.monitor.plist"
            
            # 停止并卸载
            subprocess.run(["launchctl", "stop", "com.kimicode.monitor"], check=False)
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            
            # 删除 plist
            if plist_path.exists():
                plist_path.unlink()
            
            print("[OK] macOS auto-start uninstalled")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to uninstall macOS auto-start: {e}")
            return False
    
    def _status_macos(self) -> Dict[str, Any]:
        """获取 macOS 服务状态"""
        try:
            plist_path = Path.home() / "Library" / "LaunchAgents" / "com.kimicode.monitor.plist"
            installed = plist_path.exists()
            
            running = False
            if installed:
                result = subprocess.run(
                    ["launchctl", "list", "com.kimicode.monitor"],
                    capture_output=True,
                    text=True
                )
                running = result.returncode == 0 and "PID" in result.stdout
            
            return {
                "installed": installed,
                "running": running,
                "plist_path": str(plist_path) if installed else None
            }
            
        except Exception as e:
            return {"installed": False, "running": False, "error": str(e)}
    
    # ==================== Linux ====================
    
    def _install_linux(self) -> bool:
        """安装 Linux systemd 服务"""
        try:
            # 检查 systemd
            if not shutil.which("systemctl"):
                print("[ERROR] systemd not found")
                return False
            
            # 读取模板
            template_path = self.template_dir / "linux" / "kimi-monitor.service.template"
            with open(template_path, 'r') as f:
                template = Template(f.read())
            
            # 填充模板
            service_content = template.safe_substitute(self.config)
            
            # 确定安装路径（用户级或系统级）
            user_service_dir = Path.home() / ".config" / "systemd" / "user"
            system_service_dir = Path("/etc/systemd/system")
            
            # 优先用户级，如果无法写入系统级
            if os.geteuid() == 0:  # root
                service_dir = system_service_dir
                use_sudo = False
            else:
                user_service_dir.mkdir(parents=True, exist_ok=True)
                service_dir = user_service_dir
                use_sudo = False
            
            service_path = service_dir / "kimi-monitor.service"
            
            # 如果需要 sudo 写入系统级
            if use_sudo:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.service', delete=False) as f:
                    f.write(service_content)
                    temp_path = f.name
                subprocess.run(["sudo", "cp", temp_path, str(service_path)], check=True)
                os.unlink(temp_path)
            else:
                with open(service_path, 'w') as f:
                    f.write(service_content)
            
            # 重载 systemd
            if service_dir == system_service_dir:
                subprocess.run(["systemctl", "daemon-reload"], check=True)
                subprocess.run(["systemctl", "enable", "kimi-monitor"], check=True)
                subprocess.run(["systemctl", "start", "kimi-monitor"], check=True)
            else:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                subprocess.run(["systemctl", "--user", "enable", "kimi-monitor"], check=True)
                subprocess.run(["systemctl", "--user", "start", "kimi-monitor"], check=True)
            
            print(f"[OK] Linux auto-start installed")
            print(f"     Service: {service_path}")
            print(f"     Logs: {self.config['LOG_DIR']}")
            print(f"     Env File: {self.config['ENV_FILE_PATH']}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to install Linux auto-start: {e}")
            return False
    
    def _uninstall_linux(self) -> bool:
        """卸载 Linux systemd 服务"""
        try:
            # 停止服务
            subprocess.run(["systemctl", "--user", "stop", "kimi-monitor"], check=False)
            subprocess.run(["systemctl", "stop", "kimi-monitor"], check=False)
            
            # 禁用服务
            subprocess.run(["systemctl", "--user", "disable", "kimi-monitor"], check=False)
            subprocess.run(["systemctl", "disable", "kimi-monitor"], check=False)
            
            # 删除服务文件
            user_service = Path.home() / ".config" / "systemd" / "user" / "kimi-monitor.service"
            system_service = Path("/etc/systemd/system") / "kimi-monitor.service"
            
            for path in [user_service, system_service]:
                if path.exists():
                    if os.geteuid() != 0 and path == system_service:
                        subprocess.run(["sudo", "rm", str(path)], check=False)
                    else:
                        path.unlink()
            
            # 重载 systemd
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "daemon-reload"], check=False)
            
            print("[OK] Linux auto-start uninstalled")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to uninstall Linux auto-start: {e}")
            return False
    
    def _status_linux(self) -> Dict[str, Any]:
        """获取 Linux 服务状态"""
        try:
            user_service = Path.home() / ".config" / "systemd" / "user" / "kimi-monitor.service"
            system_service = Path("/etc/systemd/system") / "kimi-monitor.service"
            
            installed = user_service.exists() or system_service.exists()
            service_path = user_service if user_service.exists() else system_service
            
            running = False
            if installed:
                result = subprocess.run(
                    ["systemctl", "--user", "is-active", "kimi-monitor"],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    result = subprocess.run(
                        ["systemctl", "is-active", "kimi-monitor"],
                        capture_output=True,
                        text=True
                    )
                running = "active" in result.stdout
            
            return {
                "installed": installed,
                "running": running,
                "service_path": str(service_path) if installed else None
            }
            
        except Exception as e:
            return {"installed": False, "running": False, "error": str(e)}
    
    # ==================== Windows ====================
    
    def _install_windows(self) -> bool:
        """安装 Windows 服务"""
        try:
            # 生成安装脚本
            template_path = self.template_dir / "windows" / "install.bat.template"
            with open(template_path, 'r') as f:
                template = Template(f.read())
            
            script_content = template.safe_substitute(self.config)
            
            # 写入临时脚本
            import tempfile
            script_path = Path(tempfile.gettempdir()) / "agent_trace_install.bat"
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            print(f"[INFO] Windows service installer created: {script_path}")
            print("[INFO] Please run the script as Administrator:")
            print(f"       {script_path}")
            
            # 尝试自动运行（需要管理员权限）
            try:
                subprocess.run([str(script_path)], check=True, shell=True)
                return True
            except:
                return False
            
        except Exception as e:
            print(f"[ERROR] Failed to install Windows auto-start: {e}")
            return False
    
    def _uninstall_windows(self) -> bool:
        """卸载 Windows 服务"""
        try:
            # 生成卸载脚本
            template_path = self.template_dir / "windows" / "uninstall.bat.template"
            with open(template_path, 'r') as f:
                template = Template(f.read())
            
            script_content = template.safe_substitute(self.config)
            
            # 写入临时脚本
            import tempfile
            script_path = Path(tempfile.gettempdir()) / "agent_trace_uninstall.bat"
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            print(f"[INFO] Windows service uninstaller created: {script_path}")
            print("[INFO] Please run the script as Administrator")
            
            try:
                subprocess.run([str(script_path)], check=True, shell=True)
                return True
            except:
                return False
            
        except Exception as e:
            print(f"[ERROR] Failed to uninstall Windows auto-start: {e}")
            return False
    
    def _status_windows(self) -> Dict[str, Any]:
        """获取 Windows 服务状态"""
        try:
            result = subprocess.run(
                ["sc", "query", "KimiMonitor"],
                capture_output=True,
                text=True
            )
            installed = result.returncode == 0
            running = "RUNNING" in result.stdout if installed else False
            
            return {
                "installed": installed,
                "running": running
            }
            
        except Exception as e:
            return {"installed": False, "running": False, "error": str(e)}


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kimi Monitor Auto-Start Manager")
    parser.add_argument("command", choices=["install", "uninstall", "status"], help="Command")
    
    args = parser.parse_args()
    
    manager = AutoStartManager()
    
    if args.command == "install":
        manager.install()
    elif args.command == "uninstall":
        manager.uninstall()
    elif args.command == "status":
        status = manager.status()
        print(f"Platform: {manager.system}")
        print(f"Installed: {status['installed']}")
        print(f"Running: {status['running']}")
        if 'plist_path' in status and status['plist_path']:
            print(f"Plist: {status['plist_path']}")
        if 'service_path' in status and status['service_path']:
            print(f"Service: {status['service_path']}")


if __name__ == "__main__":
    main()
