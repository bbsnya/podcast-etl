import logging
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict

logger = logging.getLogger(__name__)

def fetch_podcasts_from_itunes(term: str, limit: int) -> List[Dict]:
    params = {"term": term, "media": "podcast", "limit": limit}
    try:
        response = requests.get("https://itunes.apple.com/search", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        logger.info(f"Получено подкастов из iTunes: {len(results)}")
        return results
    except Exception as e:
        logger.error(f"Ошибка при запросе к iTunes API: {e}")
        return []

def parse_rss_feed(rss_url: str) -> List[Dict]:
    episodes = []
    try:
        response = requests.get(rss_url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        channel = root.find("channel")
        if channel is None:
            return []
        
        for item in channel.findall("item"):
            title = item.findtext("title")
            pub_date = item.findtext("pubDate")
            description = item.findtext("description")
            duration = item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
            enclosure = item.find("enclosure")
            audio_url = enclosure.attrib.get("url") if enclosure is not None else None
            
            episodes.append({
                "title": title,
                "pub_date": pub_date,
                "description": description,
                "duration": duration,
                "audio_url": audio_url,
            })
        logger.info(f"Из RSS {rss_url} извлечено выпусков: {len(episodes)}")
    except Exception as e:
        logger.warning(f"Не удалось загрузить RSS {rss_url}: {e}")
    return episodes
