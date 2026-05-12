# -*- coding: utf-8 -*-
"""
SSH 端口转发隧道
通过 paramiko 建立 SSH 隧道，将远程服务映射到本地端口
"""
import os
import socket
import threading
import logging
import atexit
import time
from typing import Optional

logger = logging.getLogger(__name__)

_tunnel_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_ssh_client = None


def _forward_port(transport, local_port: int, remote_host: str, remote_port: int):
    """在 transport 上建立一条端口转发。"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1)
    server.bind(("127.0.0.1", local_port))
    server.listen(5)
    logger.info(f"[SSH隧道] 监听 127.0.0.1:{local_port} -> {remote_host}:{remote_port}")

    while not _stop_event.is_set():
        try:
            client, _ = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            chan = transport.open_channel(
                "direct-tcpip",
                (remote_host, remote_port),
                client.getpeername(),
            )
        except Exception:
            client.close()
            continue
        if chan is None:
            client.close()
            continue
        t = threading.Thread(target=_pipe, args=(client, chan), daemon=True)
        t.start()
        t2 = threading.Thread(target=_pipe, args=(chan, client), daemon=True)
        t2.start()

    server.close()


def _pipe(src, dst):
    """双向数据管道中的一条方向。Each pipe only closes its source end."""
    try:
        while not _stop_event.is_set():
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except (OSError, EOFError):
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass


def _tunnel_worker(host: str, port: int, username: str, password: str,
                   forwards: list, ready_event: threading.Event):
    """SSH 隧道后台线程（含指数退避重连）。"""
    global _ssh_client
    try:
        import paramiko
    except ImportError:
        logger.error("[SSH隧道] paramiko 未安装，请运行 pip install paramiko")
        ready_event.set()
        return

    retries = 0
    max_retries = 5

    while retries < max_retries and not _stop_event.is_set():
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            logger.info(f"[SSH隧道] 正在连接 {username}@{host}:{port} ...")
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=15,
                allow_agent=False,
                look_for_keys=False,
            )
            _ssh_client = client
            transport = client.get_transport()
            if transport is None:
                logger.error("[SSH隧道] 获取 transport 失败")
                ready_event.set()
                return

            logger.info("[SSH隧道] SSH 连接成功，正在建立端口转发...")
            threads = []
            for local_port, remote_host, remote_port in forwards:
                t = threading.Thread(
                    target=_forward_port,
                    args=(transport, local_port, remote_host, remote_port),
                    daemon=True,
                )
                t.start()
                threads.append(t)

            retries = 0  # 连接成功后重置
            ready_event.set()

            # 保持连接直到 stop 事件
            while not _stop_event.is_set():
                _stop_event.wait(timeout=5)
                if transport.is_active():
                    transport.send_ignore()
                else:
                    logger.warning("[SSH隧道] 连接已断开")
                    break

        except paramiko.AuthenticationException:
            logger.error("[SSH隧道] 认证失败，请检查密码")
            break  # 认证失败不重试
        except paramiko.SSHException as e:
            retries += 1
            wait = min(2 ** retries, 32)
            logger.warning(f"[SSH隧道] SSH 错误，{wait}秒后重试 ({retries}/{max_retries}): {e}")
            time.sleep(wait)
        except OSError as e:
            retries += 1
            wait = min(2 ** retries, 32)
            logger.warning(f"[SSH隧道] 网络错误，{wait}秒后重试 ({retries}/{max_retries}): {e}")
            time.sleep(wait)
        except Exception as e:
            retries += 1
            wait = min(2 ** retries, 32)
            logger.warning(f"[SSH隧道] 未知错误，{wait}秒后重试 ({retries}/{max_retries}): {e}")
            time.sleep(wait)
        finally:
            _ssh_client = None
            try:
                client.close()
            except Exception:
                pass

    logger.info("[SSH隧道] 已断开")
    ready_event.set()


def start_ssh_tunnel() -> bool:
    """根据配置启动 SSH 端口转发隧道。"""
    global _tunnel_thread

    if _tunnel_thread is not None and _tunnel_thread.is_alive():
        logger.debug("[SSH隧道] 已在运行，跳过")
        return True

    try:
        from core.config_manager import get_config_manager
        cfg = get_config_manager().config
        ssh_cfg = cfg.ssh_tunnel
    except Exception as e:
        logger.debug(f"[SSH隧道] 加载配置失败: {e}")
        return False

    if not ssh_cfg.enable:
        logger.debug("[SSH隧道] 未启用")
        return False

    host = ssh_cfg.host
    port = ssh_cfg.port
    password = os.getenv("SSH_TUNNEL_PASSWORD", "").strip()
    if not password:
        logger.warning("[SSH隧道] 未配置 SSH_TUNNEL_PASSWORD 环境变量")
        return False

    # 解析 host: "root@xxx.com" -> username="root", hostname="xxx.com"
    if "@" in host:
        username, hostname = host.split("@", 1)
    else:
        username = "root"
        hostname = host

    forwards = [
        (ssh_cfg.local_tts_port, "localhost", ssh_cfg.remote_tts_port),
        (ssh_cfg.local_asr_port, "localhost", ssh_cfg.remote_asr_port),
    ]
    # SER 端口转发（可选）
    if hasattr(ssh_cfg, 'local_ser_port') and hasattr(ssh_cfg, 'remote_ser_port'):
        forwards.append((ssh_cfg.local_ser_port, "localhost", ssh_cfg.remote_ser_port))

    _stop_event.clear()
    ready_event = threading.Event()

    _tunnel_thread = threading.Thread(
        target=_tunnel_worker,
        args=(hostname, port, username, password, forwards, ready_event),
        daemon=True,
    )
    _tunnel_thread.start()

    # 等待隧道建立或失败
    ready_event.wait(timeout=20)

    if _ssh_client is not None and _ssh_client.get_transport() and _ssh_client.get_transport().is_active():
        ser_info = f", SER localhost:{ssh_cfg.local_ser_port}" if hasattr(ssh_cfg, 'local_ser_port') else ""
        logger.info(
            f"[SSH隧道] 已建立，TTS localhost:{ssh_cfg.local_tts_port}, "
            f"ASR localhost:{ssh_cfg.local_asr_port}{ser_info}"
        )
        atexit.register(stop_ssh_tunnel)
        return True
    else:
        logger.error("[SSH隧道] 建立失败")
        return False


def stop_ssh_tunnel() -> None:
    """关闭 SSH 隧道。"""
    global _tunnel_thread, _ssh_client
    if _tunnel_thread is None:
        return
    logger.info("[SSH隧道] 正在关闭...")
    _stop_event.set()
    if _ssh_client is not None:
        try:
            _ssh_client.close()
        except Exception:
            pass
    _tunnel_thread.join(timeout=5)
    _tunnel_thread = None
