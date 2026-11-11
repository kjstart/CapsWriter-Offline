"""仅清理 CapsWriter 自己的识别记录，不扫描或删除其他用户文件。"""
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import re
import tempfile

_ENTRY = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:[.,]\d+)?\s+'
    r'(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)\b'
)


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def prune_log(path: Path, days: int, now=None):
    """在创建该日志的 FileHandler 之前清理；保留完整的多行日志条目。

    旧版日志没有日期：已过期文件清空，否则以本次迁移日期标记旧条目，
    最多再保留 days 天，避免持续更新的文件永久保留无日期正文。
    清理失败不阻止程序启动。days=0 禁用。
    """
    if days <= 0 or not path.is_file() or _linked(path) or _linked(path.parent):
        return
    now = now or datetime.now()
    cutoff = now - timedelta(days=days)
    temporary = None
    try:
        text = path.read_text(encoding='utf-8')
        stale_file = datetime.fromtimestamp(path.stat().st_mtime) < cutoff
        keep = not stale_file
        retained = []
        if text and not stale_file and not _ENTRY.match(text.splitlines()[0]):
            retained.append(now.strftime('%Y-%m-%d %H:%M:%S') +
                            ' INFO [Legacy log imported; original dates unknown]\n')
        for line in text.splitlines(keepends=True):
            match = _ENTRY.match(line)
            if match:
                try:
                    keep = datetime.strptime(match[1], '%Y-%m-%d %H:%M:%S') >= cutoff
                except ValueError:
                    keep = True
            if keep:
                retained.append(line)
        cleaned = ''.join(retained)
        if cleaned == text:
            return
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(cleaned)
        os.replace(temporary, path)
    except (OSError, UnicodeError):
        pass
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def cleanup_history(base_dir: Path, days: int, now=None):
    """清理过期识别日记及程序命名的音频；不处理导出文件、不跟随链接。
    """
    if days <= 0:
        return
    cutoff = ((now or datetime.now()) - timedelta(days=days)).date()
    try:
        for year in base_dir.iterdir():
            if not re.fullmatch(r'\d{4}', year.name) or _linked(year) or not year.is_dir():
                continue
            for month in year.iterdir():
                if not re.fullmatch(r'\d{2}', month.name) or _linked(month) or not month.is_dir():
                    continue
                assets = month / 'assets'
                if assets.is_dir() and not _linked(assets):
                    for audio in assets.iterdir():
                        match = re.match(r'^\((\d{8}-\d{6})\)', audio.name)
                        if (not match or audio.suffix.lower() not in ('.wav', '.mp3')
                                or _linked(audio) or not audio.is_file()):
                            continue
                        try:
                            recorded = datetime.strptime(match[1], '%Y%m%d-%H%M%S').date()
                            if (recorded.year == int(year.name) and recorded.month == int(month.name)
                                    and recorded < cutoff):
                                audio.unlink()
                        except (ValueError, OSError):
                            continue
                for path in month.iterdir():
                    match = re.fullmatch(r'(\d{2})(?:-.+)?\.md', path.name)
                    if not match or _linked(path) or not path.is_file():
                        continue
                    try:
                        recorded = date(int(year.name), int(month.name), int(match[1]))
                        if recorded >= cutoff:
                            continue
                        with path.open(encoding='utf-8') as stream:
                            header = stream.read(128)
                        if header.startswith('```txt\n正则表达式 Tip') or header.startswith('# LLM 对话记录'):
                            path.unlink()
                    except (ValueError, OSError, UnicodeError):
                        continue
    except OSError:
        pass
