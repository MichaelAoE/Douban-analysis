# -*- coding: utf-8 -*-
"""豆瓣真实数据：清洗 + 入库 + 汇总层构建。

用法：python src/load.py
幂等：每次重建 ods/dim/bridge/dws/ads，重复执行结果一致。
"""
from __future__ import annotations

import configparser
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymysql

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT.parent / "archive"
SQL_DIR = ROOT / "sql"
DB_NAME = "douban_analytics"

sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- 连接
def load_settings() -> dict:
    cfg_path = ROOT.parent / "film-analytics" / "config.ini"
    conf = {}
    if cfg_path.exists():
        cp = configparser.ConfigParser()
        cp.read(cfg_path, encoding="utf-8")
        if "mysql" in cp:
            conf = dict(cp["mysql"])
    return {
        "host": conf.get("host", "127.0.0.1"),
        "port": int(conf.get("port", 3306)),
        "user": conf.get("user", "root"),
        "password": conf.get("password", ""),
    }


def connect(settings: dict, database: str | None = None):
    return pymysql.connect(
        host=settings["host"], port=settings["port"], user=settings["user"],
        password=settings["password"], database=database, charset="utf8mb4",
    )


def split_sql(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def run_sql_file(conn, name: str) -> int:
    stmts = split_sql((SQL_DIR / name).read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for stmt in stmts:
            cur.execute(stmt)
    conn.commit()
    return len(stmts)


# ---------------------------------------------------------------- 清洗
DATE_RE = {"full": re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"),
           "ym": re.compile(r"^(\d{4})-(\d{2})$"),
           "y": re.compile(r"^(\d{4})$")}


def parse_date(raw: str):
    """返回 (date 或 None, year 或 None, 状态)。"""
    if not isinstance(raw, str):
        return None, None, "empty"
    s = raw.strip()
    if not s:
        return None, None, "empty"
    m = DATE_RE["full"].match(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return datetime(y, mo, d).date(), y, "full"
        except ValueError:
            return None, y, "invalid"
    m = DATE_RE["ym"].match(s)
    if m:
        return None, int(m.group(1)), "year_month"
    m = DATE_RE["y"].match(s)
    if m:
        return None, int(m.group(1)), "year_only"
    return None, None, "unparsed"


def parse_runtime(raw):
    if not isinstance(raw, str):
        return None
    m = re.search(r"(\d+)", raw)
    if not m:
        return None
    v = int(m.group(1))
    return v if 20 <= v <= 600 else None


def split_multi(raw, sep: str) -> list[str]:
    if not isinstance(raw, str):
        return []
    return [x.strip() for x in raw.split(sep) if x.strip()]


# ---------------------------------------------------------------- 主流程
def main() -> int:
    t0 = time.time()
    settings = load_settings()

    print("读取 CSV ...")
    df = pd.read_csv(ARCHIVE / "douban_all_movies.csv", encoding="utf-8")
    print(f"  all_movies: {len(df):,} 行")

    top250 = set()
    try:
        t = pd.read_csv(ARCHIVE / "douban_top250_movies.csv", encoding="utf-8-sig")
    except pd.errors.ParserError as exc:
        print(f"  top250 解析失败（{str(exc)[:50]}），跳过坏行读取")
        t = pd.read_csv(ARCHIVE / "douban_top250_movies.csv", encoding="utf-8-sig",
                        engine="python", on_bad_lines="skip")
    top250 = set(t["movie_id"].astype(int))
    print(f"  top250: {len(top250):,} 个 id（文件行数 {len(t)}，有坏行被跳过）")

    # ---------- 清洗 ----------
    stats = {"date_full": 0, "date_ym": 0, "date_y": 0, "date_empty": 0, "date_bad": 0,
             "runtime_ok": 0, "runtime_bad": 0}

    movies, raw_rows = [], []
    genre_links, country_links, person_links = [], [], []
    now = datetime.now()

    for row in df.itertuples(index=False):
        mid = int(row.movie_id)
        d, year, dstat = parse_date(row.release_date)
        if dstat == "full":
            stats["date_full"] += 1
        elif dstat == "year_month":
            stats["date_ym"] += 1
        elif dstat == "year_only":
            stats["date_y"] += 1
        elif dstat == "empty":
            stats["date_empty"] += 1
        else:
            stats["date_bad"] += 1

        rt = parse_runtime(row.runtime)
        stats["runtime_ok" if rt else "runtime_bad"] += 1

        summary = row.summary if isinstance(row.summary, str) else ""
        countries = split_multi(row.countries, " / ")
        genres = split_multi(row.genres, ",")

        raw_rows.append((
            mid, str(row.title), str(row.rating), int(row.total_ratings) if pd.notna(row.total_ratings) else None,
            row.directors if isinstance(row.directors, str) else None,
            row.actors if isinstance(row.actors, str) else None,
            row.screenwriters if isinstance(row.screenwriters, str) else None,
            row.release_date if isinstance(row.release_date, str) else None,
            row.genres if isinstance(row.genres, str) else None,
            row.countries if isinstance(row.countries, str) else None,
            row.languages if isinstance(row.languages, str) else None,
            row.runtime if isinstance(row.runtime, str) else None,
            summary or None, row.link, 1 if mid in top250 else 0, now,
        ))

        movies.append((
            mid, str(row.title), float(row.rating) if pd.notna(row.rating) else None,
            int(row.total_ratings) if pd.notna(row.total_ratings) else None,
            year, d, rt, len(summary) if summary else None,
            countries[0] if countries else None,
            1 if mid in top250 else 0,
            1 if summary.strip() else 0,
        ))

        for g in genres:
            genre_links.append((mid, g))
        for c in countries:
            country_links.append((mid, c))
        if isinstance(row.directors, str) and row.directors.strip():
            person_links.append((mid, row.directors.strip(), "director", 0))
        for i, a in enumerate(split_multi(row.actors, ","), start=1):
            person_links.append((mid, a, "actor", i))
        if isinstance(row.screenwriters, str) and row.screenwriters.strip():
            person_links.append((mid, row.screenwriters.strip(), "screenwriter", 0))

    print(f"\n清洗结果：日期 完整 {stats['date_full']} / 年月 {stats['date_ym']} / "
          f"仅年 {stats['date_y']} / 空 {stats['date_empty']} / 无法解析 {stats['date_bad']}")
    print(f"          片长 可解析 {stats['runtime_ok']} / 异常或缺失 {stats['runtime_bad']}")

    # ---------- 建库建表 ----------
    conn = connect(settings)
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
    conn.commit()
    conn.close()

    conn = connect(settings, DB_NAME)
    n_stmt = run_sql_file(conn, "01_schema.sql")
    print(f"\n表结构：{n_stmt} 条语句")

    # ---------- 装载 ----------
    def bulk(sql, rows, batch=1000):
        with conn.cursor() as cur:
            for i in range(0, len(rows), batch):
                cur.executemany(sql, rows[i:i + batch])
        conn.commit()

    bulk("INSERT INTO ods_movie_raw (movie_id,title,rating_raw,total_ratings,directors_raw,"
         "actors_raw,screenwriters_raw,release_date_raw,genres_raw,countries_raw,languages_raw,"
         "runtime_raw,summary,link,in_top250,load_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
         raw_rows)
    print(f"  ods_movie_raw      {len(raw_rows):>6,} 行")

    bulk("INSERT INTO dim_movie (movie_id,title,rating,total_ratings,release_year,"
         "release_date,runtime_min,summary_len,country_main,in_top250,has_summary) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", movies)
    print(f"  dim_movie          {len(movies):>6,} 行")

    # 维度去重后写入，再建映射
    def upsert_dim(table, id_col, name_col, names):
        uniq = sorted({n for n in names if n})
        bulk(f"INSERT IGNORE INTO {table} ({name_col}) VALUES (%s)", [(x,) for x in uniq])
        with conn.cursor() as cur:
            cur.execute(f"SELECT {id_col}, {name_col} FROM {table}")
            return {name: pk for pk, name in cur.fetchall()}

    g_map = upsert_dim("dim_genre", "genre_id", "name", [g for _, g in genre_links])
    c_map = upsert_dim("dim_country", "country_id", "name", [c for _, c in country_links])
    p_map = upsert_dim("dim_person", "person_id", "name", [p for _, p, _, _ in person_links])
    print(f"  dim_genre {len(g_map)}  dim_country {len(c_map)}  dim_person {len(p_map)}")

    bulk("INSERT IGNORE INTO bridge_movie_genre (movie_id,genre_id) VALUES (%s,%s)",
         [(m, g_map[g]) for m, g in genre_links])
    bulk("INSERT IGNORE INTO bridge_movie_country (movie_id,country_id) VALUES (%s,%s)",
         [(m, c_map[c]) for m, c in country_links])
    bulk("INSERT IGNORE INTO bridge_movie_person (movie_id,person_id,role,bill_order) VALUES (%s,%s,%s,%s)",
         [(m, p_map[p], r, o) for m, p, r, o in person_links if p in p_map])
    print(f"  bridge: genre {len(genre_links):,}  country {len(country_links):,}  person {len(person_links):,}")

    # ---------- 汇总层 ----------
    n2 = run_sql_file(conn, "02_metrics.sql")
    print(f"\nDWS/ADS：{n2} 条语句")

    print("\n" + "=" * 58)
    print("自检")
    print("=" * 58)
    checks = {
        "影片数": "SELECT COUNT(*) FROM dim_movie",
        "类型数": "SELECT COUNT(*) FROM dim_genre",
        "影人数": "SELECT COUNT(*) FROM dim_person",
        "平均评分": "SELECT ROUND(AVG(rating),2) FROM dim_movie",
        "跨类型关联": "SELECT COUNT(*) FROM bridge_movie_genre",
    }
    with conn.cursor() as cur:
        for k, sql in checks.items():
            cur.execute(sql)
            print(f"  {k:<10} {cur.fetchone()[0]}")
    conn.close()
    print(f"\n完成，用时 {time.time() - t0:.1f}s　数据库：{DB_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
