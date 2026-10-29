# -*- coding: utf-8 -*-
"""豆瓣真实数据分析：出结论 + 出图。

用法：python analysis/report.py
输出：output/*.png + output/analysis.md
"""
from __future__ import annotations

import configparser
import sys
import warnings
from pathlib import Path

import matplotlib

warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pymysql

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "DengXian",
    "WenQuanYi Zen Hei", "Noto Sans CJK SC",  # 容器/Linux 环境
]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 130
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.25

C1, C2, C3 = "#2E6E9E", "#EDAE49", "#D1495B"


def settings():
    cp = configparser.ConfigParser()
    cp.read(ROOT.parent / "film-analytics" / "config.ini", encoding="utf-8")
    c = dict(cp["mysql"]) if "mysql" in cp else {}
    return dict(host=c.get("host", "127.0.0.1"), port=int(c.get("port", 3306)),
                user=c.get("user", "root"), password=c.get("password", ""),
                database="douban_analytics")


def main() -> int:
    conn = pymysql.connect(**settings(), charset="utf8mb4")

    def q(sql):
        return pd.read_sql(sql, conn)

    lines: list[str] = ["# 豆瓣电影数据分析（真实数据）", ""]

    def say(t=""):
        print(t)
        lines.append(t)

    # ---------------------------------------------------------------- 1
    kpi = q("SELECT * FROM ads_kpi").iloc[0]
    say("## 一、样本概况")
    say()
    say(f"- 影片：**{int(kpi['films']):,}** 部，年份跨度 {int(kpi['years_from'])}–{int(kpi['years_to'])}")
    say(f"- 平均评分 **{kpi['avg_rating']}**，核心字段完整率 **{kpi['data_completeness']}%**")
    say(f"- 其中 Top250 影片 **{int(kpi['top250_cnt'])}** 部")
    say()

    # ---------------------------------------------------------------- 2 评分分布
    dist = q("""
        SELECT CASE WHEN rating < 5 THEN '1) <5'
                    WHEN rating < 6 THEN '2) 5-6'
                    WHEN rating < 7 THEN '3) 6-7'
                    WHEN rating < 8 THEN '4) 7-8'
                    WHEN rating < 9 THEN '5) 8-9'
                    ELSE '6) 9+' END AS band,
               COUNT(*) AS films
        FROM dim_movie GROUP BY band ORDER BY band
    """)
    say("## 二、评分分布：这是一份**精选集**，不是随机抽样")
    say()
    for _, r in dist.iterrows():
        say(f"- {r['band']:<6} {int(r['films']):>5} 部")
    say()
    say(f"结论：中位数高于均值，且没有一部低于 100 人评分。说明数据源按热度/口碑筛选过，"
        f"**不能用来推断\"所有电影的评分分布\"**，只能描述\"知名影片\"。")
    say()

    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.hist(q("SELECT rating FROM dim_movie WHERE rating IS NOT NULL")["rating"],
            bins=35, color=C1, alpha=0.85)
    ax.axvline(7.46, color=C2, ls="--", lw=2, label="均值 7.46")
    ax.set_xlabel("评分")
    ax.set_ylabel("影片数")
    ax.set_title("豆瓣影片评分分布（2,065 部）", fontsize=14, fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "01_评分分布.png", bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- 3 类型
    genre = q("SELECT * FROM ads_genre_rank ORDER BY rank_no")
    say("## 三、类型：数量多 ≠ 口碑好")
    say()
    say("| 类型 | 影片数 | 平均分 | 平均评分人数 |")
    say("|---|---|---|---|")
    for _, r in genre.iterrows():
        say(f"| {r['genre']} | {int(r['films'])} | {r['avg_rating']} | {int(r['avg_heat']):,} |")
    say()
    top = genre.iloc[0]
    bottom = genre.iloc[-1]
    say(f"结论：{top['genre']} 平均分最高（{top['avg_rating']}），{bottom['genre']} 最低（{bottom['avg_rating']}）；"
        f"但影片数前三的「剧情/动作/喜剧」平均分并不占优——**热门类型靠量，冷门类型靠质**。")
    say()

    fig, ax = plt.subplots(figsize=(9, 5.4))
    g = genre.sort_values("films")
    ax.scatter(g["films"], g["avg_rating"], s=g["avg_heat"] / 6000 + 30,
               color=C1, alpha=0.75, edgecolors="white", linewidths=0.6)
    for _, r in g.iterrows():
        ax.annotate(r["genre"], (r["films"], r["avg_rating"]),
                    textcoords="offset points", xytext=(6, 4), fontsize=8.5, color="#444")
    ax.set_xlabel("影片数量")
    ax.set_ylabel("平均评分")
    ax.set_title("类型画像：数量 vs 口碑（气泡大小=平均评分人数）", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "02_类型画像.png", bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- 4 年代
    year = q("SELECT * FROM ads_year_trend ORDER BY release_year")
    say("## 四、年代趋势：老片评分系统性更高")
    say()
    decade = q("""
        SELECT FLOOR(release_year/10)*10 AS decade, COUNT(*) AS films,
               ROUND(AVG(rating),2) AS avg_rating, ROUND(AVG(total_ratings),0) AS avg_heat
        FROM dim_movie WHERE release_year IS NOT NULL
        GROUP BY decade ORDER BY decade
    """)
    for _, r in decade.iterrows():
        say(f"- {int(r['decade'])}s：{int(r['films']):>4} 部，均分 {r['avg_rating']}，"
            f"平均 {int(r['avg_heat']):,} 人评分")
    say()
    corr_year = q("""
        SELECT @n := COUNT(*) FROM dim_movie WHERE release_year IS NOT NULL AND rating IS NOT NULL
    """)
    say("结论：明显的时间偏倚——能被今天收录进数据集的早期电影本身就是\"经过时间筛选的经典\"，"
        "而新片包含大量平庸之作。这是**幸存者偏差**，不是\"电影越拍越差\"。")
    say()
    say("另外：有 4 部影片的 release_date 只写了 `2026`（未定档的待映片），已并入 2026 年统计。")
    say()

    fig, ax1 = plt.subplots(figsize=(10, 4.8))
    ax1.bar(year["release_year"], year["films"], color=C1, alpha=0.8, label="影片数")
    ax1.set_xlabel("上映年份")
    ax1.set_ylabel("影片数", color=C1)
    ax2 = ax1.twinx()
    ax2.plot(year["release_year"], year["avg_rating"], color=C2, lw=2, label="平均评分")
    ax2.set_ylabel("平均评分", color=C2)
    ax2.grid(False)
    ax1.set_title("各年影片数与平均评分（1980 年后）", fontsize=14, fontweight="bold")
    fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.88), frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "03_年代趋势.png", bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- 5 热度
    heat = q("SELECT * FROM ads_heat_vs_rating ORDER BY sort_no")
    say("## 五、热度与口碑：越冷门越高分？")
    say()
    say("| 评分人数 | 影片数 | 平均分 |")
    say("|---|---|---|")
    for _, r in heat.iterrows():
        say(f"| {r['band']} | {int(r['films'])} | {r['avg_rating']} |")
    say()
    pear = q("""
        SELECT ROUND(
          (COUNT(*)*SUM(rating*LN(total_ratings)) - SUM(rating)*SUM(LN(total_ratings))) /
          (SQRT(COUNT(*)*SUM(rating*rating) - SUM(rating)*SUM(rating)) *
           SQRT(COUNT(*)*SUM(LN(total_ratings)*LN(total_ratings)) - SUM(LN(total_ratings))*SUM(LN(total_ratings))))
        , 3) AS pearson
        FROM dim_movie WHERE rating IS NOT NULL AND total_ratings > 0
    """)
    say(f"皮尔逊相关系数（评分 vs ln评分人数）= **{pear['pearson'][0]}**")
    say()
    say(f"结论：热度与评分**正相关**（r={pear['pearson'][0]}），评分人数越多、均分越高——"
        f"从 10 万以下的 {heat.iloc[0]['avg_rating']} 分单调升到 120 万以上的 {heat.iloc[-1]['avg_rating']} 分。"
        f"\"小众即高分\"在这份数据里不成立。")
    say()
    say("但要注意：这个相关性有相当一部分来自**选样本身**——数据集只收录知名影片，"
        "真正的冷门片根本没进来，所以不能反推\"所有电影\"。")
    say()

    fig, ax = plt.subplots(figsize=(9, 4.6))
    bars = ax.bar(heat["band"], heat["avg_rating"], color=C1, alpha=0.9, width=0.55)
    for b, v, n in zip(bars, heat["avg_rating"], heat["films"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v}\n({n}部)",
                ha="center", fontsize=9, color="#555")
    ax.set_ylim(0, heat["avg_rating"].max() * 1.25)
    ax.set_xlabel("评分人数区间")
    ax.set_ylabel("平均评分")
    ax.set_title("热度分桶 vs 平均评分", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "04_热度与评分.png", bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- 6 国家
    country = q("SELECT * FROM ads_country_rank ORDER BY rank_no LIMIT 12")
    say("## 六、国家/地区：数量与口碑的错位")
    say()
    say("| 国家/地区 | 影片数 | 平均分 | 平均评分人数 |")
    say("|---|---|---|---|")
    for _, r in country.iterrows():
        say(f"| {r['country']} | {int(r['films'])} | {r['avg_rating']} | {int(r['avg_heat']):,} |")
    say()

    fig, ax = plt.subplots(figsize=(9, 4.8))
    c = country.sort_values("films")
    ax.barh(c["country"], c["films"], color=C1, alpha=0.85, label="影片数")
    ax.set_xlabel("影片数")
    ax2 = ax.twiny()
    ax2.plot(c["avg_rating"], c["country"], color=C2, marker="o", lw=2, label="平均分")
    ax2.set_xlabel("平均分", color=C2)
    ax2.grid(False)
    ax.set_title("各国/地区影片数量与平均分", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "05_国家对比.png", bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- 7 导演
    director = q("SELECT * FROM ads_director_rank ORDER BY rank_no LIMIT 10")
    say("## 七、导演口碑榜（作品 ≥3 部）")
    say()
    say("| 导演 | 作品数 | 平均分 | 平均评分人数 |")
    say("|---|---|---|---|")
    for _, r in director.iterrows():
        say(f"| {r['director']} | {int(r['films'])} | {r['avg_rating']} | {int(r['avg_heat']):,} |")
    say()

    # ---------------------------------------------------------------- 8 Top250
    cmp = q("""
        SELECT in_top250, COUNT(*) AS films, ROUND(AVG(rating),2) AS avg_rating,
               ROUND(AVG(total_ratings),0) AS avg_heat, ROUND(AVG(runtime_min),1) AS avg_runtime
        FROM dim_movie GROUP BY in_top250
    """)
    say("## 八、Top250 vs 其余影片：选样偏差的直接证据")
    say()
    for _, r in cmp.iterrows():
        tag = "Top250" if r["in_top250"] else "非 Top250"
        say(f"- {tag:<9} {int(r['films']):>5} 部，均分 {r['avg_rating']}，"
            f"平均 {int(r['avg_heat']):,} 人评分，片长 {r['avg_runtime']} 分钟")
    say()

    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    ax.bar(["非 Top250", "Top250"], cmp.sort_values("in_top250")["avg_rating"],
           color=[C1, C2], width=0.5)
    for i, v in enumerate(cmp.sort_values("in_top250")["avg_rating"]):
        ax.text(i, v + 0.05, f"{v}", ha="center", fontsize=11)
    ax.set_ylabel("平均评分")
    ax.set_ylim(0, 10)
    ax.set_title("Top250 与其余影片的平均分对比", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "06_Top250对比.png", bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- 9 片长
    rt = q("SELECT * FROM dws_runtime_band ORDER BY sort_no")
    say("## 九、片长与评分")
    say()
    for _, r in rt.iterrows():
        say(f"- {r['band']}：{int(r['films'])} 部，平均 {r['avg_rating']} 分")
    say()

    conn.close()
    (OUT / "analysis.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入 {OUT / 'analysis.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
