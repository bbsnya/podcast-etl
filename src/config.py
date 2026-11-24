"""Параметры подключения и настройки конвейера."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}



DB_CONFIG = {
    "user": os.getenv("POSTGRES_USER", "podcast_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "podcast_pass"),
    "dbname": os.getenv("POSTGRES_DB", "podcast_dwh"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    # Для проверки сертификата используется режим verify-full.
    "sslmode": os.getenv("POSTGRES_SSLMODE", "prefer"),
    "sslrootcert": os.getenv("POSTGRES_SSLROOTCERT", "/opt/airflow/ca.crt"),
}


MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "podcast-lake")
MINIO_SECURE = _bool("MINIO_SECURE", False)
MINIO_CA_CERT = os.getenv("MINIO_CA_CERT", "/opt/airflow/ca.crt")


ITUNES_API_URL = os.getenv("ITUNES_API_URL", "https://itunes.apple.com/search")
SEARCH_TERM = os.getenv("SEARCH_TERM", "technology")
LIMIT = int(os.getenv("LIMIT", "50"))

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))
HTTP_BACKOFF = float(os.getenv("HTTP_BACKOFF", "1.0"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))
MAX_RSS_BYTES = int(os.getenv("MAX_RSS_BYTES", str(20 * 1024 * 1024)))
MAX_EPISODES_PER_FEED = int(os.getenv("MAX_EPISODES_PER_FEED", "500"))
REQUIRE_TLS = _bool("REQUIRE_TLS", True)


LOAD_MODE = os.getenv("LOAD_MODE", "incremental")
LOAD_CHUNK_SIZE = int(os.getenv("LOAD_CHUNK_SIZE", "5000"))


PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
