"""空识别结果不触发外部副作用；执行真实方法，隔离设备和网络依赖。"""
import ast
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'recognition_text', ROOT / 'core/tools/recognition_text.py')
content = importlib.util.module_from_spec(spec)
spec.loader.exec_module(content)


def load_class(relative, name, namespace, method=None):
    """加载真实类的方法体，避免导入时启动键盘钩子等依赖。"""
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    if method:
        cls.body = [node for node in cls.body if getattr(node, 'name', None) == method]
    module = ast.Module(body=[ast.ImportFrom(module='__future__',
        names=[ast.alias(name='annotations')], level=0), cls], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace[name]


EMPTY_RESULTS = [None, '', ' \t\r\n', '\u200b\ufeff', '。，！？…', '. , ? !']


class ContentTests(unittest.TestCase):
    def test_empty_and_punctuation_are_not_content(self):
        for text in EMPTY_RESULTS:
            with self.subTest(text=text):
                self.assertFalse(content.has_recognition_content(text))

    def test_short_words_numbers_and_symbols_are_preserved(self):
        for text in ['好', 'no', '0', '不', '日本語', 'é', '+', '$', '😀']:
            with self.subTest(text=text):
                self.assertTrue(content.has_recognition_content(text))


class ResultTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = SimpleNamespace(traditional_convert=False, hot=False,
            paste=False, paste_apps=[], enter_apps=[], llm_enabled=True, save_audio=False)
        self.window = Mock(return_value={})
        self.broadcast = Mock()
        self.app = SimpleNamespace(state=Mock(), hotword=Mock(), output=Mock(),
            diary=Mock(), llm=Mock(), ws=Mock())
        self.app.state.last_recognition_text = 'previous valid text'
        self.app.output.output = AsyncMock()
        self.app.llm.process_and_output = AsyncMock(return_value=None)
        self.app.hotword.get_phoneme_corrector.return_value.correct.side_effect = (
            lambda text, **kwargs: SimpleNamespace(text=text, matches=[], similars=[]))
        self.app.hotword.get_rule_corrector.return_value.substitute.side_effect = lambda text: text
        namespace = dict(asyncio=asyncio, time=time, Config=self.config,
            console=Mock(), logger=Mock(), TextOutput=SimpleNamespace(strip_punc=lambda text: text),
            get_active_window_info=self.window, broadcast_output_udp=self.broadcast,
            has_recognition_content=content.has_recognition_content)
        cls = load_class('core/client/output/result_processor.py', 'ResultProcessor', namespace)
        self.processor = cls(self.app)

    def message(self, text, final=True):
        return SimpleNamespace(text=text, is_final=final, task_id='silent-test',
            time_complete=2.0, time_submit=1.0, time_start=0.0)

    def assert_no_output(self):
        self.app.llm.process_and_output.assert_not_awaited()
        self.app.output.output.assert_not_awaited()
        self.app.diary.write.assert_not_called()
        self.window.assert_not_called()
        self.broadcast.assert_not_called()
        self.assertEqual(self.app.state.last_recognition_text, 'previous valid text')

    async def test_final_empty_results_stop_before_hotwords_llm_or_output(self):
        for text in EMPTY_RESULTS:
            with self.subTest(text=text):
                await self.processor._handle_message(self.message(text))
                self.assert_no_output()
                self.app.hotword.get_phoneme_corrector.assert_not_called()
        self.assertEqual(self.app.state.pop_audio_file.call_count, len(EMPTY_RESULTS))

    async def test_rule_that_removes_all_content_also_stops(self):
        self.app.hotword.get_rule_corrector.return_value.substitute.side_effect = None
        self.app.hotword.get_rule_corrector.return_value.substitute.return_value = '。 '
        await self.processor._handle_message(self.message('remove this'))
        self.assert_no_output()
        self.app.state.pop_audio_file.assert_called_once_with('silent-test')

    async def test_normal_short_transcript_still_reaches_llm(self):
        await self.processor._handle_message(self.message('0'))
        self.app.llm.process_and_output.assert_awaited_once_with(
            '0', paste=False, matched_hotwords=[])
        self.app.diary.write.assert_called_once_with('0', 0.0, None)

    async def test_partial_result_is_still_not_output(self):
        await self.processor._handle_message(self.message('hello', final=False))
        self.assert_no_output()
        self.app.state.pop_audio_file.assert_not_called()


class LLMEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_empty_calls_do_not_detect_roles_or_output(self):
        cls = load_class('core/client/llm/llm_handler.py', 'LLMHandler',
            dict(has_recognition_content=content.has_recognition_content,
                 LLMResult=lambda **kwargs: SimpleNamespace(**kwargs)), 'process_and_output')
        handler = cls()
        handler.detect_role = Mock(side_effect=AssertionError('must not detect a role'))
        handler.app = Mock()
        handler.monitor = Mock()
        for text in EMPTY_RESULTS:
            result = await handler.process_and_output(text)
            self.assertFalse(result.processed)
            self.assertEqual(result.result, '')
        handler.detect_role.assert_not_called()
        handler.monitor.reset.assert_not_called()
        handler.app.state.set_output_text.assert_not_called()


if __name__ == '__main__':
    unittest.main()
