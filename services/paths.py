"""应用可写数据目录。

打包后的程序目录可能不可写，因此数据库绝不能放在 EXE 旁边。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "FootballJCAssistant"


def user_data_dir() -> Path:
    """返回当前用户的数据目录，并保证目录已经存在。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    result = base / APP_NAME
    result.mkdir(parents=True, exist_ok=True)
    return result


def default_database_path() -> Path:
    return user_data_dir() / "football.db"
