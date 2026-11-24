import pandas as pd
import pytest

pytest.importorskip("great_expectations")

from src.quality import validate_episodes, validate_podcasts  # noqa: E402
from src.transform import transform_episodes, transform_podcasts  # noqa: E402
from tests.helpers import make_episode, make_itunes_podcast  # noqa: E402


def good_podcasts():
    return transform_podcasts([make_itunes_podcast(1), make_itunes_podcast(2)])


def good_episodes():
    return transform_episodes([make_episode(i) for i in range(5)], 1)


def test_valid_podcasts_pass():
    report = validate_podcasts(good_podcasts())
    assert report.passed, report.critical_failures
    assert report.checked >= 6


def test_valid_episodes_pass():
    report = validate_episodes(good_episodes())
    assert report.passed, report.critical_failures


def test_empty_frames_fail():
    assert not validate_podcasts(pd.DataFrame()).passed
    assert not validate_episodes(pd.DataFrame()).passed


def test_podcasts_null_title_detected():
    df = good_podcasts()
    df.loc[0, "title"] = None
    report = validate_podcasts(df)
    assert not report.passed
    assert any("title" in f for f in report.critical_failures)


def test_podcasts_duplicate_id_detected():
    df = pd.concat([good_podcasts(), good_podcasts()], ignore_index=True)
    assert any("уникален" in f for f in validate_podcasts(df).critical_failures)


def test_podcasts_bad_url_detected():
    df = good_podcasts()
    df.loc[0, "rss_url"] = "ftp://bad"
    assert any("URL" in f for f in validate_podcasts(df).critical_failures)


def test_episodes_negative_duration_detected():
    df = good_episodes()
    df["duration_seconds"] = df["duration_seconds"].astype("float64")
    df.loc[0, "duration_seconds"] = -5
    assert any("длительность" in f for f in validate_episodes(df).critical_failures)


def test_episodes_duplicate_key_detected():
    df = pd.concat([good_episodes(), good_episodes()], ignore_index=True)
    assert any("episode_key уникален" in f for f in validate_episodes(df).critical_failures)


def test_episodes_missing_dates_only_warning():
    df = good_episodes()
    df["pub_date"] = pd.NaT
    report = validate_episodes(df)
    assert report.passed                       # критических нет
    assert any("pub_date" in w for w in report.warnings)


def test_report_serializable():
    data = validate_podcasts(good_podcasts()).to_dict()
    assert data["passed"] is True and data["dataset"] == "podcasts"
