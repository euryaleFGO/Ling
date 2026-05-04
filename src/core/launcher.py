import sys
import subprocess
import os
import time
import platform
import shutil
import threading
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt

# Add project root to path
project_root = Path(__file__).parent.parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from core.log import log, set_debug
from gui.main_window import MainWindow
from core.settings import AppSettings

class Launcher:
    def __init__(self, debug_mode=False, enable_conversation=True, text_only=False, asr_device="auto"):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("玲 - 中控中心")
        self.app.setQuitOnLastWindowClosed(False)
        
        # 调试模式标志
        self.debug_mode = debug_mode
        self.enable_conversation = enable_conversation
        self.text_only = text_only  # 文字输入模式（不使用麦克风）

        # 从配置文件读取文字输入模式（CLI 参数优先）
        if not text_only:
            try:
                from core.config_manager import get_config_manager
                cfg = get_config_manager().config
                if cfg.general.use_text_input:
                    self.text_only = True
                    log.info("[配置] 从配置文件启用文字输入模式")
            except Exception:
                pass
        self.asr_device = asr_device
        
        # 设置全局日志级别
        set_debug(debug_mode)
        
        if self.debug_mode:
            log.info("=" * 60)
            log.info("调试模式已启用")
            log.info("=" * 60)
        
        # 记录是否由我们启动了 MongoDB
        self.mongodb_started_by_us = False
        
        # 对话管理器
        self._conversation_manager = None
        self._conversation_thread = None
        
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

        # 消息服务（Live2D 文本框通过轮询此服务获取 AI 回复）
        self._message_server = None
        self._message_server_thread = None
        self._start_message_server()

        # 启动对话系统
        if self.enable_conversation:
            self.start_conversation_system()

        # Self-healing system initialization
        self._heal_event_bus = None
        self._heal_backup = None
        self._heal_rate_limiter = None
        self._heal_emergency_stop = None
        self._heal_error_handler = None
        self._heal_monitor = None
        try:
            from backend.llm.self_heal import (
                EventBus, HealthMonitor, ErrorHandler, BackupManager,
                RateLimiter, EmergencyStop, LogWatchCheck, ServiceHealthCheck,
                ConfigValidateCheck, PerformanceCheck, RetryStrategy,
                ServiceRestartStrategy, ConfigRollbackStrategy, NotifyUserStrategy,
            )

            # Create components
            self._heal_event_bus = EventBus()
            self._heal_backup = BackupManager(backup_dir="data/backups/snapshots")
            self._heal_rate_limiter = RateLimiter(max_per_window=5, window_seconds=300)
            self._heal_emergency_stop = EmergencyStop()

            # Create error handler with strategy chain
            self._heal_error_handler = ErrorHandler(
                event_bus=self._heal_event_bus,
                backup_manager=self._heal_backup,
                rate_limiter=self._heal_rate_limiter,
                emergency_stop=self._heal_emergency_stop,
            )
            self._heal_error_handler.add_strategy(RetryStrategy(max_retries=3))
            self._heal_error_handler.add_strategy(ServiceRestartStrategy())
            self._heal_error_handler.add_strategy(ConfigRollbackStrategy(self._heal_backup))
            self._heal_error_handler.add_strategy(NotifyUserStrategy())

            # Create health monitor with checks
            self._heal_monitor = HealthMonitor(self._heal_event_bus)
            self._heal_monitor.register_check(LogWatchCheck(log_dir="logs"))
            self._heal_monitor.register_check(ServiceHealthCheck())
            self._heal_monitor.register_check(ConfigValidateCheck())
            self._heal_monitor.register_check(PerformanceCheck())

            # Start background monitoring
            self._heal_monitor.start()
            log.debug("自修复系统已启动")
        except Exception as e:
            log.error(f"自修复系统初始化失败: {e}")
        
    def ensure_mongodb_service(self):
        """Check if MongoDB is running and start it if necessary."""
        log.debug("检查 MongoDB 状态...")
        if platform.system() != "Windows":
            return

        # 首先检查 MongoDB 进程是否在运行
        if self._is_mongodb_running():
            log.debug("MongoDB 已在运行中")
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
                    log.debug(f"MongoDB 服务 '{name}' 已在运行")
                    self.mongodb_started_by_us = False  # 不是我们启动的
                    return
                elif out and out.lower() != "running":
                    log.debug(f"尝试启动 MongoDB 服务 '{name}'...")
                    try:
                        subprocess.run([
                            "powershell", "-NoProfile", "-Command",
                            f"Start-Service -Name '{name}'"
                        ], capture_output=True, text=True, timeout=15, check=True)
                        time.sleep(2)
                        if self._is_mongodb_running():
                            log.debug(f"MongoDB 服务 '{name}' 启动成功")
                            self.mongodb_started_by_us = False  # 服务启动的，不是我们直接启动的进程
                            return
                    except subprocess.CalledProcessError:
                        log.debug(f"无法启动服务 '{name}'，尝试直接启动进程...")
            except Exception as e:
                continue

        # 如果没有服务或服务启动失败，直接启动 MongoDB 进程
        log.debug("尝试直接启动 MongoDB 进程...")
        if self._start_mongodb_process():
            self.mongodb_started_by_us = True  # 标记为我们启动的

    def _is_mongodb_running(self):
        """检查 MongoDB 是否在运行（通过进程和端口）"""
        try:
            s = AppSettings.load()
            # 仅当使用本地默认端口时才做端口监听判断（避免误判远程/自定义端口）
            expected_port = 27017
            try:
                if s.mongodb_uri:
                    # 简单解析 mongodb://host:port
                    if "://" in s.mongodb_uri:
                        tail = s.mongodb_uri.split("://", 1)[1]
                        host_port = tail.split("/", 1)[0]
                        if ":" in host_port:
                            expected_port = int(host_port.rsplit(":", 1)[1])
            except Exception:
                expected_port = 27017

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
                if f":{expected_port}" in port_check.stdout and "LISTENING" in port_check.stdout:
                    return True
        except Exception:
            pass
        return False

    def _start_mongodb_process(self):
        """启动 MongoDB 进程"""
        # 不再硬编码本机路径：允许用户通过环境变量指定 mongod 与配置
        mongod_exe_env = os.environ.get("MONGOD_EXE", "").strip()
        mongod_cfg_env = os.environ.get("MONGOD_CFG", "").strip()
        if not mongod_exe_env:
            log.error("未设置 MONGOD_EXE，无法直接启动 MongoDB 进程；请先安装并启动 MongoDB 服务，或设置该环境变量。")
            return False

        mongod_exe = Path(mongod_exe_env)
        config_file = Path(mongod_cfg_env) if mongod_cfg_env else None

        if not mongod_exe.exists():
            log.error(f"MongoDB 可执行文件不存在: {mongod_exe}")
            return False

        try:
            # 使用 Start-Process 在后台启动，隐藏窗口
            if config_file and config_file.exists():
                arg = f"Start-Process -FilePath '{mongod_exe}' -ArgumentList '--config', '{config_file}' -WindowStyle Hidden"
            else:
                arg = f"Start-Process -FilePath '{mongod_exe}' -WindowStyle Hidden"
            subprocess.run(["powershell", "-NoProfile", "-Command", arg], timeout=10)
            
            # 等待几秒让 MongoDB 启动
            log.debug("等待 MongoDB 启动...")
            for _ in range(10):
                time.sleep(1)
                if self._is_mongodb_running():
                    log.debug("MongoDB 启动成功")
                    return True
            
            log.error("MongoDB 启动超时，请检查日志文件")
            return False
        except Exception as e:
            log.error(f"启动 MongoDB 失败: {e}")
            return False

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Set icon (using standard icon as placeholder)
        icon = self.app.style().standardIcon(self.app.style().StandardPixmap.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("玲 - 中控中心")
        
        # Context Menu
        menu = QMenu()
        
        # 对话控制
        self.action_pause = QAction("暂停对话", self.app)
        self.action_pause.triggered.connect(self.toggle_conversation)
        self.action_pause.setCheckable(True)
        menu.addAction(self.action_pause)

        # 文字输入
        self.action_text_input = QAction("文字输入", self.app)
        self.action_text_input.triggered.connect(self.show_text_input_dialog)
        menu.addAction(self.action_text_input)

        menu.addSeparator()
        
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
    
    def start_conversation_system(self):
        """启动对话系统（ASR + Agent + TTS）- 使用异步版本"""
        log.debug("\n" + "=" * 50)
        log.debug("正在启动异步对话系统...")
        log.debug("=" * 50)
        
        def run_conversation():
            try:
                import asyncio
                from core.conversation_manager_async import AsyncConversationManager, ConversationConfig
                
                config = ConversationConfig(
                    user_id=os.environ.get("LIYING_USER_ID", "default_user"),
                    use_vad=True,
                    silence_duration=0.55,
                    asr_device=self.asr_device,
                    tts_remote_url=os.environ.get("LIYING_TTS_REMOTE_URL") or None,
                    tts_spk_id=os.environ.get("LIYING_TTS_SPK_ID", "玲"),
                    use_text_input=self.text_only,  # 文字输入模式
                    # 异步优化配置
                    enable_barge_in=True,  # 启用打断功能
                    tts_enable_cache=True,  # 启用 TTS 缓存
                    tts_cache_size=100,  # 缓存大小
                    asr_stream_profile="balanced",  # ASR 流式配置（balanced/low_latency/accuracy）
                )
                
                self._conversation_manager = AsyncConversationManager(config)

                # 注册 user_text handler（WebSocket 来源的文字输入）
                if self.text_only and self._message_server:
                    self._message_server.set_user_text_handler(
                        self._conversation_manager.submit_user_text
                    )

                # 情绪 → Live2D 动作映射（Agent 根据 LLM 情绪自主触发）
                EMOTION_TO_MOTION = {
                    "joy": "Tap@Body",      # 开心 → 挥手/抬手
                    "surprise": "Tap",      # 惊讶 → Tap
                    "anger": "Flick",       # 生气 → 快速挥手
                    "sadness": "Idle",      # 悲伤 → 保持空闲（不触发额外动作）
                    "shy": "Tap@Body",      # 害羞 → 轻触身体
                    "think": "Idle",        # 思考 → 不触发
                }

                def on_subtitle(text, is_final, emotion="neutral"):
                    """AI 字幕回调 → 通过 WebSocket 发送给 Live2D"""
                    try:
                        from core.message_server import send_message, send_motion
                        send_message(text, emotion=emotion, is_final=is_final)
                        # 最终字幕时，根据情绪触发对应动作（仅非 neutral）
                        if is_final and emotion and emotion != "neutral":
                            motion = EMOTION_TO_MOTION.get(emotion)
                            if motion and motion != "Idle":
                                send_motion(motion)
                    except Exception:
                        pass
                
                def on_audio_rms(rms):
                    """TTS 音频 RMS 回调 → 驱动 Live2D 嘴型同步（Fallback）"""
                    try:
                        from core.message_server import send_audio_rms
                        send_audio_rms(rms)
                    except Exception:
                        pass
                
                def on_viseme(openY, form):
                    """TTS Viseme 回调 → Rhubarb 精确口型同步"""
                    try:
                        from core.message_server import send_viseme
                        send_viseme(openY, form)
                    except Exception:
                        pass

                def on_state_change(state):
                    """对话状态变化 → 供 Live2D 做空闲时自动动作等"""
                    try:
                        from core.message_server import send_state
                        send_state(state.value)
                    except Exception:
                        pass

                def on_exit_requested(reason: str):
                    """对话请求退出应用（在当前播报结束后触发）"""
                    log.info(f"收到对话退出请求: {reason}")
                    self.quit_app()
                
                self._conversation_manager.set_callbacks(
                    on_subtitle=on_subtitle,
                    on_audio_rms=on_audio_rms,
                    on_viseme=on_viseme,
                    on_state_change=on_state_change,
                    on_exit_requested=on_exit_requested,
                )
                
                # 初始化对话管理器
                self._conversation_manager.initialize()
                
                # 创建新的事件循环并运行异步对话系统
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._conversation_manager.run_async())
                finally:
                    loop.close()
                
            except Exception as e:
                log.error(f"对话系统启动失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 在独立线程运行对话系统
        self._conversation_thread = threading.Thread(
            target=run_conversation,
            daemon=True,
            name="ConversationThread"
        )
        self._conversation_thread.start()
        log.debug("对话系统已在后台启动")
    
    def toggle_conversation(self):
        """暂停/恢复对话"""
        if self._conversation_manager:
            if self.action_pause.isChecked():
                # 暂停 - 异步版本使用 cancel_current_turn
                if hasattr(self._conversation_manager, 'cancel_current_turn'):
                    import asyncio
                    # 在事件循环中取消当前 turn
                    try:
                        # 获取事件循环：优先使用 _loop，否则尝试获取运行中的循环
                        loop = None
                        if hasattr(self._conversation_manager, '_loop'):
                            loop = self._conversation_manager._loop
                        else:
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                loop = asyncio.get_event_loop()
                        asyncio.run_coroutine_threadsafe(
                            self._conversation_manager.cancel_current_turn(),
                            loop
                        )
                    except Exception as e:
                        log.debug(f"取消对话时出错: {e}")
                log.debug("对话已暂停")
            else:
                # 恢复 - 异步版本会自动恢复
                log.debug("对话已恢复")
    
    def stop_conversation_system(self):
        """停止对话系统"""
        if self._conversation_manager:
            log.debug("正在停止异步对话系统...")
            # 注销 user_text handler
            if self._message_server:
                self._message_server.clear_user_text_handler()
            # 异步版本使用 stop_sync 方法（同步版本）
            if hasattr(self._conversation_manager, 'stop_sync'):
                self._conversation_manager.stop_sync()
            elif hasattr(self._conversation_manager, 'stop'):
                self._conversation_manager.stop()
            self._conversation_manager = None
        
    def show_settings(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def show_text_input_dialog(self):
        """显示文字输入对话框"""
        if self._conversation_manager is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "提示", "对话系统未启动，请先启动对话系统。")
            return
        dlg = TextInputDialog(self._conversation_manager, parent=None)
        dlg.show()
        
    def start_live2d(self):
        project_root = Path(__file__).parent.parent.parent
        live2d_path = project_root / "src" / "frontend" / "live2d"
        
        if not live2d_path.exists():
            log.error(f"Live2D path not found: {live2d_path}")
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
                    log.debug("Maven (mvn) not found in PATH.")
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
                log.error("Live2D JAR not found and Maven not available.")
        
        if cmd:
            try:
                log.debug(f"Live2D 启动命令: {' '.join(cmd)}")
                log.debug(f"Live2D 工作目录: {live2d_path}")
                
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
                    log.debug(f"Live2D 进程已启动，PID: {self.live2d_process.pid}")
                    log.debug("开始实时输出（按 Ctrl+C 停止）...")
                    log.debug("-" * 60)
                    
                    # 启动线程实时读取输出
                    def read_output():
                        try:
                            while True:
                                line = self.live2d_process.stdout.readline()
                                if not line:
                                    # 进程已结束
                                    if self.live2d_process.poll() is not None:
                                        log.debug(f"Live2D 进程已退出，退出码: {self.live2d_process.returncode}")
                                        break
                                    continue
                                print(f"[Live2D] {line.rstrip()}")
                        except Exception as e:
                            log.debug(f"读取输出时出错: {e}")
                        finally:
                            # 读取剩余输出
                            try:
                                remaining = self.live2d_process.stdout.read()
                                if remaining:
                                    log.debug(f"剩余输出:\n{remaining}")
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
                    # 正常模式：后台读取 stderr，闪退时能在终端看到 Java/OpenGL 报错
                    self.live2d_process = subprocess.Popen(
                        cmd,
                        cwd=live2d_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        creationflags=creation_flags,
                        bufsize=1,
                    )
                    log.debug(f"Live2D started with PID: {self.live2d_process.pid}")

                    def _read_live2d_output():
                        try:
                            while self.live2d_process and self.live2d_process.stdout:
                                line = self.live2d_process.stdout.readline()
                                if not line and self.live2d_process.poll() is not None:
                                    break
                                if line and line.strip():
                                    log.debug(f"[Live2D] {line.rstrip()}")
                        except Exception:
                            pass

                    _t = threading.Thread(target=_read_live2d_output, daemon=True, name="Live2D-Output")
                    _t.start()

                # 如果使用 Maven 启动，等待并查找 Java 子进程
                if self.live2d_started_with_maven:
                    wait_time = 5 if self.debug_mode else 3
                    log.debug(f"等待 {wait_time} 秒让 Maven 启动 Java 进程...")
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
                log.error(f"Failed to start Live2D: {e}")
        else:
            log.error("No valid launch method found for Live2D.")

    def _start_message_server(self):
        """后台启动 WebSocket 消息服务（端口 8765），供 Live2D 前端实时接收 AI 回复"""
        try:
            from core.message_server import create_server
            s = AppSettings.load()
            self._message_server = create_server(s.ws_port, host=s.ws_host)
            self._message_server_thread = threading.Thread(
                target=self._message_server.serve_forever,
                daemon=True,
                name="WebSocketServerThread",
            )
            self._message_server_thread.start()
            log.debug(f"消息服务(WebSocket)已启动: ws://{self._message_server.host}:{self._message_server.port}")
        except Exception as e:
            log.error(f"消息服务启动失败: {e}")

    def _stop_message_server(self):
        """关闭 WebSocket 消息服务"""
        if self._message_server is None:
            return
        try:
            self._message_server.stop()
            log.debug("消息服务已关闭")
        except Exception as e:
            log.debug(f"关闭消息服务时出错: {e}")
        self._message_server = None
        self._message_server_thread = None

    def quit_app(self):
        """退出应用，关闭所有相关进程"""
        log.info("正在关闭...")

        # Stop self-healing monitor
        if hasattr(self, '_heal_monitor') and self._heal_monitor is not None:
            try:
                self._heal_monitor.stop()
                log.debug("自修复监控已停止")
            except Exception as e:
                log.debug(f"停止自修复监控时出错: {e}")

        # 先关闭消息服务
        self._stop_message_server()

        # 关闭对话系统
        self.stop_conversation_system()

        # 关闭 Live2D 进程和窗口
        self._stop_live2d_process()

        # 关闭 MongoDB 进程（如果是由我们启动的）
        if self.mongodb_started_by_us:
            log.debug("正在关闭 MongoDB...")
            self._stop_mongodb_process()
        
        # 关闭主窗口
        if self.main_window:
            self.main_window.close()
        
        log.debug("正在退出应用...")
        self.app.quit()
    
    def _find_live2d_java_process(self):
        """查找 Live2D 的 Java 进程 PID"""
        if platform.system() != "Windows":
            return
        
        try:
            project_root = Path(__file__).parent.parent.parent
            live2d_path = project_root / "src" / "frontend" / "live2d"
            
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
                                    log.debug(f"找到 Live2D Java 进程 PID: {self.live2d_java_pid}")
                                    return
                                # 或者直接通过路径匹配
                                elif str(live2d_path).replace('\\', '/') in line.replace('\\', '/'):
                                    self.live2d_java_pid = part
                                    log.debug(f"找到 Live2D Java 进程 PID: {self.live2d_java_pid}")
                                    return
        except Exception as e:
            log.debug(f"查找 Live2D Java 进程时出错: {e}")
    
    def _stop_live2d_process(self):
        """停止 Live2D 进程和窗口"""
        log.debug("正在关闭 Live2D...")
        
        if platform.system() != "Windows":
            # 非 Windows 系统，直接关闭主进程
            if self.live2d_process:
                try:
                    self.live2d_process.terminate()
                    try:
                        self.live2d_process.wait(timeout=2)
                        log.debug("Live2D 已关闭")
                    except subprocess.TimeoutExpired:
                        self.live2d_process.kill()
                        log.debug("Live2D 已强制关闭")
                except Exception as e:
                    log.debug(f"关闭 Live2D 时出错: {e}")
            return
        
        # Windows 系统：优先通过窗口标题关闭（最可靠）
        try:
            # 方法1：通过窗口标题关闭（GLFW 窗口标题是 "Live2D Pet"）
            result = subprocess.run([
                "powershell", "-NoProfile", "-Command",
                "$processes = Get-Process | Where-Object {$_.MainWindowTitle -like '*Live2D*' -or $_.MainWindowTitle -like '*Pet*'}; if ($processes) { $processes | Stop-Process -Force; Write-Host '已通过窗口标题关闭 Live2D' } else { Write-Host '未找到 Live2D 窗口' }"
            ], timeout=5, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            if result.stdout and "已通过窗口标题关闭" in result.stdout:
                log.debug(result.stdout.strip())
                # 等待一下确保窗口关闭
                time.sleep(0.5)
            elif result.stdout and "未找到 Live2D 窗口" in result.stdout:
                log.debug("未找到 Live2D 窗口（可能已关闭）")
        except Exception as e:
            log.debug(f"通过窗口标题关闭时出错: {e}")
        
        # 方法2：如果记录了 Java 进程 PID，直接关闭
        if self.live2d_java_pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(self.live2d_java_pid)],
                    capture_output=True,
                    timeout=5
                )
                log.debug(f"已关闭 Live2D Java 进程 (PID: {self.live2d_java_pid})")
            except Exception as e:
                log.debug(f"关闭 Java 进程时出错: {e}")
        
        # 方法3：查找并关闭所有相关的 Java 进程
        try:
            project_root = Path(__file__).parent.parent.parent
            live2d_path = project_root / "src" / "frontend" / "live2d"
            
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
                        log.debug(f"已关闭 Live2D Java 进程 (PID: {pid})")
                    except Exception:
                        pass
        except Exception as e:
            log.debug(f"查找 Java 进程时出错: {e}")
        
        # 方法4：关闭 Maven 进程（如果使用 Maven 启动）
        if self.live2d_process:
            try:
                self.live2d_process.terminate()
                try:
                    self.live2d_process.wait(timeout=1)
                    log.debug("Live2D Maven 进程已关闭")
                except subprocess.TimeoutExpired:
                    self.live2d_process.kill()
                    log.debug("Live2D Maven 进程已强制关闭")
            except Exception as e:
                log.debug(f"关闭 Maven 进程时出错: {e}")
        
        log.debug("Live2D 关闭完成")
    
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
                log.debug("MongoDB 已关闭")
            else:
                log.debug("MongoDB 进程未找到")
        except Exception as e:
            log.debug(f"关闭 MongoDB 时出错: {e}")
        
    def run(self):
        sys.exit(self.app.exec())


