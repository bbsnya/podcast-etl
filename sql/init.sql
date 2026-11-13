CREATE TABLE IF NOT EXISTS podcasts (
    podcast_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    rss_url TEXT NOT NULL,
    episode_count INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id SERIAL PRIMARY KEY,
    podcast_id BIGINT NOT NULL REFERENCES podcasts(podcast_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    pub_date TIMESTAMP,
    description TEXT,
    duration_seconds INT,
    audio_url TEXT,
    UNIQUE(podcast_id, title, pub_date)
);

CREATE INDEX IF NOT EXISTS idx_episodes_podcast_id ON episodes(podcast_id);
