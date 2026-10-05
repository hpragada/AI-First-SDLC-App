"""Object store for artifact bodies (#1/#3: bodies live here, not in the DB/state).

Provider-agnostic via the S3 API (ADR 0001): `S3ObjectStore` talks to MinIO locally
(endpoint set) or AWS S3 in prod (endpoint empty, IAM creds). `InMemoryObjectStore` is
for tests. Same code path either way.
"""
from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable


def content_hash(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _as_bytes(body: bytes | str) -> bytes:
    return body if isinstance(body, bytes) else body.encode("utf-8")


@runtime_checkable
class ObjectStore(Protocol):
    def put(self, key: str, body: bytes | str, content_type: str = "text/markdown") -> str: ...
    def get(self, key: str) -> bytes: ...
    def copy(self, src_key: str, dst_key: str) -> str: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class InMemoryObjectStore:
    """Test double. Not for production."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put(self, key: str, body: bytes | str, content_type: str = "text/markdown") -> str:
        self._data[key] = _as_bytes(body)
        return key

    def get(self, key: str) -> bytes:
        return self._data[key]

    def copy(self, src_key: str, dst_key: str) -> str:
        self._data[dst_key] = self._data[src_key]
        return dst_key

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._data


class S3ObjectStore:
    def __init__(
        self, *, bucket: str, endpoint_url: str = "", region: str = "us-east-1",
        access_key: str = "", secret_key: str = "",
    ) -> None:
        import boto3

        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        self._s3 = boto3.client("s3", **kwargs)
        self._bucket = bucket

    def put(self, key: str, body: bytes | str, content_type: str = "text/markdown") -> str:
        self._s3.put_object(
            Bucket=self._bucket, Key=key, Body=_as_bytes(body), ContentType=content_type
        )
        return key

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def copy(self, src_key: str, dst_key: str) -> str:
        self._s3.copy_object(
            Bucket=self._bucket,
            CopySource={"Bucket": self._bucket, "Key": src_key},
            Key=dst_key,
        )
        return dst_key

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        """Is there an object at this key? `head_object`, not `get`, so checking a 2 MB
        wireframe body costs one metadata call instead of downloading it.

        Only a genuine "not there" answers False — any other failure (credentials, network,
        a bucket that is refusing everything) is raised. Swallowing those would turn an
        outage into "this artifact has no body", which is a far more confusing thing to be
        told, and would make the caller's refusal message a lie."""
        import botocore.exceptions

        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
        except botocore.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True


def s3_from_settings() -> S3ObjectStore:
    from django.conf import settings

    return S3ObjectStore(
        bucket=settings.S3_BUCKET,
        endpoint_url=settings.S3_ENDPOINT_URL,
        region=settings.S3_REGION,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
    )
