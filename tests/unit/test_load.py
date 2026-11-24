import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")

from src import load  # noqa: E402
from src.transform import aggregate_podcast_stats, transform_episodes, transform_podcasts  # noqa: E402
from tests.conftest import count_rows  # noqa: E402
from tests.helpers import make_episode, make_itunes_podcast  # noqa: E402


def frames(n_eps=5, pid=1):
    podcasts = transform_podcasts([make_itunes_podcast(pid)])
    episodes = transform_episodes([make_episode(i) for i in range(n_eps)], pid)
    return podcasts, episodes, aggregate_podcast_stats(episodes)


def test_nan_and_na_converted_to_none():
    from src.frames import df_to_records

    df = pd.DataFrame({"a": [1.0, float("nan")], "b": pd.array([1, None], dtype="Int64"),
                       "c": pd.to_datetime([None, "2026-01-01"], utc=True)})
    recs = df_to_records(df)
    assert recs[1] == {"a": None, "b": None, "c": "2026-01-01T00:00:00+00:00"}
    assert recs[0]["c"] is None


def test_load_all_inserts(sqlite_engine):
    p, e, s = frames()
    counts = load.load_all(p, e, s, engine=sqlite_engine, mode="full")
    assert counts == {"podcasts": 1, "episodes": 5, "episodes_skipped": 0, "stats": 1}
    assert count_rows(sqlite_engine, "episodes") == 5


def test_load_is_idempotent(sqlite_engine):
    """NFR-3: многократный запуск -> одинаковый результат."""
    p, e, s = frames()
    for _ in range(3):
        load.load_all(p, e, s, engine=sqlite_engine, mode="full")
    assert count_rows(sqlite_engine, "podcasts") == 1
    assert count_rows(sqlite_engine, "episodes") == 5
    assert count_rows(sqlite_engine, "podcast_stats") == 1


def test_episodes_without_pub_date_not_duplicated(sqlite_engine):
    podcasts = transform_podcasts([make_itunes_podcast(1)])
    episodes = transform_episodes([make_episode(0, pub_date=None), make_episode(1, pub_date=None)], 1)
    for _ in range(2):
        load.load_all(podcasts, episodes, aggregate_podcast_stats(episodes), engine=sqlite_engine, mode="full")
    assert count_rows(sqlite_engine, "episodes") == 2


def test_upsert_updates_changed_episode(sqlite_engine):
    p, e, s = frames(n_eps=1)
    load.load_all(p, e, s, engine=sqlite_engine, mode="full")
    changed = transform_episodes([make_episode(0, description="Новое описание")], 1)
    load.load_all(p, changed, aggregate_podcast_stats(changed), engine=sqlite_engine, mode="full")
    import sqlalchemy as sa

    with sqlite_engine.connect() as conn:
        assert conn.execute(sa.text("SELECT description FROM episodes")).scalar() == "Новое описание"
    assert count_rows(sqlite_engine, "episodes") == 1


def test_incremental_skips_old_episodes(sqlite_engine):
    p, e, s = frames(n_eps=5)
    load.load_all(p, e, s, engine=sqlite_engine, mode="full")
    more = transform_episodes([make_episode(i) for i in range(8)], 1)      # +3 новых выпуска
    counts = load.load_all(p, more, aggregate_podcast_stats(more), engine=sqlite_engine, mode="incremental")
    assert counts["episodes"] == 4            # граничный (== watermark) + 3 новых
    assert counts["episodes_skipped"] == 4
    assert count_rows(sqlite_engine, "episodes") == 8


def test_get_watermarks(sqlite_engine):
    p, e, s = frames(n_eps=3)
    load.load_all(p, e, s, engine=sqlite_engine, mode="full")
    wm = load.get_watermarks(sqlite_engine)
    assert set(wm) == {1}
    assert wm[1] == e["pub_date"].max()


def test_filter_new_episodes_keeps_undated_and_unknown_podcasts():
    e = pd.concat([transform_episodes([make_episode(0), make_episode(1, pub_date=None)], 1),
                   transform_episodes([make_episode(0)], 2)], ignore_index=True)
    wm = {1: pd.Timestamp("2030-01-01", tz="UTC")}
    kept = load.filter_new_episodes(e, wm)
    assert len(kept) == 2                     # без даты (podcast 1) + podcast 2 без watermark


def test_empty_frames_are_noop(sqlite_engine):
    empty = pd.DataFrame()
    assert load.load_all(empty, empty, empty, engine=sqlite_engine, mode="full")["podcasts"] == 0


def test_invalid_mode_rejected(sqlite_engine):
    p, e, s = frames()
    with pytest.raises(ValueError):
        load.load_all(p, e, s, engine=sqlite_engine, mode="weird")


def test_public_wrappers(sqlite_engine):
    p, e, s = frames()
    assert load.load_podcasts(p, sqlite_engine) == 1
    assert load.load_episodes(e, sqlite_engine, mode="full") == 5
    assert load.load_episodes(e, sqlite_engine, mode="incremental") == 1     # только граничный
