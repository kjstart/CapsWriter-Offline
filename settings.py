"""加载数据配置；不执行配置内容，不依赖当前工作目录。"""
import json
from pathlib import Path

BASE_DIR = str(Path(__file__).resolve().parent)


def load_settings(path=None):
    path = Path(path) if path is not None else Path(BASE_DIR) / 'config.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'无法读取配置文件 {path}：{exc}') from exc
    sections = ('client', 'server', 'model_downloads', 'model_paths', 'paraformer',
                'sensevoice', 'fun_asr_nano', 'qwen_asr', 'force_aligner')
    if not isinstance(data, dict) or any(not isinstance(data.get(s), dict) for s in sections):
        raise ValueError(f'{path} 必须包含这些对象：{", ".join(sections)}')
    client = data['client']
    for key in ('save_audio', 'save_recognition', 'microphone_on_demand'):
        if type(client.get(key)) is not bool:
            raise ValueError(f'{path} client.{key} 必须是 true 或 false')
    if type(client.get('history_retain_days')) is not int or client['history_retain_days'] < 0:
        raise ValueError(f'{path} client.history_retain_days 必须是大于等于 0 的整数')
    if 'recognition_history_days' in client:
        raise ValueError('recognition_history_days 已改名为 history_retain_days')
    return data


def resolve_model_paths(templates):
    """解析 {model_dir} 等路径引用；检测循环及缺失引用，不使用 eval。"""
    resolved = {}
    pending = dict(templates)
    while pending:
        progressed = False
        for key, value in list(pending.items()):
            if not isinstance(value, str):
                raise ValueError(f'model_paths.{key} 必须是字符串')
            try:
                resolved[key] = value.format_map(resolved)
            except KeyError:
                continue
            del pending[key]
            progressed = True
        if not progressed:
            raise ValueError('model_paths 存在循环或缺失的引用：' + ', '.join(pending))
    return {key: Path(value) for key, value in resolved.items()}


SETTINGS = load_settings()
