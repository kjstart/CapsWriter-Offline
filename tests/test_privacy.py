"""隐私清理及按需开麦的回归检查；无需模型、麦克风或第三方依赖。"""
import asyncio
from datetime import datetime
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleanup = load('privacy_cleanup', 'core/tools/privacy_cleanup.py')


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 11, 11, 12)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_dated_logs_remove_whole_old_entries_and_keep_boundary(self):
        path = self.write('server_latest.log',
            '2026-10-01 10:00:00.123 INFO old secret\nold continuation\n'
            '2026-10-12 12:00:00.000 INFO boundary\n'
            '2026-11-11 10:00:00.000 ERROR fresh\nfresh traceback\n')
        cleanup.prune_log(path, 30, self.now)
        text = path.read_text(encoding='utf-8')
        self.assertNotIn('old', text)
        self.assertIn('boundary', text)
        self.assertIn('fresh traceback', text)

    def test_legacy_log_uses_file_age(self):
        old = self.write('old.log', '12:00:00 INFO old body\n')
        recent = self.write('recent.log', '12:00:00 INFO recent body\n')
        os.utime(old, (0, 0))
        cleanup.prune_log(old, 30, self.now)
        cleanup.prune_log(recent, 30, self.now)
        self.assertEqual(old.read_text(), '')
        self.assertIn('recent body', recent.read_text())

    def test_legacy_entries_expire_after_conservative_migration(self):
        path = self.write('legacy.log', '12:00:00 INFO legacy body\n')
        cleanup.prune_log(path, 30, self.now)
        cleanup.prune_log(path, 30, datetime(2026, 12, 12, 12))
        self.assertEqual(path.read_text(), '')

    def test_diaries_only_delete_owned_expired_files(self):
        old = self.write('2026/10/01.md', '```txt\n正则表达式 Tip\nprivate')
        llm = self.write('2026/10/01-助理.md', '# LLM 对话记录\nprivate')
        boundary = self.write('2026/10/12.md', '```txt\n正则表达式 Tip\nkeep')
        personal = self.write('2026/10/02.md', '# My own notes\nkeep')
        audio = self.write('2026/10/assets/test.wav', 'keep')
        invalid = self.write('2026/99/01.md', '# LLM 对话记录\nkeep')
        cleanup.cleanup_history(self.root, 30, self.now)
        self.assertFalse(old.exists())
        self.assertFalse(llm.exists())
        for path in (boundary, personal, audio, invalid):
            self.assertTrue(path.exists())

    def test_disabled_retention_keeps_files(self):
        path = self.write('2026/01/01.md', '# LLM 对话记录\nkeep')
        log = self.write('server.log', '2020-01-01 10:00:00 INFO keep\n')
        cleanup.cleanup_history(self.root, 0, self.now)
        cleanup.prune_log(log, 0, self.now)
        self.assertTrue(path.exists())
        self.assertIn('keep', log.read_text())

    def test_audio_retention_uses_recording_date_not_modified_time(self):
        old = self.write('2026/10/assets/(20261001-120000)正文.wav', 'old')
        recent = self.write('2026/10/assets/(20261012-120000)keep.mp3', 'keep')
        custom = self.write('2026/10/assets/my-recording.wav', 'keep')
        invalid = self.write('2026/10/assets/(20261399-120000)bad.wav', 'keep')
        cleanup.cleanup_history(self.root, 30, self.now)
        self.assertFalse(old.exists())
        for path in (recent, custom, invalid):
            self.assertTrue(path.exists())

    def test_retention_disabled_keeps_old_audio(self):
        old = self.write('2026/10/assets/(20261001-120000)old.wav', 'old')
        cleanup.cleanup_history(self.root, 0, self.now)
        self.assertTrue(old.exists())


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.settings = load('settings_test', 'settings.py')

    def test_config_validation_and_path_references(self):
        self.assertTrue(self.settings.SETTINGS['client']['save_recognition'])
        self.assertEqual(self.settings.SETTINGS['client']['history_retain_days'], 30)
        paths = self.settings.resolve_model_paths({'root': 'custom', 'file': '{root}/model.onnx'})
        self.assertEqual(paths['file'], Path('custom/model.onnx'))
        with self.assertRaises(ValueError):
            self.settings.resolve_model_paths({'a': '{b}', 'b': '{a}'})

    def test_invalid_privacy_types_fail_instead_of_enabling_retention(self):
        for field, value in [('save_audio', 'false'), ('save_recognition', 1),
                             ('history_retain_days', -1), ('history_retain_days', True)]:
            data = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
            data['client'][field] = value
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'bad.json'
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.settings.load_settings(path)

    def test_all_shipped_role_configs_are_data_not_executable_scripts(self):
        import dataclasses
        with patch.dict(sys.modules, {'role_config_test': ModuleType('role_config_test')}):
            role_module = load('role_config_test', 'core/client/llm/llm_role_config.py')
        allowed = {f.name for f in dataclasses.fields(role_module.RoleConfig)}
        for path in (ROOT / 'LLM').glob('*.json'):
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            self.assertLessEqual(data.keys(), allowed)
            role_module.RoleConfig(**data)

    def test_role_loader_ignores_python_and_reloads_json_without_stale_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            roles = Path(temp) / 'LLM'
            roles.mkdir()
            (roles / 'unsafe.py').write_text("raise RuntimeError('must not execute')", encoding='utf-8')
            path = roles / 'role.json'
            data = {'name': 'first', 'provider': 'ollama', 'model': 'local', 'enabled': False}
            path.write_text(json.dumps(data), encoding='utf-8')
            config = ModuleType('config_client')
            config.BASE_DIR = temp
            role_module = load('role_config_test', 'core/client/llm/llm_role_config.py')
            with patch.dict(sys.modules, {'config_client': config,
                                         'core.client.llm.llm_role_config': role_module}):
                loader_module = load('core.client.llm.llm_role_loader', 'core/client/llm/llm_role_loader.py')
                loader = loader_module.RoleLoader()
                self.assertEqual(list(loader.get_roles()), ['first'])
                data['name'] = 'second'
                path.write_text(json.dumps(data), encoding='utf-8')
                self.assertEqual(loader.reload_role(path), (True, None))
                self.assertEqual(list(loader.get_roles()), ['second'])
                self.assertFalse(loader.reload_role(roles / 'unsafe.py')[0])


class SaveControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = SimpleNamespace(save_audio=False, save_recognition=True, audio_name_len=20,
                                      history_retain_days=30)
        modules = {name: ModuleType(name) for name in (
            'config_client', 'numpy', 'rich', 'rich.logging', 'core', 'core.tools',
            'core.client', 'core.client.state', 'core.client.diary', 'core.client.audio')}
        modules['config_client'].ClientConfig = self.config
        modules['config_client'].BASE_DIR = str(self.root)
        modules['core.client.state'].console = Mock()
        modules['core.client.diary'].logger = Mock()
        modules['core.client.audio'].logger = Mock()
        modules['core.tools.privacy_cleanup'] = cleanup
        class RichHandler(logging.StreamHandler):
            def __init__(self, **kwargs):
                super().__init__()
                self.setLevel(kwargs.get('level', logging.NOTSET))
        modules['rich.logging'].RichHandler = RichHandler
        with patch.dict(sys.modules, modules):
            self.diary = load('core.client.diary.diary_writer', 'core/client/diary/diary_writer.py')
            self.llm = load('llm_writer_test', 'core/client/llm/llm_write_md.py')
            self.audio = load('core.client.audio.file_manager', 'core/client/audio/file_manager.py')
            self.logger_module = load('logger_test', 'core/logger.py')
        self.modules = modules

    def test_text_can_be_saved_without_audio_and_disabled_independently(self):
        writer = self.diary.DiaryWriter(self.root)
        self.assertTrue(writer.write('text without audio', datetime(2026, 11, 11).timestamp()))
        self.config.save_recognition = False
        self.assertEqual(writer.write('do not save', datetime(2026, 11, 12).timestamp()), [])
        self.assertFalse((self.root / '2026/11/12.md').exists())
        before = Path.cwd()
        try:
            os.chdir(self.root)
            self.llm.write_llm_md('secret', 'secret', '', datetime(2026, 11, 12).timestamp())
        finally:
            os.chdir(before)
        self.assertFalse((self.root / '2026/11/12-默认.md').exists())

    def test_audio_filename_does_not_retain_transcript_when_disabled(self):
        self.config.save_recognition = False
        manager = self.audio.AudioFileManager.__new__(self.audio.AudioFileManager)
        manager.file_path = self.root / '(20261111-120000)random.wav'
        manager.file_path.write_bytes(b'audio')
        self.assertEqual(manager.rename('private transcript', 0).name, '(20261111-120000)random.wav')

    def test_file_logging_disabled_with_recognition_saving(self):
        self.config.save_recognition = False
        with patch.dict(sys.modules, self.modules):
            logger = self.logger_module.Logger.setup('privacy-off', log_dir=str(self.root))
            logger.info('private transcript')
            self.assertFalse((self.root / 'privacy-off_latest.log').exists())
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)

    def test_file_logging_has_dates_when_enabled(self):
        with patch.dict(sys.modules, self.modules):
            logger = self.logger_module.Logger.setup('privacy-on', log_dir=str(self.root))
            logger.info('recognition text')
            for handler in list(logger.handlers):
                handler.flush()
                handler.close()
                logger.removeHandler(handler)
        text = (self.root / 'privacy-on_latest.log').read_text(encoding='utf-8')
        self.assertRegex(text, r'^\d{4}-\d{2}-\d{2} ')
        self.assertIn('recognition text', text)


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = SimpleNamespace(microphone_on_demand=True)
        modules = {name: ModuleType(name) for name in (
            'config_client', 'core', 'core.client', 'core.client.shortcut',
            'core.tools', 'core.tools.my_status')}
        modules['config_client'].ClientConfig = self.config
        modules['core.client.shortcut'].logger = Mock()
        modules['core.tools.my_status'].Status = Mock()
        with patch.dict(sys.modules, modules):
            self.module = load('core.client.shortcut.task', 'core/client/shortcut/task.py')
        self.state = SimpleNamespace(queue_in=asyncio.Queue(), recording=False)
        self.state.start_recording = lambda _: setattr(self.state, 'recording', True)
        self.state.stop_recording = lambda: setattr(self.state, 'recording', False)
        self.stream = SimpleNamespace(session_lock=threading.Lock(), start=Mock(return_value=object()), stop=Mock())
        self.app = SimpleNamespace(loop=asyncio.get_running_loop(), state=self.state, stream=self.stream)
        self.messages = []
        async def record():
            try:
                while True:
                    item = await self.state.queue_in.get()
                    self.state.queue_in.task_done()
                    self.messages.append(item['type'])
                    if item['type'] == 'finish':
                        return
            finally:
                while not self.state.queue_in.empty():
                    self.state.queue_in.get_nowait()
                    self.state.queue_in.task_done()
        self.recorder = lambda _: SimpleNamespace(record_and_send=record)
        self.shortcut = SimpleNamespace(key='caps_lock', suppress=True, is_toggle_key=lambda: True)

    def task(self):
        return self.module.ShortcutTask(self.app, self.shortcut, self.recorder)

    async def ready(self):
        for _ in range(100):
            if self.state.recording:
                return
            await asyncio.sleep(.005)
        self.fail('Recording did not start')

    async def done(self, future):
        await asyncio.wait_for(asyncio.wrap_future(future), 2)

    async def test_release_closes_device_and_finishes_recorder(self):
        task = self.task()
        task.launch()
        future = task.task
        await self.ready()
        task.finish()
        await self.done(future)
        self.assertFalse(self.state.recording)
        self.assertEqual(self.messages, ['begin', 'finish'])
        self.assertGreaterEqual(self.stream.stop.call_count, 1)
        self.assertFalse(self.stream.session_lock.locked())

    async def test_short_press_while_opening_does_not_leave_mic_open(self):
        entered, release = threading.Event(), threading.Event()
        def start():
            entered.set()
            release.wait(1)
            return object()
        self.stream.start.side_effect = start
        task = self.task()
        task.launch()
        future = task.task
        try:
            await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            await asyncio.sleep(.01)
        finally:
            release.set()
        await self.done(future)
        self.assertFalse(self.state.recording)
        self.assertEqual(self.messages, [])
        self.stream.stop.assert_called()

    async def test_device_failure_releases_session(self):
        self.stream.start.return_value = None
        task = self.task()
        task.launch()
        await self.done(task.task)
        self.assertFalse(task.is_recording)
        self.assertFalse(self.stream.session_lock.locked())

    async def test_overlapping_shortcuts_cannot_close_owners_microphone(self):
        owner, other = self.task(), self.task()
        owner.launch()
        future = owner.task
        await self.ready()
        other.launch()
        self.assertFalse(other.is_recording)
        self.stream.stop.assert_not_called()
        owner.finish()
        await self.done(future)

    async def test_legacy_mode_keeps_stream_open(self):
        self.config.microphone_on_demand = False
        task = self.task()
        task.launch()
        future = task.task
        await self.ready()
        task.finish()
        await self.done(future)
        self.stream.start.assert_not_called()
        self.stream.stop.assert_not_called()

    async def test_cancel_then_record_again(self):
        task = self.task()
        task.launch()
        future = task.task
        await self.ready()
        task.cancel()
        await self.done(future)
        task.launch()
        future = task.task
        await self.ready()
        task.finish()
        await self.done(future)
        self.assertTrue(self.state.queue_in.empty())


