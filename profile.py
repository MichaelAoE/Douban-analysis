# -*- coding: utf-8 -*-
"""豆瓣电影数据画像：把"脏"在哪、缺在哪、异常在哪全部量化出来。

用法：python src/profile.py
输出：控制台摘要 + output/profile.json（供后续报告引用）
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT.parent / "archive"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

pd.set_option("display.width", 200)


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def pct(part, whole) -> str:
    return f"{part:,} ({part / whole * 100:.1f}%)" if whole else "0"


def main() -> int:
    main_csv = ARCHIVE / "douban_all_movies.csv"
    df = pd.read_csv(main_csv, encoding="utf-8")
    n = len(df)
    findings: dict = {"total_rows": n, "columns": list(df.columns)}

    section("1. 基本规模")
    print(f"文件: {main_csv.name}")
    print(f"行数: {n:,}　列数: {df.shape[1]}")

    # ---------- 缺失 ----------
    section("2. 缺失值（真实世界第一道坎）")
    miss = df.isna().sum().sort_values(ascending=False)
    miss = miss[miss > 0]
    if miss.empty:
        print("无缺失")
    for col, cnt in miss.items():
        print(f"  {col:<16} 缺失 {pct(cnt, n)}")
    findings["missing"] = {c: int(v) for c, v in miss.items()}

    # 空字符串也当缺失
    blank = {}
    for col in df.columns:
        if df[col].dtype == object:
            b = (df[col].astype(str).str.strip() == "").sum()
            if b:
                blank[col] = int(b)
    if blank:
        print("\n  空字符串（伪装成有值）:")
        for col, cnt in sorted(blank.items(), key=lambda x: -x[1]):
            print(f"  {col:<16} {pct(cnt, n)}")
    findings["blank_strings"] = blank

    # ---------- 唯一性 ----------
    section("3. 主键与重复")
    dup_id = df["movie_id"].duplicated().sum()
    print(f"  movie_id 重复: {pct(dup_id, n)}")
    dup_title = df.duplicated(subset=["title"]).sum()
    print(f"  title 重复:    {pct(dup_title, n)}")
    if dup_title:
        vc = df["title"].value_counts()
        print("  重复片名示例:", ", ".join(f"{t}×{c}" for t, c in vc[vc > 1].head(5).items()))
    findings["dup_movie_id"] = int(dup_id)
    findings["dup_title"] = int(dup_title)

    # ---------- 评分 ----------
    section("4. 评分（rating）")
    r = pd.to_numeric(df["rating"], errors="coerce")
    print(f"  可解析为数值: {pct(r.notna().sum(), n)}")
    print(f"  缺失/非数值:  {pct(r.isna().sum(), n)}")
    if r.notna().any():
        print(f"  范围: {r.min()} ~ {r.max()}　均值 {r.mean():.2f}　中位数 {r.median():.1f}")
        print(f"  = 0 的影片:   {pct((r == 0).sum(), n)}")
        print(f"  < 1 的影片:   {pct((r < 1).sum(), n)}")
        print(f"  >= 9.5 的影片: {(r >= 9.5).sum()}")
        buckets = {
            "<5": int((r < 5).sum()),
            "5-6": int(((r >= 5) & (r < 6)).sum()),
            "6-7": int(((r >= 6) & (r < 7)).sum()),
            "7-8": int(((r >= 7) & (r < 8)).sum()),
            "8-9": int(((r >= 8) & (r < 9)).sum()),
            "9+": int((r >= 9).sum()),
        }
        print("  分档:", "  ".join(f"{k}:{v}" for k, v in buckets.items()))
        findings["rating_buckets"] = buckets
    findings["rating_null"] = int(r.isna().sum())
    findings["rating_zero"] = int((r == 0).sum())
    findings["rating_min"] = float(r.min()) if r.notna().any() else None
    findings["rating_max"] = float(r.max()) if r.notna().any() else None

    # ---------- 评分人数 ----------
    section("5. 评分人数（total_ratings）")
    c = pd.to_numeric(df["total_ratings"], errors="coerce")
    print(f"  缺失: {pct(c.isna().sum(), n)}　=0: {pct((c == 0).sum(), n)}　负数: {(c < 0).sum()}")
    if c.notna().any():
        q = c.describe(percentiles=[0.5, 0.9, 0.99])
        print(f"  中位数 {q['50%']:,.0f}　P90 {q['90%']:,.0f}　P99 {q['99%']:,.0f}　最大 {q['max']:,.0f}")
        print(f"  < 100 人评分的影片: {pct((c < 100).sum(), n)}　（长尾极重）")
    findings["rating_count_zero"] = int((c == 0).sum())

    # ---------- 日期 ----------
    section("6. 上映日期（release_date）")
    s = df["release_date"].astype(str).str.strip()
    good = s.str.match(r"^\d{4}-\d{2}-\d{2}$")
    print(f"  标准 yyyy-mm-dd: {pct(good.sum(), n)}")
    bad = s[~good]
    print(f"  非标准: {pct(len(bad), n)}")
    if len(bad):
        print("  样例:", ", ".join(f"'{v}'" for v in bad.head(8).tolist()))
        print("  形态统计:", Counter(
            re.sub(r"\d", "D", v) if v and v != "nan" else "EMPTY" for v in bad
        ).most_common(6))
    dt = pd.to_datetime(s, errors="coerce")
    print(f"  可解析为日期: {pct(dt.notna().sum(), n)}")
    print(f"  年份范围: {dt.dt.year.min():.0f} ~ {dt.dt.year.max():.0f}")
    print(f"  未来日期: {(dt > pd.Timestamp.now()).sum()}")
    findings["date_nonstandard"] = int((~good).sum())
    findings["date_unparsable"] = int(dt.isna().sum())

    # ---------- 片长 ----------
    section("7. 片长（runtime，字符串）")
    rt = df["runtime"].astype(str).str.strip()
    pure = rt.str.match(r"^\d+分钟$")
    print(f"  标准 'N分钟': {pct(pure.sum(), n)}")
    print("  非标准样例:", ", ".join(f"'{v}'" for v in rt[~pure].head(6).tolist()))
    mins = rt.str.extract(r"(\d+)").astype(float)[0]
    print(f"  可提取数字: {pct(mins.notna().sum(), n)}　范围 {mins.min():.0f}~{mins.max():.0f} 分钟")
    print(f"  < 40 分钟（疑似短片/脏数据）: {(mins < 40).sum()}　> 300 分钟: {(mins > 300).sum()}")
    findings["runtime_nonstandard"] = int((~pure).sum())

    # ---------- 多值字段 ----------
    section("8. 多值字段的分隔与基数")
    for col, sep in [("genres", ","), ("actors", ","), ("countries", " / "), ("languages", " / ")]:
        raw = df[col].dropna().astype(str)
        items = [x.strip() for v in raw for x in v.split(sep) if x.strip()]
        print(f"  {col:<10} 非空 {len(raw):,}　拆分后 {len(items):,} 项　去重 {len(set(items)):,} 项")
        print(f"  {'':10} Top5: {', '.join(f'{k}({v})' for k, v in Counter(items).most_common(5))}")
        findings[f"{col}_unique"] = len(set(items))
        if col == "genres":
            findings["genre_top"] = Counter(items).most_common(10)

    # ---------- 文本 ----------
    section("9. 文本字段")
    summ = df["summary"].fillna("").astype(str)
    print(f"  summary 平均长度 {summ.str.len().mean():.0f} 字　中位数 {summ.str.len().median():.0f}　"
          f"最短 {summ.str.len().min()}　最长 {summ.str.len().max()}")
    print(f"  空摘要: {pct((summ.str.strip() == '').sum(), n)}")
    if "tags" in df.columns:
        tg = df["tags"].fillna("").astype(str)
        print(f"  tags 非空: {pct((tg.str.strip() != '').sum(), n)}　（仅 all_movies 有此列）")
        items = [x.strip() for v in tg for x in v.split(",") if x.strip()]
        print(f"  标签 Top8: {', '.join(f'{k}({v})' for k, v in Counter(items).most_common(8))}")
        findings["tags_nonnull"] = int((tg.str.strip() != "").sum())

    # ---------- 子集关系 ----------
    section("10. 七个文件的重复度（选样偏差）")
    sets = {}
    for f in sorted(ARCHIVE.glob("douban_*.csv")):
        try:
            d = pd.read_csv(f, encoding="utf-8-sig")
        except pd.errors.ParserError as exc:
            print(f"  {f.stem:<28} 解析失败：{str(exc)[:70]}")
            d = pd.read_csv(f, encoding="utf-8-sig", engine="python", on_bad_lines="skip")
            print(f"  {f.stem:<28} 跳过坏行后剩 {len(d)} 行（该文件 summary 未加引号且含英文逗号）")
        sets[f.stem] = set(d["movie_id"])
        print(f"  {f.stem:<28} {len(d):>5} 行　唯一 id {len(sets[f.stem]):>5}")
    full = sets.get("douban_all_movies", set())
    for name, s in sets.items():
        if name == "douban_all_movies":
            continue
        print(f"  {name:<28} 被 all_movies 覆盖 {len(s & full) / len(s) * 100:5.1f}%　"
              f"独有 {len(s - full):>4}")
    print(f"\n  合并七个文件后的唯一影片数: {len(set().union(*sets.values())):,}")

    (OUT / "profile.json").write_text(
        json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n画像结果已写入 {OUT / 'profile.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