class TextInputDialog(QDialog):
    """文字输入对话框 — 可拖拽、置顶、Enter 发送"""

    def __init__(self, conversation_manager, parent=None):
        super().__init__(parent)
        self._conv = conversation_manager
        self.setWindowTitle("文字输入")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(420, 60)
        self.resize(420, 60)

        # 内容容器（圆角半透明背景）
        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet("""
            #container {
                background-color: rgba(30, 30, 30, 220);
                border-radius: 14px;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("输入文字，Enter 发送，Shift+Enter 换行")
        self.text_edit.setMaximumHeight(40)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: #e0e0e0;
                border: none;
                font-size: 14px;
                selection-background-color: #43a047;
            }
        """)
        self.text_edit.installEventFilter(self)
        layout.addWidget(self.text_edit, 1)

        send_btn = QPushButton("发送")
        send_btn.setFixedSize(60, 34)
        send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #4caf50, stop:1 #43a047);
                color: white; border: none; border-radius: 8px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #66bb6a, stop:1 #4caf50);
            }
        """)
        send_btn.clicked.connect(self._send)
        layout.addWidget(send_btn)

        # 初始位置：屏幕底部居中
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width() // 2 - 210, geo.height() - 120)

        # 拖拽支持
        self._drag_pos = None

    def eventFilter(self, obj, event):
        if obj is self.text_edit and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False  # Shift+Enter 换行
                self._send()
                return True
        return super().eventFilter(obj, event)

    def _send(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            return
        if self._conv:
            self._conv.submit_user_text(text)
        self.text_edit.clear()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

if __name__ == "__main__":
    # 检查是否启用调试模式（通过命令行参数 --debug 或 -d）
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    
    launcher = Launcher(debug_mode=debug_mode)
    launcher.run()
