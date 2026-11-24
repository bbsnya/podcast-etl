-- Схема DWH. Выполняется автоматически при первом запуске контейнера postgres.

CREATE TABLE IF NOT EXISTS podcasts (
    podcast_id    BIGINT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    rss_url       TEXT NOT NULL,
    episode_count INT,
    artist_name   TEXT,
    genre         TEXT,
    country       TEXT,
    language      TEXT,
    created_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- episode_key = sha1(podcast_id | guid или title | pub_date): всегда NOT NULL,
-- поэтому повторные запуски не создают дубликатов даже при отсутствии pub_date (NFR-3).
CREATE TABLE IF NOT EXISTS episodes (
    episode_id       BIGSERIAL PRIMARY KEY,
    episode_key      TEXT NOT NULL UNIQUE,
    podcast_id       BIGINT NOT NULL REFERENCES podcasts(podcast_id) ON DELETE CASCADE,
    guid             TEXT,
    title            TEXT NOT NULL,
    pub_date         TIMESTAMPTZ,
    description      TEXT,
    duration_seconds INT CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    audio_url        TEXT,
    duration_bucket  TEXT,
    pub_month        TEXT,
    created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_episodes_podcast_id ON episodes(podcast_id);
CREATE INDEX IF NOT EXISTS idx_episodes_pub_date   ON episodes(pub_date);

-- Агрегаты по подкастам (результат этапа Transform)
CREATE TABLE IF NOT EXISTS podcast_stats (
    podcast_id             BIGINT PRIMARY KEY REFERENCES podcasts(podcast_id) ON DELETE CASCADE,
    episodes_loaded        INT,
    avg_duration_seconds   NUMERIC(12, 1),
    total_duration_seconds BIGINT,
    first_pub_date         TIMESTAMPTZ,
    last_pub_date          TIMESTAMPTZ,
    episodes_per_month     NUMERIC(10, 2),
    activity_segment       TEXT
);

-- ---------------------------------------------------------------------------
-- Представления для Metabase (метрики и аналитические срезы)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_kpi AS
SELECT
    (SELECT COUNT(*) FROM podcasts)                                              AS total_podcasts,
    (SELECT COUNT(*) FROM episodes)                                              AS total_episodes,
    (SELECT ROUND(AVG(duration_seconds)) FROM episodes)                          AS avg_duration_seconds,
    (SELECT COUNT(*) FROM episodes WHERE pub_date >= NOW() - INTERVAL '30 days') AS episodes_last_30d;

CREATE OR REPLACE VIEW v_top_podcasts AS
SELECT p.podcast_id, p.title, COUNT(e.episode_key) AS episodes
FROM podcasts p
JOIN episodes e ON e.podcast_id = p.podcast_id
GROUP BY p.podcast_id, p.title
ORDER BY episodes DESC
LIMIT 10;

CREATE OR REPLACE VIEW v_monthly_publications AS
SELECT pub_month AS month, COUNT(*) AS episodes
FROM episodes
WHERE pub_date >= date_trunc('month', NOW()) - INTERVAL '5 years'
GROUP BY pub_month
ORDER BY pub_month;

CREATE OR REPLACE VIEW v_duration_distribution AS
SELECT duration_bucket, COUNT(*) AS episodes,
       CASE duration_bucket
            WHEN '< 10 мин'    THEN 1
            WHEN '10-30 мин'   THEN 2
            WHEN '30-60 мин'   THEN 3
            WHEN '60-120 мин'  THEN 4
            WHEN '> 2 ч'       THEN 5
            ELSE 6
       END AS sort_order
FROM episodes
GROUP BY duration_bucket
ORDER BY sort_order;

CREATE OR REPLACE VIEW v_activity_matrix AS
SELECT p.title, s.episodes_loaded, s.avg_duration_seconds, s.episodes_per_month, s.activity_segment
FROM podcast_stats s
JOIN podcasts p ON p.podcast_id = s.podcast_id;
