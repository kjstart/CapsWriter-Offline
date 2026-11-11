"""兼容旧导入接口；所有用户设置来自根目录 config.json。"""
from settings import SETTINGS, BASE_DIR
__version__ = '2.6'
ClientConfig = type('ClientConfig', (), SETTINGS['client'])
