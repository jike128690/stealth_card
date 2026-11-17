"""外部配置与数据路径解耦工具（对应开发计划文档 3.1）。

打包为单文件 EXE 后，程序运行时代码会被解压至系统临时目录（sys._MEIPASS），
而用户日常修改的 YAML 模板、Excel 题库与 SQLite 数据库必须保留在 EXE
同级目录下以支持热更新，因此统一在此封装路径定位函数。
"""

import os
import sys


def get_app_dir() -> str:
    """获取 EXE 可执行文件所在的真实外部目录，用于读写配置、题库与数据库"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_external_path(relative_path: str) -> str:
    """拼接外部可热更新资源路径"""
    base_dir = get_app_dir()
    full_path = os.path.join(base_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    return full_path
