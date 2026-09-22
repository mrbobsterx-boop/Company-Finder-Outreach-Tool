"""Gzip-compressed on-disk cache of fetched HTML, keyed by URL hash.

Re-running `enrich` shouldn't re-download pages it already has — that
wastes the target site's bandwidth and slows down reruns for no benefit.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from typing import Optional


class HtmlCache:
    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.html.gz"

    def get(self, url: str) -> Optional[str]:
        path = self._path_for(url)
        if not path.exists():
            return None
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return fh.read()

    def set(self, url: str, html: str) -> None:
        path = self._path_for(url)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(html)
