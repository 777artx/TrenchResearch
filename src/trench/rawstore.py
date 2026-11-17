"""Immutable cache of raw upstream responses.

Every HTTP response body is written once, gzipped, under
``raw/<source>/<YYYY-MM-DD>/``, and indexed in an append-only JSONL manifest.
Normalized tables carry the ``raw_sha256`` of the body they came from, so any
stored number can be traced back to the exact bytes we received.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RawRecord:
    source: str
    url: str
    params: dict
    status: int
    fetched_at: str
    sha256: str
    path: str
    n_bytes: int


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:80] or "root"


class RawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(
        self,
        *,
        source: str,
        url: str,
        endpoint: str,
        params: dict | None,
        status: int,
        body: bytes,
        fetched_at: datetime,
    ) -> RawRecord:
        sha = hashlib.sha256(body).hexdigest()
        day_dir = self.root / source / fetched_at.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        name = f"{fetched_at.strftime('%H%M%S%f')}_{_slug(endpoint)}_{sha[:12]}.json.gz"
        path = day_dir / name
        # "xb" refuses to overwrite: raw responses are immutable.
        with open(path, "xb") as fh:
            fh.write(gzip.compress(body, mtime=0))
        rec = RawRecord(
            source=source,
            url=url,
            params=dict(params or {}),
            status=status,
            fetched_at=fetched_at.isoformat(),
            sha256=sha,
            path=str(path.relative_to(self.root)),
            n_bytes=len(body),
        )
        with open(day_dir / "manifest.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec), sort_keys=True) + "\n")
        return rec

    def load(self, rec: RawRecord) -> bytes:
        return gzip.decompress((self.root / rec.path).read_bytes())
