"""The suite cannot reach real object storage.

This file exists because the leak it guards against was silent for weeks. `s3_from_settings()` reads
`S3_ENDPOINT_URL` from `.env`, which is empty — documented in settings as meaning "PROD/cloud -> AWS
S3" — so every test that staged an artifact body was writing a real object into the team's own
bucket and reading it back over the internet. Nothing failed. The only symptoms were the odd
`EndpointConnectionError` that looked like a flaky test, and a suite three times slower than it
needed to be.

The autouse `object_store` fixture in `conftest.py` closes it. These two tests make sure it stays
closed, so the next person to touch the store — or to add a caller that imports the factory a
different way — finds out here rather than from a bill or a stray object.
"""
from storage import InMemoryObjectStore, s3_from_settings
from storage.object_store import S3ObjectStore


def test_the_factory_hands_out_a_test_double_not_a_live_client():
    store = s3_from_settings()

    assert isinstance(store, InMemoryObjectStore)
    assert not isinstance(store, S3ObjectStore), "a test is talking to real storage"


def test_every_caller_shares_one_store(object_store):
    """Each call must return the SAME double. A fresh one per call would make a body staged in one
    request invisible to the next, which is not how storage behaves — and tests written around that
    would be passing for the wrong reason."""
    object_store.put("k/one.md", b"# staged")

    assert s3_from_settings() is object_store
    assert s3_from_settings().get("k/one.md") == b"# staged"
