import io

import pytest

from src.storage import Storage


class FakeObject:
    def __init__(self, data):
        self._data = data
        self.closed = self.released = False

    def read(self):
        return self._data

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class FakeMinio:
    def __init__(self):
        self.buckets, self.objects, self.last = set(), {}, None

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, key, data, length, content_type):
        payload = data.read()
        assert len(payload) == length
        self.objects[(bucket, key)] = payload
        self.last = content_type

    def get_object(self, bucket, key):
        self.last = FakeObject(self.objects[(bucket, key)])
        return self.last


def test_ensure_bucket_creates_once():
    client = FakeMinio()
    s = Storage(client, "lake")
    s.ensure_bucket()
    s.ensure_bucket()
    assert client.buckets == {"lake"}


def test_bytes_roundtrip_releases_connection():
    client = FakeMinio()
    s = Storage(client, "lake")
    s.put_bytes("a/b.xml", b"<x/>", "application/xml")
    assert s.get_bytes("a/b.xml") == b"<x/>"
    assert client.last.closed and client.last.released


def test_json_roundtrip_unicode():
    s = Storage(FakeMinio(), "lake")
    s.put_json("k.json", {"название": "Подкаст", "n": 1})
    assert s.get_json("k.json") == {"название": "Подкаст", "n": 1}


def test_missing_key_propagates():
    with pytest.raises(KeyError):
        Storage(FakeMinio(), "lake").get_bytes("nope")
