import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "user": os.getenv("POSTGRES_USER", "podcast_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "podcast_pass"),
    "dbname": os.getenv("POSTGRES_DB", "podcast_dwh"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

ITUNES_API_URL = os.getenv("ITUNES_API_URL", "https://itunes.apple.com/search")
SEARCH_TERM = os.getenv("SEARCH_TERM", "technology")
LIMIT = int(os.getenv("LIMIT", "50"))
