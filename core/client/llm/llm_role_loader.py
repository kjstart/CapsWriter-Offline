"""加载 LLM/*.json 角色配置，不导入或执行用户角色脚本。"""
import json
from dataclasses import fields
from pathlib import Path
from typing import Dict
from .llm_role_config import RoleConfig


class RoleLoader:
    def __init__(self):
        from config_client import BASE_DIR
        self.llm_dir = Path(BASE_DIR) / 'LLM'
        self.roles_registry: Dict[str, RoleConfig] = {}
        self.load_all_roles()

    def _load_file(self, path):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        allowed = {f.name for f in fields(RoleConfig)} - {'module_name'}
        if not isinstance(data, dict) or not {'provider', 'model'} <= data.keys():
            raise ValueError('角色必须是 JSON 对象，且包含 provider 和 model')
        if data.keys() - allowed:
            raise ValueError('未知角色字段：' + ', '.join(sorted(data.keys() - allowed)))
        for key in ('name', 'provider', 'model', 'api_url', 'api_key', 'system_prompt'):
            if key in data and not isinstance(data[key], str):
                raise ValueError(f'{key} 必须是字符串')
        for key in ('enabled', 'enable_history', 'enable_hotwords', 'enable_thinking',
                    'enable_read_selection', 'toast_editable'):
            if key in data and type(data[key]) is not bool:
                raise ValueError(f'{key} 必须是 true 或 false')
        role = RoleConfig(module_name=f'LLM.{path.stem}', **data)
        name = role.display_name or RoleConfig.DEFAULT_ROLE_NAME
        self.roles_registry = {k: v for k, v in self.roles_registry.items()
                               if v.module_name != role.module_name}
        self.roles_registry[name] = role

    def load_all_roles(self):
        self.roles_registry.clear()
        errors = []
        for path in sorted(self.llm_dir.glob('*.json')):
            try:
                self._load_file(path)
            except (OSError, ValueError, TypeError) as exc:
                errors.append({'file': path.name, 'error': type(exc).__name__, 'details': str(exc)})
        return errors

    def reload_role(self, file_path):
        path = Path(file_path)
        if path.suffix.lower() != '.json' or path.parent.resolve() != self.llm_dir.resolve():
            return False, '不是 LLM 目录内的 JSON 角色文件'
        try:
            self._load_file(path)
            return True, None
        except (OSError, ValueError, TypeError) as exc:
            return False, str(exc)

    def get_roles(self):
        return self.roles_registry.copy()

    def get_default_role(self):
        return self.get_role_by_name(RoleConfig.DEFAULT_ROLE_NAME)

    def get_role_by_name(self, name):
        return self.roles_registry.get(name, RoleConfig(name=RoleConfig.DEFAULT_ROLE_NAME,
                                                       module_name='', enabled=False))