class DeviceTests(unittest.TestCase):
    def setUp(self):
        modules = {name: ModuleType(name) for name in (
            'config_client', 'numpy', 'sounddevice', 'core', 'core.client',
            'core.client.audio', 'core.client.state', 'core.client.manager', 'core.client.ui')}
        self.config = SimpleNamespace(microphone_on_demand=True, udp_control=False)
        modules['config_client'].ClientConfig = self.config
        modules['config_client'].__version__ = 'test'
        modules['core.client.audio'].logger = Mock()
        modules['core.client.manager'].logger = Mock()
        modules['core.client.state'].console = Mock()
        modules['core.client.ui'].TipsDisplay = Mock()
        self.device = modules['sounddevice']
        self.device.PortAudioError = RuntimeError
        self.device.query_devices = Mock(return_value={'max_input_channels': 1, 'name': 'test'})
        self.handle = Mock()
        self.device.InputStream = Mock(return_value=self.handle)
        with patch.dict(sys.modules, modules):
            stream = load('core.client.audio.stream', 'core/client/audio/stream.py')
            runner = load('core.client.manager.mic_runner', 'core/client/manager/mic_runner.py')
        self.state = SimpleNamespace(recording=False, stream=None)
        self.app = SimpleNamespace(state=self.state, loop=None, stream=Mock(), shortcut=Mock(),
                                   udp=Mock(), hotword=Mock(), llm=Mock(), tray=Mock())
        self.stream = stream.AudioStreamManager(self.app)
        self.runner = runner.MicRunner(self.app)

    def test_startup_does_not_open_microphone(self):
        self.runner.start_resources()
        self.app.stream.start.assert_not_called()
        self.config.microphone_on_demand = False
        self.runner.start_resources()
        self.app.stream.start.assert_called_once()

    def test_device_is_closed_and_idle_callbacks_are_ignored(self):
        data = Mock()
        self.stream._audio_callback(data, 1, None, None)
        data.copy.assert_not_called()
        self.stream.start()
        self.assertIs(self.state.stream, self.handle)
        self.stream.stop()
        self.assertIsNone(self.state.stream)
        self.handle.close.assert_called_once()

    def test_failed_device_start_closes_partial_stream(self):
        self.handle.start.side_effect = RuntimeError('device busy')
        self.assertIsNone(self.stream.start())
        self.handle.close.assert_called_once()
        self.assertIsNone(self.state.stream)


if __name__ == '__main__':
    unittest.main()
