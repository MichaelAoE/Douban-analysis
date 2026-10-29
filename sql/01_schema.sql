-- 豆瓣真实数据集：ODS + 维度层
-- 字符集 utf8mb4，MySQL 5.7 兼容

SET NAMES utf8mb4;

DROP TABLE IF EXISTS ods_movie_raw;
DROP TABLE IF EXISTS bridge_movie_genre;
DROP TABLE IF EXISTS bridge_movie_person;
DROP TABLE IF EXISTS bridge_movie_country;
DROP TABLE IF EXISTS dim_genre;
DROP TABLE IF EXISTS dim_person;
DROP TABLE IF EXISTS dim_country;
DROP TABLE IF EXISTS dim_movie;

-- 原始快照：一个字都不改，用于回溯和对比清洗效果
CREATE TABLE ods_movie_raw (
  movie_id        INT           NOT NULL,
  title           VARCHAR(200)  NOT NULL,
  rating_raw      VARCHAR(20)   NULL,
  total_ratings   BIGINT        NULL,
  directors_raw   VARCHAR(200)  NULL,
  actors_raw      TEXT          NULL,
  screenwriters_raw VARCHAR(200) NULL,
  release_date_raw VARCHAR(40)  NULL,
  genres_raw      VARCHAR(200)  NULL,
  countries_raw   VARCHAR(200)  NULL,
  languages_raw   VARCHAR(200)  NULL,
  runtime_raw     VARCHAR(60)   NULL,
  summary         TEXT          NULL,
  link            VARCHAR(200)  NULL,
  in_top250       TINYINT       NOT NULL DEFAULT 0,
  load_time       DATETIME      NOT NULL,
  PRIMARY KEY (movie_id),
  KEY idx_year (release_date_raw)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='豆瓣原始数据快照';

-- 清洗后的影片主表
CREATE TABLE dim_movie (
  movie_id      INT           NOT NULL,
  title         VARCHAR(200)  NOT NULL,
  rating        DECIMAL(3,1)  NULL COMMENT '0-10',
  total_ratings BIGINT        NULL,
  release_year  SMALLINT      NULL,
  release_date  DATE          NULL COMMENT '缺失或非标准则为 NULL',
  runtime_min   SMALLINT      NULL COMMENT '清洗后的分钟数',
  summary_len   SMALLINT      NULL COMMENT '摘要字数',
  country_main  VARCHAR(30)   NULL COMMENT '第一出品国/地区',
  in_top250     TINYINT       NOT NULL DEFAULT 0,
  has_summary   TINYINT       NOT NULL DEFAULT 0,
  PRIMARY KEY (movie_id),
  KEY idx_year (release_year),
  KEY idx_rating (rating),
  KEY idx_ratings_cnt (total_ratings)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='影片维度（已清洗）';

CREATE TABLE dim_genre (
  genre_id INT         NOT NULL AUTO_INCREMENT,
  name     VARCHAR(20) NOT NULL,
  PRIMARY KEY (genre_id),
  UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_person (
  person_id INT         NOT NULL AUTO_INCREMENT,
  name      VARCHAR(80) NOT NULL,
  PRIMARY KEY (person_id),
  UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_country (
  country_id INT         NOT NULL AUTO_INCREMENT,
  name       VARCHAR(40) NOT NULL,
  PRIMARY KEY (country_id),
  UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE bridge_movie_genre (
  movie_id INT NOT NULL,
  genre_id INT NOT NULL,
  PRIMARY KEY (movie_id, genre_id),
  KEY idx_genre (genre_id),
  CONSTRAINT fk_bmg_movie FOREIGN KEY (movie_id) REFERENCES dim_movie(movie_id) ON DELETE CASCADE,
  CONSTRAINT fk_bmg_genre FOREIGN KEY (genre_id) REFERENCES dim_genre(genre_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE bridge_movie_country (
  movie_id   INT NOT NULL,
  country_id INT NOT NULL,
  PRIMARY KEY (movie_id, country_id),
  KEY idx_country (country_id),
  CONSTRAINT fk_bmc_movie FOREIGN KEY (movie_id) REFERENCES dim_movie(movie_id) ON DELETE CASCADE,
  CONSTRAINT fk_bmc_country FOREIGN KEY (country_id) REFERENCES dim_country(country_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE bridge_movie_person (
  movie_id  INT         NOT NULL,
  person_id INT         NOT NULL,
  role      VARCHAR(12) NOT NULL COMMENT 'director/actor/screenwriter',
  bill_order TINYINT    NULL,
  PRIMARY KEY (movie_id, person_id, role),
  KEY idx_person (person_id),
  KEY idx_role (role),
  CONSTRAINT fk_bmp_movie FOREIGN KEY (movie_id) REFERENCES dim_movie(movie_id) ON DELETE CASCADE,
  CONSTRAINT fk_bmp_person FOREIGN KEY (person_id) REFERENCES dim_person(person_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
