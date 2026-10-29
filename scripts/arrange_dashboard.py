# -*- coding: utf-8 -*-
"""把卡片按 12 栅格排进看板。用法：python bi/arrange_dashboard.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import require  # noqa: E402

BASE = require("METABASE_URL")
EMAIL = require("METABASE_ADMIN_EMAIL")
PWD = require("METABASE_ADMIN_PASSWORD")
COLLECTION = "豆瓣分析"
DASHBOARD = "豆瓣电影数据看板"

# (卡片名, row, col, size_x, size_y) —— 24 栅格（Metabase 全宽看板）
LAYOUT = [
    ("KPI · 影片数",          0, 0, 6, 3),
    ("KPI · 平均评分",        0, 6, 6, 3),
    ("KPI · Top250 影片",     0, 12, 6, 3),
    ("KPI · 核心字段完整率",  0, 18, 6, 3),

    ("评分分布",              3, 0, 12, 4),
    ("评分人数 × 评分",       3, 12, 12, 4),

    ("年度影片数",            7, 0, 12, 4),
    ("年度平均评分",          7, 12, 12, 4),

    ("类型 · 影片数量",       11, 0, 12, 5),
    ("类型 · 口碑榜",         11, 12, 12, 5),

    ("国家/地区 · 影片数",    16, 0, 12, 5),
    ("片长 × 评分",           16, 12, 12, 4),

    ("Top250 vs 其余",        20, 0, 8, 4),
    ("数据质量",              20, 8, 8, 4),
    ("热度 Top10",            20, 16, 8, 5),

    ("评分 Top20",            25, 0, 12, 6),
    ("导演榜（≥3 部）",       25, 12, 12, 6),
]


def req(method, path, payload=None, session=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if session:
        r.add_header("X-Metabase-Session", session)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            body = resp.read().decode()
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode('utf-8','ignore')[:300]}")


def main() -> int:
    session = req("POST", "/api/session", {"username": EMAIL, "password": PWD})["id"]

    coll = next(c for c in req("GET", "/api/collection", session=session)
                if c["name"] == COLLECTION)
    items = req("GET", f"/api/collection/{coll['id']}/items", session=session)["data"]
    cards = {c["name"]: c["id"] for c in items if c.get("model") == "card"}

    dash = next(d for d in req("GET", "/api/dashboard", session=session)
                if d["name"] == DASHBOARD)

    # 全宽看板是 24 列栅格；确保持久化设置与布局一致
    if dash.get("width") != "full":
        req("PUT", f"/api/dashboard/{dash['id']}", {"width": "full"}, session=session)

    dashcards, missing = [], []
    for i, (name, row, col, sx, sy) in enumerate(LAYOUT, start=1):
        if name not in cards:
            missing.append(name)
            continue
        dashcards.append({
            "id": -i,
            "card_id": cards[name],
            "row": row, "col": col, "size_x": sx, "size_y": sy,
            "parameter_mappings": [],
            "visualization_settings": {},
        })

    req("PUT", f"/api/dashboard/{dash['id']}/cards", {"cards": dashcards}, session=session)
    print(f"✓ 已向看板添加 {len(dashcards)} 张卡片（共 {len(LAYOUT)} 个位置）")
    if missing:
        print("  · 跳过缺失卡片：" + "、".join(missing))
    print(f"  看板地址：{BASE}/dashboard/{dash['id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\n失败：{exc}")
        raise SystemExit(1)
