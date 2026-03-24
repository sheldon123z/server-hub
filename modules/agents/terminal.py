"""WebSocket PTY 终端 — 在浏览器中提供完整的 bash 终端"""

import asyncio
import fcntl
import logging
import os
import pty
import select
import struct
import termios

logger = logging.getLogger(__name__)


class WebTerminal:
    """异步 PTY 终端，通过 WebSocket 驱动"""

    def __init__(self):
        self.master_fd: int | None = None
        self.pid: int | None = None

    def spawn(self, cols: int = 120, rows: int = 30):
        """启动一个 bash 子进程，连接到 PTY"""
        pid, fd = pty.fork()
        if pid == 0:
            # 子进程 — 执行 bash
            os.execvp("bash", ["bash", "--login"])
        else:
            # 父进程
            self.pid = pid
            self.master_fd = fd
            # 设置终端大小
            self.resize(cols, rows)
            # 设置非阻塞
            flag = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)
            logger.info(f"Terminal spawned: pid={pid}, fd={fd}")

    def resize(self, cols: int, rows: int):
        """调整终端大小"""
        if self.master_fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def write(self, data: str):
        """写入用户输入到终端"""
        if self.master_fd is not None:
            os.write(self.master_fd, data.encode("utf-8", errors="replace"))

    def read(self, max_bytes: int = 65536) -> str | None:
        """从终端读取输出（非阻塞）"""
        if self.master_fd is None:
            return None
        try:
            ready, _, _ = select.select([self.master_fd], [], [], 0.01)
            if ready:
                data = os.read(self.master_fd, max_bytes)
                return data.decode("utf-8", errors="replace")
        except (OSError, IOError):
            return None
        return None

    def is_alive(self) -> bool:
        """检查子进程是否存活"""
        if self.pid is None:
            return False
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self):
        """关闭终端"""
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        if self.pid is not None:
            try:
                os.kill(self.pid, 9)
                os.waitpid(self.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
            self.pid = None
            logger.info("Terminal closed")
