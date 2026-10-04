"""Private, bounded S3 transfers. Synchronous SDK work runs in worker threads."""

import hashlib
from collections.abc import Iterator
from functools import lru_cache
from typing import BinaryIO

import urllib3
from minio import Minio
from minio.error import MinioException
from urllib3.exceptions import HTTPError
from urllib3.response import BaseHTTPResponse

from app.core.config import get_settings
from app.services.errors import DomainError

CHUNK_SIZE = 1024 * 1024
PREFIX = "attachments/"


class StorageUnavailable(DomainError):
    status_code = 503

    def __init__(self) -> None:
        super().__init__("Attachment storage temporarily unavailable")


class ObjectStorage:
    def __init__(self, client: Minio, bucket: str):
        self.client = client
        self.bucket = bucket

    def put(self, key: str, stream: BinaryIO, size: int) -> None:
        try:
            stream.seek(0)
            self.client.put_object(
                self.bucket,
                key,
                stream,
                size,
                content_type="application/octet-stream",
                part_size=5 * CHUNK_SIZE,
                num_parallel_uploads=1,
            )
        except (MinioException, HTTPError, OSError):
            raise StorageUnavailable() from None

    def open(self, key: str) -> BaseHTTPResponse:
        try:
            return self.client.get_object(self.bucket, key)
        except (MinioException, HTTPError, OSError):
            raise StorageUnavailable() from None

    @staticmethod
    def close(response: BaseHTTPResponse) -> None:
        response.close()
        response.release_conn()

    def copy_to(self, key: str, stream: BinaryIO) -> tuple[int, str]:
        response = self.open(key)
        digest = hashlib.sha256()
        size = 0
        try:
            while chunk := response.read(CHUNK_SIZE):
                size += len(chunk)
                if size > 25 * CHUNK_SIZE:
                    raise StorageUnavailable()
                digest.update(chunk)
                stream.write(chunk)
        except (HTTPError, OSError):
            raise StorageUnavailable() from None
        finally:
            self.close(response)
        return size, digest.hexdigest()

    def keys(self) -> Iterator[str]:
        try:
            for item in self.client.list_objects(self.bucket, prefix=PREFIX, recursive=True):
                if item.object_name:
                    yield item.object_name
        except (MinioException, HTTPError, OSError):
            raise StorageUnavailable() from None

    def abort_abandoned_parts(self) -> int:
        """Caller must hold the exclusive DB storage lock (no live publishers).

        The SDK has no public multipart maintenance API. Keep these two S3 calls
        isolated here and integration-tested against the locked SDK version.
        One bounded page per pass also avoids retaining a bucket-wide listing.
        """
        try:
            page = self.client._list_multipart_uploads(self.bucket, prefix=PREFIX, max_uploads=100)
            for upload in page.uploads:
                if upload.upload_id:
                    self.client._abort_multipart_upload(
                        self.bucket, upload.object_name, upload.upload_id
                    )
            return len(page.uploads)
        except (MinioException, HTTPError, OSError):
            raise StorageUnavailable() from None

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except (MinioException, HTTPError, OSError):
            raise StorageUnavailable() from None


@lru_cache
def get_storage() -> ObjectStorage:
    settings = get_settings()
    if not settings.s3_access_key or not settings.s3_secret_key.get_secret_value():
        raise StorageUnavailable()
    client = Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key.get_secret_value(),
        secure=settings.s3_secure,
        region="us-east-1",
        http_client=urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=5, read=settings.s3_timeout_seconds),
            retries=False,
            maxsize=settings.attachment_upload_slots + settings.attachment_download_slots,
            cert_reqs="CERT_REQUIRED",
        ),
    )
    return ObjectStorage(client, settings.s3_bucket)
