# coding: utf-8
"""
快捷键任务模块

管理单个快捷键的录音任务状态
"""

from __future__ import annotations
import asyncio
import time
from contextlib import suppress
from config_client import ClientConfig as Config
from threading import Event
from typing import TYPE_CHECKING, Optional

from . import logger
from core.tools.my_status import Status
 
if TYPE_CHECKING:
    from core.client.shortcut.shortcut_config import Shortcut
    from core.client.state import ClientState
    from core.client.audio.recorder import AudioRecorder
    from core.client.app import CapsWriterClient



class ShortcutTask:
    """
    单个快捷键的录音任务

    跟踪每个快捷键独立的录音状态，防止互相干扰。
    """

    def __init__(self, app: CapsWriterClient, shortcut: Shortcut, recorder_class=None):
        """
        初始化快捷键任务

        Args:
            app: 客户端 App 实例
            shortcut: 快捷键配置
            recorder_class: AudioRecorder 类（可选，用于延迟导入）
        """
        self.app = app
        self.shortcut = shortcut
        self._recorder_class = recorder_class

        # 任务状态
        self.task: Optional[asyncio.Future] = None
        self.recording_start_time: float = 0.0
        self.is_recording: bool = False

        # hold_mode 状态跟踪
        self.pressed: bool = False
        self.released: bool = True
        self.event: Event = Event()

        # 线程池（用于 countdown）
        self.pool = None

        # 录音状态动画
        self._status = Status('开始录音', spinner='point')

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    def _get_recorder(self) -> AudioRecorder:
        """获取 AudioRecorder 实例"""
        if self._recorder_class is None:
            from core.client.audio.recorder import AudioRecorder
            self._recorder_class = AudioRecorder
        return self._recorder_class(self.app)

    def launch(self) -> None:
        """调度录音；设备打开/关闭不阻塞系统键盘钩子。"""
        if not self.app.stream.session_lock.acquire(blocking=False):
            return
        self.recording_start_time = time.time()
        self.is_recording = True
        self._stop_event = asyncio.Event()
        self._cancel_requested = False
        try:
            self.task = asyncio.run_coroutine_threadsafe(self._run_recording(), self.app.loop)
        except Exception:
            self.is_recording = False
            self.app.stream.session_lock.release()
            raise

    async def _run_recording(self) -> None:
        recorder_task = None
        try:
            if Config.microphone_on_demand:
                # 即使快速松键，也等待开麦完成后在 finally 中关闭，不能取消
                # to_thread 后留下仍在后台打开的设备。
                stream = await asyncio.to_thread(self.app.stream.start)
                if stream is None:
                    logger.warning("无法打开麦克风，本次录音已取消")
                    return
            if self._stop_event.is_set():
                return
            self.state.queue_in.put_nowait({
                'type': 'begin', 'time': self.recording_start_time, 'data': None
            })
            self.state.start_recording(self.recording_start_time)
            self._status.start()
            recorder_task = asyncio.create_task(self._get_recorder().record_and_send())
            stop_waiter = asyncio.create_task(self._stop_event.wait())
            try:
                # 录音处理异常退出时也释放麦克风，不等用户再次松键。
                await asyncio.wait((recorder_task, stop_waiter), return_when=asyncio.FIRST_COMPLETED)
            finally:
                stop_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await stop_waiter
            self.state.stop_recording()
            if Config.microphone_on_demand:
                await asyncio.to_thread(self.app.stream.stop)
            if self._cancel_requested:
                recorder_task.cancel()
            else:
                self.state.queue_in.put_nowait({
                    'type': 'finish', 'time': time.time(), 'data': None
                })
            with suppress(asyncio.CancelledError):
                await recorder_task
        except Exception:
            logger.exception("录音会话失败")
        finally:
            self.state.stop_recording()
            if Config.microphone_on_demand:
                await asyncio.to_thread(self.app.stream.stop)
            if recorder_task is not None and not recorder_task.done():
                recorder_task.cancel()
                with suppress(asyncio.CancelledError):
                    await recorder_task
            self.is_recording = False
            self._status.stop()
            self.task = None
            self.app.stream.session_lock.release()

    def cancel(self) -> None:
        """短按取消；由会话协程负责关闭可能正在打开的麦克风。"""
        self.is_recording = False
        self._cancel_requested = True
        self.app.loop.call_soon_threadsafe(self._stop_event.set)

    def finish(self) -> None:
        """结束录音并立即安排释放麦克风。"""
        self.is_recording = False
        self.app.loop.call_soon_threadsafe(self._stop_event.set)
        if self.shortcut.is_toggle_key() and not self.shortcut.suppress:
            self._restore_key()

    def _restore_key(self) -> None:
        """恢复按键状态（防自捕获逻辑由 ShortcutManager 处理）"""
        # 通知管理器执行 restore
        # 防自捕获：管理器会设置 flag 再发送按键
        manager = self._manager_ref()
        if manager:
            logger.debug(f"[{self.shortcut.key}] 自动恢复按键状态 (suppress={self.shortcut.suppress})")
            manager.schedule_restore(self.shortcut.key)
        else:
            logger.warning(f"[{self.shortcut.key}] manager 引用丢失，无法 restore")
