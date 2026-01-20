import sys
import subprocess
import os
import time
import platform
import shutil
import threading
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction, QIcon

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from gui.main_window import MainWindow

class Launcher:
    def __init__(self, debug_mode=False):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("玲 - 中控中心")
        self.app.setQuitOnLastWindowClosed(False)
        
        # 调试模式标志
        self.debug_mode = debug_mode
        if self.debug_mode:
            print("=" * 60)
            print("调试模式已启用")
            print("=" * 60)
        
        # 记录是否由我们启动了 MongoDB
        self.mongodb_started_by_us = False
        
        # Check and start MongoDB service first
        self.ensure_mongodb_service()
        
        # Initialize MainWindow but don't show it yet
        self.main_window = MainWindow()
        
        # Setup System Tray
        self.setup_tray()
        
        # Live2D Process
        self.live2d_process = None
        self.live2d_java_pid = None  # 记录 Live2D Java 进程的 PID
        self.live2d_started_with_maven = False  # 记录是否使用 Maven 启动
        self.start_live2d()
        
    def ensure_mongodb_service(self):
        """Check if MongoDB is running and start it if necessary."""
        print("检查 MongoDB 状态...")
        if platform.system() != "Windows":
            return

        # 首先检查 MongoDB 进程是否在运行
        if self._is_mongodb_running():
            print("MongoDB 已在运行中")
            self.mongodb_started_by_us = False  # 不是我们启动的
            return

        # 检查是否有 Windows 服务
        names = ["MongoDB", "MongoDB Server", "mongodb"]
        for name in names:
            try:
                status = subprocess.run([
                    "powershell", "-NoProfile", "-Command",
                    f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status"
                ], capture_output=True, text=True, timeout=5)
                
                out = (status.stdout or "").strip()
                if out and out.lower() == "running":
                    print(f"MongoDB 服务 '{name}' 已在运行")
                    self.mongodb_started_by_us = False  # 不是我们启动的
                    return
                elif out and out.lower() != "running":
                    print(f"尝试启动 MongoDB 服务 '{name}'...")
                    try:
                        subprocess.run([
                            "powershell", "-NoProfile", "-Command",
                            f"Start-Service -Name '{name}'"
                        ], capture_output=True, text=True, timeout=15, check=True)
                        time.sleep(2)
                        if self._is_mongodb_running():
                            print(f"MongoDB 服务 '{name}' 启动成功")
                            self.mongodb_started_by_us = False  # 服务启动的，不是我们直接启动的进程
                            return
                    except subprocess.CalledProcessError:
                        print(f"无法启动服务 '{name}'，尝试直接启动进程...")
            except Exception as e:
                continue

        # 如果没有服务或服务启动失败，直接启动 MongoDB 进程
        print("尝试直接启动 MongoDB 进程...")
        if self._start_mongodb_process():
            self.mongodb_started_by_us = True  # 标记为我们启动的

    def _is_mongodb_running(self):
        """检查 MongoDB 是否在运行（通过进程和端口）"""
        try:
            # 检查进程
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mongod.exe"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "mongod.exe" in result.stdout:
                # 再检查端口是否在监听
                port_check = subprocess.run(
                    ["netstat", "-an"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if ":27017" in port_check.stdout and "LISTENING" in port_check.stdout:
                    return True
        except Exception:
            pass
        return False

    def _start_mongodb_process(self):
        """启动 MongoDB 进程"""
        mongodb_path = Path("E:/MongoDB")
        mongod_exe = mongodb_path / "bin" / "mongod.exe"
        config_file = mongodb_path / "mongod.cfg"

        if not mongod_exe.exists():
            print(f"MongoDB 可执行文件不存在: {mongod_exe}")
            return False

        try:
            # 使用 Start-Process 在后台启动，隐藏窗口
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"Start-Process -FilePath '{mongod_exe}' -ArgumentList '--config', '{config_file}' -WindowStyle Hidden"
            ], timeout=10)
            
            # 等待几秒让 MongoDB 启动
            print("等待 MongoDB 启动...")
            for _ in range(10):
                time.sleep(1)
                if self._is_mongodb_running():
                    print("MongoDB 启动成功")
                    return True
            
            print("MongoDB 启动超时，请检查日志文件")
            return False
        except Exception as e:
            print(f"启动 MongoDB 失败: {e}")
            return False

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Set icon (using standard icon as placeholder)
        icon = self.app.style().standardIcon(self.app.style().StandardPixmap.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("玲 - 中控中心")
        
        # Context Menu
        menu = QMenu()
        
        # Open Settings
        action_settings = QAction("打开设置", self.app)
        action_settings.triggered.connect(self.show_settings)
        menu.addAction(action_settings)
        
        # Separator
        menu.addSeparator()
        
        # Exit
        action_exit = QAction("退出", self.app)
        action_exit.triggered.connect(self.quit_app)
        menu.addAction(action_exit)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
    def show_settings(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        
    def start_live2d(self):
        project_root = Path(__file__).parent.absolute()
        live2d_path = project_root / "frontend" / "Live2DPet"
        
        if not live2d_path.exists():
            print(f"Live2D path not found: {live2d_path}")
            return

        cmd = None
        # Try Maven first, then JAR
        if (live2d_path / "pom.xml").exists():
            # Maven
            # Use mvn.cmd on Windows to avoid 'FileNotFoundError'
            mvn_cmd = "mvn.cmd" if sys.platform == "win32" else "mvn"
            
            # Check if mvn is in path
            if shutil.which(mvn_cmd) is None:
                # Fallback to just 'mvn' if 'mvn.cmd' not found (unlikely on valid Windows install but possible)
                if shutil.which("mvn"):
                    mvn_cmd = "mvn"
                else:
                    print("Maven (mvn) not found in PATH.")
                    mvn_cmd = None
            
            if mvn_cmd:
                # 先编译，然后运行（确保代码更改后会自动重新编译）
                cmd = [mvn_cmd, "-q", "-DskipTests", "compile", "exec:java"]
        
        # Fallback to JAR if Maven not available or not found
        if not cmd:
            # Check for JAR
            jar_path = live2d_path / "target" / "live2d-pet-1.0.0.jar"
            if jar_path.exists():
                cmd = ["java", "-jar", str(jar_path)]
            else:
                print("Live2D JAR not found and Maven not available.")
        
        if cmd:
            try:
                if self.debug_mode:
                    print(f"[DEBUG] 启动命令: {' '.join(cmd)}")
                    print(f"[DEBUG] 工作目录: {live2d_path}")
                else:
                    print(f"Starting Live2D with command: {' '.join(cmd)}")
                
                # 调试模式下不隐藏控制台窗口
                creation_flags = 0 if self.debug_mode else (subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                
                # 记录是否使用 Maven 启动
                self.live2d_started_with_maven = mvn_cmd and mvn_cmd in cmd[0] if cmd else False
                
                if self.debug_mode:
                    # 调试模式：实时显示所有输出
                    self.live2d_process = subprocess.Popen(
                        cmd,
                        cwd=live2d_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                        text=True,
                        encoding='utf-8',
                        errors='replace',  # 替换无法解码的字符
                        creationflags=creation_flags,
                        bufsize=1  # 行缓冲
                    )
                    print(f"[DEBUG] Live2D 进程已启动，PID: {self.live2d_process.pid}")
                    print("[DEBUG] 开始实时输出（按 Ctrl+C 停止）...")
                    print("-" * 60)
                    
                    # 启动线程实时读取输出
                    def read_output():
                        try:
                            while True:
                                line = self.live2d_process.stdout.readline()
                                if not line:
                                    # 进程已结束
                                    if self.live2d_process.poll() is not None:
                                        print(f"[DEBUG] Live2D 进程已退出，退出码: {self.live2d_process.returncode}")
                                        break
                                    continue
                                print(f"[Live2D] {line.rstrip()}")
                        except Exception as e:
                            print(f"[DEBUG] 读取输出时出错: {e}")
                        finally:
                            # 读取剩余输出
                            try:
                                remaining = self.live2d_process.stdout.read()
                                if remaining:
                                    print(f"[DEBUG] 剩余输出:\n{remaining}")
                            except:
                                pass
                    
                    output_thread = threading.Thread(target=read_output, daemon=True)
                    output_thread.start()
                    
                    # 同时启动一个监控线程，定期检查进程状态
                    def monitor_process():
                        time.sleep(3)  # 等待3秒
                        if self.live2d_process.poll() is not None:
                            print(f"[DEBUG] 警告：Live2D 进程在启动后立即退出，退出码: {self.live2d_process.returncode}")
                            # 尝试读取 stderr（虽然已经合并到 stdout，但以防万一）
                            try:
                                if hasattr(self.live2d_process, 'stderr') and self.live2d_process.stderr:
                                    stderr_content = self.live2d_process.stderr.read()
                                    if stderr_content:
                                        print(f"[DEBUG] 错误输出:\n{stderr_content}")
                            except:
                                pass
                    
                    monitor_thread = threading.Thread(target=monitor_process, daemon=True)
                    monitor_thread.start()
                else:
                    # 正常模式：静默运行
                    self.live2d_process = subprocess.Popen(
                        cmd,
                        cwd=live2d_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding='utf-8',
                        errors='ignore',
                        creationflags=creation_flags
                    )
                    print(f"Live2D started with PID: {self.live2d_process.pid}")
                
                # 如果使用 Maven 启动，等待并查找 Java 子进程
                if self.live2d_started_with_maven:
                    wait_time = 5 if self.debug_mode else 3
                    if self.debug_mode:
                        print(f"[DEBUG] 等待 {wait_time} 秒让 Maven 启动 Java 进程...")
                    time.sleep(wait_time)
                    self._find_live2d_java_process()
                    
                # 在调试模式下，检查进程是否还在运行
                if self.debug_mode:
                    time.sleep(2)
                    if self.live2d_process.poll() is not None:
                        print(f"[DEBUG] 警告：Live2D 进程已退出，退出码: {self.live2d_process.returncode}")
                        # 尝试读取剩余的错误信息
                        try:
                            if self.live2d_process.stdout:
                                remaining_output = self.live2d_process.stdout.read()
                                if remaining_output:
                                    print(f"[DEBUG] 剩余输出:\n{remaining_output}")
                        except:
                            pass
            except Exception as e:
                print(f"Failed to start Live2D: {e}")
        else:
            print("No valid launch method found for Live2D.")

    def quit_app(self):
        """退出应用，关闭所有相关进程"""
        print("正在关闭所有相关进程...")
        
        # 关闭 Live2D 进程和窗口
        self._stop_live2d_process()
        
        # 关闭 MongoDB 进程（如果是由我们启动的）
        if self.mongodb_started_by_us:
            print("正在关闭 MongoDB...")
            self._stop_mongodb_process()
        
        # 关闭主窗口
        if self.main_window:
            self.main_window.close()
        
        print("正在退出应用...")
        self.app.quit()
    
    def _find_live2d_java_process(self):
        """查找 Live2D 的 Java 进程 PID"""
        if platform.system() != "Windows":
            return
        
        try:
            project_root = Path(__file__).parent.absolute()
            live2d_path = project_root / "frontend" / "Live2DPet"
            
            # 使用 wmic 查找 Java 进程，包含 Live2DPet 路径
            wmic_result = subprocess.run(
                ["wmic", "process", "where", "name='java.exe'", "get", "ProcessId,CommandLine,ParentProcessId"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=5
            )
            
            # 查找与 Live2D 相关的 Java 进程
            if wmic_result.stdout:
                for line in wmic_result.stdout.split('\n'):
                    if 'Live2DPet' in line or 'live2d-pet' in line.lower():
                        # 提取 PID
                        parts = line.split()
                        for part in parts:
                            if part.isdigit() and len(part) > 2:  # PID 通常是 4 位以上数字
                                # 检查是否是父进程的子进程
                                if self.live2d_process and str(self.live2d_process.pid) in line:
                                    self.live2d_java_pid = part
                                    print(f"找到 Live2D Java 进程 PID: {self.live2d_java_pid}")
                                    return
                                # 或者直接通过路径匹配
                                elif str(live2d_path).replace('\\', '/') in line.replace('\\', '/'):
                                    self.live2d_java_pid = part
                                    print(f"找到 Live2D Java 进程 PID: {self.live2d_java_pid}")
                                    return
        except Exception as e:
            print(f"查找 Live2D Java 进程时出错: {e}")
    
    def _stop_live2d_process(self):
        """停止 Live2D 进程和窗口"""
        print("正在关闭 Live2D...")
        
        if platform.system() != "Windows":
            # 非 Windows 系统，直接关闭主进程
            if self.live2d_process:
                try:
                    self.live2d_process.terminate()
                    try:
                        self.live2d_process.wait(timeout=2)
                        print("Live2D 已关闭")
                    except subprocess.TimeoutExpired:
                        self.live2d_process.kill()
                        print("Live2D 已强制关闭")
                except Exception as e:
                    print(f"关闭 Live2D 时出错: {e}")
            return
        
        # Windows 系统：优先通过窗口标题关闭（最可靠）
        try:
            # 方法1：通过窗口标题关闭（GLFW 窗口标题是 "Live2D Pet"）
            result = subprocess.run([
                "powershell", "-NoProfile", "-Command",
                "$processes = Get-Process | Where-Object {$_.MainWindowTitle -like '*Live2D*' -or $_.MainWindowTitle -like '*Pet*'}; if ($processes) { $processes | Stop-Process -Force; Write-Host '已通过窗口标题关闭 Live2D' } else { Write-Host '未找到 Live2D 窗口' }"
            ], timeout=5, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            if result.stdout and "已通过窗口标题关闭" in result.stdout:
                print(result.stdout.strip())
                # 等待一下确保窗口关闭
                time.sleep(0.5)
            elif result.stdout and "未找到 Live2D 窗口" in result.stdout:
                print("未找到 Live2D 窗口（可能已关闭）")
        except Exception as e:
            print(f"通过窗口标题关闭时出错: {e}")
        
        # 方法2：如果记录了 Java 进程 PID，直接关闭
        if self.live2d_java_pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(self.live2d_java_pid)],
                    capture_output=True,
                    timeout=5
                )
                print(f"已关闭 Live2D Java 进程 (PID: {self.live2d_java_pid})")
            except Exception as e:
                print(f"关闭 Java 进程时出错: {e}")
        
        # 方法3：查找并关闭所有相关的 Java 进程
        try:
            project_root = Path(__file__).parent.absolute()
            live2d_path = project_root / "frontend" / "Live2DPet"
            
            wmic_result = subprocess.run(
                ["wmic", "process", "where", "name='java.exe'", "get", "ProcessId,CommandLine"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=5
            )
            
            java_pids = []
            if wmic_result.stdout:
                for line in wmic_result.stdout.split('\n'):
                    if 'Live2DPet' in line or 'live2d-pet' in line.lower() or 'exec:java' in line:
                        parts = line.split()
                        for part in parts:
                            if part.isdigit() and len(part) > 2:
                                java_pids.append(part)
                                break
            
            if java_pids:
                for pid in java_pids:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid],
                            capture_output=True,
                            timeout=5
                        )
                        print(f"已关闭 Live2D Java 进程 (PID: {pid})")
                    except Exception:
                        pass
        except Exception as e:
            print(f"查找 Java 进程时出错: {e}")
        
        # 方法4：关闭 Maven 进程（如果使用 Maven 启动）
        if self.live2d_process:
            try:
                self.live2d_process.terminate()
                try:
                    self.live2d_process.wait(timeout=1)
                    print("Live2D Maven 进程已关闭")
                except subprocess.TimeoutExpired:
                    self.live2d_process.kill()
                    print("Live2D Maven 进程已强制关闭")
            except Exception as e:
                print(f"关闭 Maven 进程时出错: {e}")
        
        print("Live2D 关闭完成")
    
    def _stop_mongodb_process(self):
        """停止 MongoDB 进程"""
        try:
            # 查找并关闭 mongod.exe 进程
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq mongod.exe", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if "mongod.exe" in result.stdout:
                # 使用 taskkill 关闭 MongoDB
                subprocess.run(
                    ["taskkill", "/F", "/IM", "mongod.exe"],
                    capture_output=True,
                    timeout=10
                )
                print("MongoDB 已关闭")
            else:
                print("MongoDB 进程未找到")
        except Exception as e:
            print(f"关闭 MongoDB 时出错: {e}")
        
    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    # 检查是否启用调试模式（通过命令行参数 --debug 或 -d）
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    
    launcher = Launcher(debug_mode=debug_mode)
    launcher.run()
