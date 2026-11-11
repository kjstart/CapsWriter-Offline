"""识别结果的内容检查；不以音量或字数过滤正常的短句。"""
import unicodedata


def has_recognition_content(text: str | None) -> bool:
    """忽略空白、标点及不可见控制字符，保留文字、数字和符号。"""
    return bool(text) and any(
        not char.isspace() and unicodedata.category(char)[0] not in 'PC'
        for char in text
    )
