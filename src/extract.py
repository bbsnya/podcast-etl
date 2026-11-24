"""Extract: получение данных из iTunes Search API и RSS-лент."""
import logging
from itertools import islice
from typing import Any, Dict, List, Optional

import requests
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src import config
from src.exceptions import ExtractionError, InsecureFeedError

logger = logging.getLogger(__name__)

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def build_session(retries: Optional[int] = None, backoff: Optional[float] = None) -> requests.Session:
    """Создаёт HTTP-сессию с повторными запросами при временных ошибках HTTP."""
    retries = config.HTTP_RETRIES if retries is None else retries
    backoff = config.HTTP_BACKOFF if backoff is None else backoff
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=max(config.MAX_WORKERS * 2, 10))
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "podcast-etl/1.0 (educational project)"})
    return session


def fetch_podcasts_from_itunes(
    term: str,
    limit: int,
    session: Optional[requests.Session] = None,
    url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Получает список подкастов из iTunes Search API."""
    session = session or build_session()
    params = {"term": term, "media": "podcast", "entity": "podcast", "limit": limit}
    try:
        response = session.get(url or config.ITUNES_API_URL, params=params, timeout=config.HTTP_TIMEOUT)
        response.raise_for_status()
        results = response.json().get("results", [])
    except (requests.RequestException, ValueError) as exc:
        raise ExtractionError(f"iTunes API недоступен или вернул некорректный ответ: {exc}") from exc
    logger.info("Получено подкастов из iTunes: %d", len(results))
    return results


def fetch_rss_feed(
    url: str,
    session: Optional[requests.Session] = None,
    max_bytes: Optional[int] = None,
    require_tls: Optional[bool] = None,
) -> bytes:
    """Скачивает сырой XML ленты с ограничением размера."""
    session = session or build_session()
    max_bytes = config.MAX_RSS_BYTES if max_bytes is None else max_bytes
    require_tls = config.REQUIRE_TLS if require_tls is None else require_tls

    if require_tls and not url.lower().startswith("https://"):
        raise InsecureFeedError(f"Лента не поддерживает HTTPS: {url}")

    try:
        with session.get(url, timeout=config.HTTP_TIMEOUT, stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > max_bytes:
                    raise ExtractionError(f"RSS больше лимита {max_bytes} байт: {url}")
                chunks.append(chunk)
    except requests.RequestException as exc:
        raise ExtractionError(f"Не удалось загрузить RSS {url}: {exc}") from exc
    return b"".join(chunks)


def parse_rss_content(content: bytes, max_episodes: Optional[int] = None) -> Dict[str, Any]:
    """Разбирает RSS-ленту с помощью безопасного XML-парсера."""
    max_episodes = config.MAX_EPISODES_PER_FEED if max_episodes is None else max_episodes
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ExtractionError(f"Некорректный XML: {exc}") from exc

    channel = root.find("channel")
    if channel is None:
        raise ExtractionError("В RSS отсутствует элемент <channel>")

    meta = {
        "description": channel.findtext("description") or channel.findtext(f"{ITUNES_NS}summary"),
        "language": channel.findtext("language"),
    }

    episodes = []
    for item in islice(channel.findall("item"), max_episodes):
        enclosure = item.find("enclosure")
        episodes.append(
            {
                "title": item.findtext("title"),
                "guid": item.findtext("guid"),
                "pub_date": item.findtext("pubDate"),
                "description": item.findtext("description") or item.findtext(f"{ITUNES_NS}summary"),
                "duration": item.findtext(f"{ITUNES_NS}duration"),
                "audio_url": enclosure.attrib.get("url") if enclosure is not None else None,
            }
        )
    return {"channel": meta, "episodes": episodes}
