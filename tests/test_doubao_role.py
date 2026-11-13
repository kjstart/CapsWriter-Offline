"""豆包前缀角色路由；不启动设备，不调用云端模型。"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DoubaoRoleTests(unittest.TestCase):
    def setUp(self):
        modules = {name: ModuleType(name) for name in (
            'core', 'core.client', 'core.client.llm', 'core.client.llm.llm_interfaces')}
        modules['core.client.llm'].logger = Mock()
        modules['core.client.llm.llm_interfaces'].IRoleLoader = object
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        config = load('core.client.llm.llm_role_config', 'core/client/llm/llm_role_config.py')
        self.default = config.RoleConfig(name='', enabled=True)
        self.doubao = config.RoleConfig(name='豆包', enabled=True)
        loader = SimpleNamespace(get_roles=lambda: {'默认': self.default, '豆包': self.doubao},
            get_default_role=lambda: self.default)
        detector = load('core.client.llm.llm_role_detector', 'core/client/llm/llm_role_detector.py')
        self.detector = detector.RoleDetector(loader)

    def test_natural_spoken_request_routes_to_doubao(self):
        role, text = self.detector.detect('豆包啊，你帮我翻译成英文。明天下午五点开会。')
        self.assertIs(role, self.doubao)
        self.assertEqual(text, '啊，你帮我翻译成英文。明天下午五点开会。')

    def test_prefix_punctuation_is_removed(self):
        role, text = self.detector.detect('豆包，你帮我翻译成英文。如果不是的话，麻烦帮我改一下。')
        self.assertIs(role, self.doubao)
        self.assertEqual(text, '你帮我翻译成英文。如果不是的话，麻烦帮我改一下。')

    def test_unmarked_and_quoted_requests_remain_dictation(self):
        for original in ['帮我翻译成英文。明天下午五点开会。',
                         '他说“豆包啊，你帮我翻译成英文”。',
                         '明天下午五点开会。豆包，帮我翻译成英文。']:
            with self.subTest(original=original):
                role, text = self.detector.detect(original)
                self.assertIs(role, self.default)
                self.assertEqual(text, original)

    def test_disabled_doubao_role_does_not_take_requests(self):
        self.doubao.enabled = False
        role, text = self.detector.detect('豆包，翻译成英文。你好。')
        self.assertIs(role, self.default)


if __name__ == '__main__':
    unittest.main()
