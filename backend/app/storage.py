"""Evidence bytes live in MongoDB GridFS (bucket `evidence`), keyed by SHA-256.

Each original is written once, when it arrives, and never updated or deleted;
the custody chain records its hash, and verification re-hashes it from here.
GridFS is used because a single MongoDB document is capped at 16 MB and
evidence files may be up to 50 MB.
"""
import os
import tempfile
from contextlib import contextmanager
from io import BytesIO

from gridfs import GridFSBucket

from app.db import get_db

BUCKET = "evidence"


def _bucket() -> GridFSBucket:
    return GridFSBucket(get_db(), bucket_name=BUCKET)


def exists(sha: str) -> bool:
    return get_db()[f"{BUCKET}.files"].find_one({"_id": sha}, {"_id": 1}) is not None


def put(sha: str, data: bytes, filename: str, content_type: str | None = None) -> None:
    """Store an original once; identical content uploaded again shares the same bytes."""
    if not exists(sha):
        _bucket().upload_from_stream_with_id(sha, filename, BytesIO(data),
                                             metadata={"content_type": content_type, "sha256": sha})


def get(sha: str) -> bytes:
    return _bucket().open_download_stream(sha).read()


def stream(sha: str) -> BytesIO:
    return BytesIO(get(sha))


def text(sha: str, limit: int | None = None) -> str:
    data = get(sha)
    return (data[:limit] if limit else data).decode("utf-8", errors="ignore")


@contextmanager
def temp_copy(sha: str, suffix: str = ""):
    """A short-lived file copy, for tools that only accept a path (the speech-to-text subprocess)."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(get(sha))
        yield path
    finally:
        os.remove(path)
