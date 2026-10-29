-- 豆瓣数据集：DWS 汇总层 + ADS 应用层
SET NAMES utf8mb4;

DROP TABLE IF EXISTS dws_genre;
DROP TABLE IF EXISTS dws_year;
DROP TABLE IF EXISTS dws_country;
DROP TABLE IF EXISTS dws_person;
DROP TABLE IF EXISTS dws_heat_band;
DROP TABLE IF EXISTS dws_runtime_band;
DROP TABLE IF EXISTS ads_kpi;
DROP TABLE IF EXISTS ads_top_movies;
DROP TABLE IF EXISTS ads_genre_rank;
DROP TABLE IF EXISTS ads_director_rank;
DROP TABLE IF EXISTS ads_year_trend;
DROP TABLE IF EXISTS ads_country_rank;
DROP TABLE IF EXISTS ads_heat_vs_rating;

-- ---------------- DWS ----------------
CREATE TABLE dws_genre (
  genre_id    INT           NOT NULL,
  genre       VARCHAR(20)   NOT NULL,
  films       INT           NOT NULL,
  avg_rating  DECIMAL(4,2)  NOT NULL,
  median_like DECIMAL(4,2)  NULL,
  avg_heat    DECIMAL(14,0) NOT NULL COMMENT '平均评分人数',
  avg_runtime DECIMAL(6,1)  NULL,
  PRIMARY KEY (genre_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dws_year (
  release_year SMALLINT      NOT NULL,
  films        INT           NOT NULL,
  avg_rating   DECIMAL(4,2)  NOT NULL,
  avg_heat     DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (release_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dws_country (
  country_id INT           NOT NULL,
  country    VARCHAR(40)   NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  avg_heat   DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (country_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dws_person (
  person_id  INT           NOT NULL,
  name       VARCHAR(80)   NOT NULL,
  role       VARCHAR(12)   NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  avg_heat   DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (person_id, role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dws_heat_band (
  band        VARCHAR(20)   NOT NULL,
  sort_no     TINYINT       NOT NULL,
  films       INT           NOT NULL,
  avg_rating  DECIMAL(4,2)  NOT NULL,
  avg_heat    DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (sort_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dws_runtime_band (
  band       VARCHAR(20)   NOT NULL,
  sort_no    TINYINT       NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  PRIMARY KEY (sort_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------- 装载 DWS ----------------
INSERT INTO dws_genre
SELECT g.genre_id, g.name,
       COUNT(*)                                    AS films,
       ROUND(AVG(m.rating), 2)                      AS avg_rating,
       NULL                                          AS median_like,
       ROUND(AVG(m.total_ratings), 0)               AS avg_heat,
       ROUND(AVG(m.runtime_min), 1)                  AS avg_runtime
FROM dim_genre g
JOIN bridge_movie_genre bg ON bg.genre_id = g.genre_id
JOIN dim_movie m           ON m.movie_id  = bg.movie_id
GROUP BY g.genre_id, g.name;

INSERT INTO dws_year
SELECT m.release_year, COUNT(*), ROUND(AVG(m.rating), 2), ROUND(AVG(m.total_ratings), 0)
FROM dim_movie m
WHERE m.release_year IS NOT NULL
GROUP BY m.release_year;

INSERT INTO dws_country
SELECT c.country_id, c.name, COUNT(*), ROUND(AVG(m.rating), 2), ROUND(AVG(m.total_ratings), 0)
FROM dim_country c
JOIN bridge_movie_country bc ON bc.country_id = c.country_id
JOIN dim_movie m             ON m.movie_id    = bc.movie_id
GROUP BY c.country_id, c.name;

INSERT INTO dws_person
SELECT p.person_id, p.name, bp.role, COUNT(*),
       ROUND(AVG(m.rating), 2), ROUND(AVG(m.total_ratings), 0)
FROM dim_person p
JOIN bridge_movie_person bp ON bp.person_id = p.person_id
JOIN dim_movie m            ON m.movie_id   = bp.movie_id
GROUP BY p.person_id, p.name, bp.role;

INSERT INTO dws_heat_band
SELECT band, sort_no, COUNT(*), ROUND(AVG(rating), 2), ROUND(AVG(total_ratings), 0)
FROM (
  SELECT m.*,
         CASE
           WHEN m.total_ratings <  100000  THEN '1) <10万'
           WHEN m.total_ratings <  300000  THEN '2) 10-30万'
           WHEN m.total_ratings <  600000  THEN '3) 30-60万'
           WHEN m.total_ratings < 1200000  THEN '4) 60-120万'
           ELSE                                  '5) 120万+'
         END AS band,
         CASE
           WHEN m.total_ratings <  100000  THEN 1
           WHEN m.total_ratings <  300000  THEN 2
           WHEN m.total_ratings <  600000  THEN 3
           WHEN m.total_ratings < 1200000  THEN 4
           ELSE                                 5
         END AS sort_no
  FROM dim_movie m
) t
GROUP BY band, sort_no;

INSERT INTO dws_runtime_band
SELECT band, sort_no, COUNT(*), ROUND(AVG(rating), 2)
FROM (
  SELECT rating,
         CASE
           WHEN runtime_min <  90 THEN '1) <90分'
           WHEN runtime_min < 110 THEN '2) 90-110分'
           WHEN runtime_min < 130 THEN '3) 110-130分'
           WHEN runtime_min < 150 THEN '4) 130-150分'
           ELSE                       '5) 150分+'
         END AS band,
         CASE
           WHEN runtime_min <  90 THEN 1
           WHEN runtime_min < 110 THEN 2
           WHEN runtime_min < 130 THEN 3
           WHEN runtime_min < 150 THEN 4
           ELSE 5
         END AS sort_no
  FROM dim_movie
  WHERE runtime_min IS NOT NULL
) t
GROUP BY band, sort_no;

-- ---------------- ADS ----------------
CREATE TABLE ads_kpi (
  films        INT           NOT NULL,
  avg_rating   DECIMAL(4,2)  NOT NULL,
  median_heat  BIGINT        NULL,
  years_from   SMALLINT      NULL,
  years_to     SMALLINT      NULL,
  top250_cnt   INT           NOT NULL,
  data_completeness DECIMAL(5,2) NOT NULL COMMENT '核心字段完整率%'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_kpi
SELECT
  COUNT(*),
  ROUND(AVG(rating), 2),
  NULL,
  MIN(release_year),
  MAX(release_year),
  SUM(in_top250),
  ROUND(SUM(CASE WHEN rating IS NOT NULL AND release_year IS NOT NULL
                      AND runtime_min IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
FROM dim_movie;

CREATE TABLE ads_top_movies (
  rank_no     INT           NOT NULL,
  title       VARCHAR(200)  NOT NULL,
  rating      DECIMAL(3,1)  NULL,
  total_ratings BIGINT      NULL,
  release_year SMALLINT     NULL,
  in_top250   TINYINT       NOT NULL,
  PRIMARY KEY (rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_top_movies
SELECT @rk := @rk + 1, t.*
FROM (
  SELECT title, rating, total_ratings, release_year, in_top250
  FROM dim_movie
  ORDER BY rating DESC, total_ratings DESC
  LIMIT 20
) t
CROSS JOIN (SELECT @rk := 0) init;

CREATE TABLE ads_genre_rank (
  rank_no    INT           NOT NULL,
  genre      VARCHAR(20)   NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  avg_heat   DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_genre_rank
SELECT @rk := @rk + 1, t.genre, t.films, t.avg_rating, t.avg_heat
FROM (
  SELECT genre, films, avg_rating, avg_heat
  FROM dws_genre
  WHERE films >= 20
  ORDER BY avg_rating DESC
) t
CROSS JOIN (SELECT @rk := 0) init;

CREATE TABLE ads_director_rank (
  rank_no    INT           NOT NULL,
  director   VARCHAR(80)   NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  avg_heat   DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_director_rank
SELECT @rk := @rk + 1, t.name, t.films, t.avg_rating, t.avg_heat
FROM (
  SELECT name, films, avg_rating, avg_heat
  FROM dws_person
  WHERE role = 'director' AND films >= 3
  ORDER BY avg_rating DESC, films DESC
  LIMIT 15
) t
CROSS JOIN (SELECT @rk := 0) init;

CREATE TABLE ads_year_trend (
  release_year SMALLINT      NOT NULL,
  films        INT           NOT NULL,
  avg_rating   DECIMAL(4,2)  NOT NULL,
  avg_heat     DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (release_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_year_trend
SELECT release_year, films, avg_rating, avg_heat
FROM dws_year
WHERE release_year >= 1980
ORDER BY release_year;

CREATE TABLE ads_country_rank (
  rank_no    INT           NOT NULL,
  country    VARCHAR(40)   NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  avg_heat   DECIMAL(14,0) NOT NULL,
  PRIMARY KEY (rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_country_rank
SELECT @rk := @rk + 1, t.country, t.films, t.avg_rating, t.avg_heat
FROM (
  SELECT country, films, avg_rating, avg_heat
  FROM dws_country
  WHERE films >= 30
  ORDER BY films DESC
) t
CROSS JOIN (SELECT @rk := 0) init;

CREATE TABLE ads_heat_vs_rating (
  band       VARCHAR(20)   NOT NULL,
  sort_no    TINYINT       NOT NULL,
  films      INT           NOT NULL,
  avg_rating DECIMAL(4,2)  NOT NULL,
  PRIMARY KEY (sort_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO ads_heat_vs_rating
SELECT band, sort_no, films, avg_rating FROM dws_heat_band ORDER BY sort_no;
