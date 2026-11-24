"""Data Lake: слой хранения сырых и промежуточных данных в MinIO / S3 (FR-3.1)."""
import io
import json
import logging
from typing import Any, Optional

from src import config

logger = logging.getLogger(__name__)


class Storage:
    """Тонкая обёртка над клиентом MinIO. Клиент можно подменить (тесты)."""

    def __init__(self, client: Any = None, bucket: Optional[str] = None):
        self._client = client
        self.bucket = bucket or config.MINIO_BUCKET

    @property
    def client(self) -> Any:
        if self._client is None:
            from minio import Minio
            import urllib3

            http_client = None

            if config.MINIO_SECURE:
                http_client = urllib3.PoolManager(
                    cert_reqs="CERT_REQUIRED",
                    ca_certs=config.MINIO_CA_CERT,
                )

            self._client = Minio(
                config.MINIO_ENDPOINT,
                access_key=config.MINIO_ACCESS_KEY,
                secret_key=config.MINIO_SECRET_KEY,
                secure=config.MINIO_SECURE,
                http_client=http_client,
            )
        return self._client

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info("Создан бакет %s", self.bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(self.bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)
        return key

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def put_json(self, key: str, obj: Any) -> str:
        payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        return self.put_bytes(key, payload, "application/json")

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))
