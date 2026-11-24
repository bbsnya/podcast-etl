import pytest
import requests

from src import extract
from src.exceptions import ExtractionError, InsecureFeedError
from tests.helpers import ITUNES_URL, FakeResponse, FakeSession, make_episode, rss_xml


def test_fetch_itunes_ok():
    session = FakeSession({ITUNES_URL: FakeResponse(json_data={"results": [{"collectionId": 1}, {"collectionId": 2}]})})
    assert len(extract.fetch_podcasts_from_itunes("tech", 10, session)) == 2


def test_fetch_itunes_http_error_raises():
    session = FakeSession({ITUNES_URL: FakeResponse(status=503)})
    with pytest.raises(ExtractionError):
        extract.fetch_podcasts_from_itunes("tech", 10, session)


def test_fetch_itunes_connection_error_raises():
    session = FakeSession({ITUNES_URL: requests.ConnectionError("down")})
    with pytest.raises(ExtractionError):
        extract.fetch_podcasts_from_itunes("tech", 10, session)


def test_fetch_itunes_invalid_json_raises():
    session = FakeSession({ITUNES_URL: FakeResponse(json_error=True)})
    with pytest.raises(ExtractionError):
        extract.fetch_podcasts_from_itunes("tech", 10, session)


def test_fetch_rss_ok():
    url = "https://feeds.example.com/a.xml"
    session = FakeSession({url: FakeResponse(content=b"<rss/>")})
    assert extract.fetch_rss_feed(url, session) == b"<rss/>"


def test_fetch_rss_rejects_http_when_tls_required():
    with pytest.raises(InsecureFeedError):
        extract.fetch_rss_feed("http://feeds.example.com/a.xml", FakeSession({}), require_tls=True)


def test_fetch_rss_allows_http_when_tls_not_required():
    url = "http://feeds.example.com/a.xml"
    session = FakeSession({url: FakeResponse(content=b"<rss/>")})
    assert extract.fetch_rss_feed(url, session, require_tls=False) == b"<rss/>"


def test_fetch_rss_size_limit():
    url = "https://feeds.example.com/big.xml"
    session = FakeSession({url: FakeResponse(content=b"x" * 500)})
    with pytest.raises(ExtractionError):
        extract.fetch_rss_feed(url, session, max_bytes=100)


def test_fetch_rss_http_error():
    url = "https://feeds.example.com/bad.xml"
    with pytest.raises(ExtractionError):
        extract.fetch_rss_feed(url, FakeSession({url: FakeResponse(status=404)}))


def test_parse_rss_basic():
    eps = [make_episode(0), make_episode(1, duration="01:02:03")]
    parsed = extract.parse_rss_content(rss_xml(eps, language="en", description="Channel"), max_episodes=100)
    assert parsed["channel"] == {"description": "Channel", "language": "en"}
    assert len(parsed["episodes"]) == 2
    first = parsed["episodes"][0]
    assert first["title"] == "Выпуск 0"
    assert first["guid"] == "guid-0"
    assert first["audio_url"] == "https://cdn.example.com/0.mp3"
    assert parsed["episodes"][1]["duration"] == "01:02:03"


def test_parse_rss_respects_episode_limit():
    parsed = extract.parse_rss_content(rss_xml([make_episode(i) for i in range(10)]), max_episodes=3)
    assert len(parsed["episodes"]) == 3


def test_parse_rss_invalid_xml():
    with pytest.raises(ExtractionError):
        extract.parse_rss_content(b"<rss><channel>")


def test_parse_rss_without_channel():
    with pytest.raises(ExtractionError):
        extract.parse_rss_content(b"<rss></rss>")


def test_parse_rss_rejects_entity_expansion():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            b"<rss><channel><title>&b;</title></channel></rss>")
    with pytest.raises(ExtractionError):
        extract.parse_rss_content(bomb)


def test_build_session_configures_retries():
    session = extract.build_session(retries=4, backoff=0.1)
    retry = session.get_adapter("https://example.com").max_retries
    assert retry.total == 4
    assert 503 in retry.status_forcelist
