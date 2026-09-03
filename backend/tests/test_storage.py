"""P0-T8 — object store. InMemory unit test + a real MinIO round-trip (S3 path,
ADR 0001), skipped if MinIO isn't reachable from the test host."""
import uuid

import pytest

from storage import InMemoryObjectStore, S3ObjectStore, content_hash


def test_in_memory_store_roundtrip_and_copy():
    store = InMemoryObjectStore()
    store.put("drafts/x.md", "hello")
    assert store.get("drafts/x.md") == b"hello"
    store.copy("drafts/x.md", "snapshots/x.md")
    assert store.get("snapshots/x.md") == b"hello"


def test_content_hash_is_stable():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash(b"abc").startswith("sha256:")


def test_s3_store_roundtrip_against_minio():
    """Exercises the real boto3 S3 path against the local MinIO (host port 9000)."""
    pytest.importorskip("boto3")
    from botocore.exceptions import BotoCoreError, ClientError

    store = S3ObjectStore(
        bucket="sdlc-artifacts", endpoint_url="http://localhost:9000",
        region="us-east-1", access_key="minioadmin", secret_key="minioadmin",
    )
    key = f"drafts/test/{uuid.uuid4()}.md"
    snap = f"snapshots/test/{uuid.uuid4()}.md"
    try:
        store.put(key, "PRD body", content_type="text/markdown")
        assert store.get(key) == b"PRD body"
        store.copy(key, snap)
        assert store.get(snap) == b"PRD body"
        # cleanup
        store._s3.delete_object(Bucket="sdlc-artifacts", Key=key)
        store._s3.delete_object(Bucket="sdlc-artifacts", Key=snap)
    except (BotoCoreError, ClientError, OSError) as exc:
        pytest.skip(f"MinIO not reachable at localhost:9000: {exc}")
