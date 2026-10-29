# -*- coding: utf-8 -*-
"""用 Metabase HTTP API 自动建看板：连 MySQL → 建问题卡片 → 建仪表盘。

前提：Metabase 已运行（见 start_metabase.bat），.env 里配好管理员账号与只读库账号。
用法：
    python bi/setup_metabase.py      # 建连接、集合、卡片、空看板
    python bi/arrange_dashboard.py   # 把卡片排进看板
重复执行是安全的：已存在的连接/集合/卡片会跳过。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import optional, require  # noqa: E402

BASE = require("METABASE_URL")
ADMIN_EMAIL = require("METABASE_ADMIN_EMAIL")
ADMIN_PASSWORD = require("METABASE_ADMIN_PASSWORD")
SITE_NAME = "豆瓣电影分析"
COLLECTION = "豆瓣分析"
DASHBOARD = "豆瓣电影数据看板"

DB = {
    "engine": "mysql",
    "name": "豆瓣数仓 douban_analytics",
    "details": {
        "host": optional("DB_HOST", "127.0.0.1"),
        "port": int(optional("DB_PORT", "3306")),
        "db": optional("DB_DATABASE", "douban_analytics"),
        "user": require("BI_DB_USER"),
        "password": require("BI_DB_PASSWORD"),
        "ssl": False,
        "tunnel-enabled": False,
    },
    "is_full_sync": True,
    "is_on_demand": False,
    "auto_run_queries": True,
}

# (卡片名, 图表类型, SQL, 可视化配置)
# scalar=大数字  bar=竖柱  row=横条  line=折线  table=表格
CARDS = [
    ("KPI · 影片数", "scalar",
     "SELECT COUNT(*) AS 影片数 FROM dim_movie", {}),
    ("KPI · 平均评分", "scalar",
     "SELECT ROUND(AVG(rating), 2) AS 平均评分 FROM dim_movie", {}),
    ("KPI · Top250 影片", "scalar",
     "SELECT COUNT(*) AS Top250影片数 FROM dim_movie WHERE in_top250 = 1", {}),
    ("KPI · 核心字段完整率", "scalar",
     "SELECT data_completeness AS 核心字段完整率 FROM ads_kpi", {}),

    ("评分分布", "bar",
     """SELECT CASE
                  WHEN rating < 5 THEN '1) <5'
                  WHEN rating < 6 THEN '2) 5-6'
                  WHEN rating < 7 THEN '3) 6-7'
                  WHEN rating < 8 THEN '4) 7-8'
                  WHEN rating < 9 THEN '5) 8-9'
                  ELSE '6) 9+'
                END AS 评分区间,
                COUNT(*) AS 影片数
         FROM dim_movie
         WHERE rating IS NOT NULL
         GROUP BY 评分区间
         ORDER BY 评分区间""",
     {"graph.dimensions": ["评分区间"], "graph.metrics": ["影片数"]}),

    ("评分人数 × 评分", "bar",
     """SELECT band AS 评分人数区间, avg_rating AS 平均评分
         FROM dws_heat_band ORDER BY sort_no""",
     {"graph.dimensions": ["评分人数区间"], "graph.metrics": ["平均评分"]}),

    ("年度影片数", "bar",
     """SELECT release_year AS 年份, films AS 影片数
         FROM ads_year_trend ORDER BY 年份""",
     {"graph.dimensions": ["年份"], "graph.metrics": ["影片数"]}),

    ("年度平均评分", "line",
     """SELECT release_year AS 年份, avg_rating AS 平均评分
         FROM ads_year_trend ORDER BY 年份""",
     {"graph.dimensions": ["年份"], "graph.metrics": ["平均评分"]}),

    ("类型 · 影片数量", "row",
     """SELECT genre AS 类型, films AS 影片数
         FROM dws_genre ORDER BY films DESC""",
     {"graph.dimensions": ["类型"], "graph.metrics": ["影片数"]}),

    ("类型 · 口碑榜", "table",
     """SELECT genre AS 类型, avg_rating AS 平均评分, films AS 影片数
         FROM dws_genre WHERE films >= 20
         ORDER BY avg_rating DESC LIMIT 12""", {}),

    ("国家/地区 · 影片数", "row",
     """SELECT country AS 国家地区, films AS 影片数
         FROM ads_country_rank ORDER BY films DESC""",
     {"graph.dimensions": ["国家地区"], "graph.metrics": ["影片数"]}),

    ("片长 × 评分", "bar",
     """SELECT band AS 片长区间, avg_rating AS 平均评分, films AS 影片数
         FROM dws_runtime_band ORDER BY sort_no""",
     {"graph.dimensions": ["片长区间"], "graph.metrics": ["平均评分"]}),

    ("Top250 vs 其余", "bar",
     """SELECT IF(in_top250 = 1, 'Top250', '其余影片') AS 分组,
                ROUND(AVG(rating), 2) AS 平均评分
         FROM dim_movie GROUP BY 分组""",
     {"graph.dimensions": ["分组"], "graph.metrics": ["平均评分"]}),

    ("数据质量", "table",
     """SELECT COUNT(*)               AS 影片数,
                SUM(release_year IS NULL)  AS 缺年份,
                SUM(runtime_min IS NULL)   AS 缺片长,
                SUM(total_ratings IS NULL) AS 缺评分人数,
                SUM(has_summary = 0)       AS 缺摘要,
                SUM(in_top250)             AS Top250数
         FROM dim_movie""", {}),

    ("评分 Top20", "table",
     """SELECT rank_no AS 排名, title AS 片名, rating AS 评分,
                total_ratings AS 评分人数, release_year AS 年份,
                IF(in_top250 = 1, '是', '否') AS Top250
         FROM ads_top_movies ORDER BY rank_no""", {}),

    ("热度 Top10", "table",
     """SELECT title AS 片名, total_ratings AS 评分人数, rating AS 评分,
                release_year AS 年份
         FROM dim_movie
         WHERE total_ratings IS NOT NULL
         ORDER BY total_ratings DESC LIMIT 10""", {}),

    ("导演榜（≥3 部）", "table",
     """SELECT rank_no AS 排名, director AS 导演, films AS 作品数,
                avg_rating AS 平均评分, avg_heat AS 平均评分人数
         FROM ads_director_rank ORDER BY rank_no""", {}),
]


def _req(method: str, path: str, payload=None, session: str | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-Metabase-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from None


def main() -> int:
    # Metabase 可能已被同机其他项目初始化过：优先登录，登录不上再走首次初始化
    try:
        session = _req("POST", "/api/session",
                       {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).get("id")
        print("Metabase 已初始化，登录成功")
    except RuntimeError:
        token = _req("GET", "/api/session/properties").get("setup-token")
        if not token:
            raise SystemExit("Metabase 未初始化且没有 setup-token：请先完成网页版初始化")
        print("首次初始化：创建管理员账号……")
        result = _req("POST", "/api/setup", {
            "token": token,
            "user": {
                "first_name": "豆瓣", "last_name": "管理员",
                "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
                "site_name": SITE_NAME,
            },
            "prefs": {"site_name": SITE_NAME, "site_locale": "zh", "allow_tracking": False},
            "database": None,
        })
        session = result.get("id")
        print(f"  ✓ 管理员已创建：{ADMIN_EMAIL}")

    dbs = _req("GET", "/api/database", session=session).get("data", [])
    existing = next((d for d in dbs if d["name"] == DB["name"]), None)
    if existing:
        db_id = existing["id"]
        print(f"  · 数据库连接已存在（id={db_id}），跳过")
    else:
        print("连接 MySQL 数仓……")
        db_id = _req("POST", "/api/database", DB, session=session)["id"]
        print(f"  ✓ 已连接 douban_analytics（id={db_id}）")

    collections = _req("GET", "/api/collection", session=session)
    coll = next((c for c in collections if c["name"] == COLLECTION), None)
    if coll:
        coll_id = coll["id"]
        print(f"  · 集合「{COLLECTION}」已存在（id={coll_id}）")
    else:
        coll_id = _req("POST", "/api/collection",
                       {"name": COLLECTION,
                        "description": "豆瓣电影真实数据的自助分析：ADS/DWS 层现成指标"},
                       session=session)["id"]
        print(f"  ✓ 已创建集合「{COLLECTION}」（id={coll_id}）")

    items = _req("GET", f"/api/collection/{coll_id}/items", session=session)
    existing_names = {c["name"] for c in items.get("data", []) if c.get("model") == "card"}
    for name, display, sql, viz in CARDS:
        if name in existing_names:
            print(f"  · 卡片已存在：{name}")
            continue
        _req("POST", "/api/card", {
            "name": name,
            "display": display,
            "dataset_query": {"database": db_id, "type": "native",
                              "native": {"query": sql, "template-tags": {}}},
            "visualization_settings": viz,
            "collection_id": coll_id,
        }, session=session)
        print(f"  ✓ 卡片：{name}（{display}）")

    dashboards = _req("GET", "/api/dashboard", session=session)
    dash = next((d for d in dashboards if d["name"] == DASHBOARD), None)
    if dash:
        print(f"  · 看板已存在（id={dash['id']}）")
    else:
        dash = _req("POST", "/api/dashboard",
                    {"name": DASHBOARD,
                     "description": "2,065 部豆瓣影片：评分、类型、年代、热度、国家、导演",
                     "width": "full",
                     "collection_id": coll_id},
                    session=session)
        print(f"  ✓ 已创建看板「{DASHBOARD}」（id={dash['id']}）")

    print(f"\n完成。看板地址：{BASE}/dashboard/{dash['id']}")
    print("下一步：python bi/arrange_dashboard.py  # 把卡片排进看板")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\n失败：{exc}")
        raise SystemExit(1)
