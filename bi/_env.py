# -*- coding: utf-8 -*-
"""读取项目根目录 .env（无第三方依赖的最简实现）。"""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def require(key: str) -> str:
    """必填环境变量，缺失时给出可操作的提示而不是晦涩的 KeyError。"""
    load_env()
    value = os.environ.get(key)
    if not value:
        raise SystemExit(
            f"缺少环境变量 {key}。请复制 .env.example 为 .env 并填写，"
            f"或在命令行里设置 {key}=..."
        )
    return value


def optional(key: str, default: str) -> str:
    load_env()
    return os.environ.get(key) or default
