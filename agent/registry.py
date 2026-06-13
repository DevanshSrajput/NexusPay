"""Source registry: loads x402-gated data sources from config/sources.json."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_SOURCES_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.json"


@dataclass
class DataSource:
    id: str
    endpoint: str
    price_usdc: float
    data_type: str
    quality_score: float
    description: str
    tags: list[str]
    enabled: bool = True


class SourceRegistry:
    def __init__(self, path: Path = _SOURCES_PATH):
        self._path = path
        self._sources: dict[str, DataSource] = {}
        self.reload()

    def reload(self) -> None:
        if not self._path.exists():
            self._sources = {}
            return
        raw = json.loads(self._path.read_text())
        self._sources = {
            s["id"]: DataSource(
                id=s["id"],
                endpoint=s["endpoint"],
                price_usdc=float(s["price_usdc"]),
                data_type=s["data_type"],
                quality_score=float(s["quality_score"]),
                description=s["description"],
                tags=list(s.get("tags", [])),
                enabled=bool(s.get("enabled", True)),
            )
            for s in raw.get("sources", [])
        }

    def get_all(self, enabled_only: bool = True) -> list[DataSource]:
        sources = list(self._sources.values())
        if enabled_only:
            sources = [s for s in sources if s.enabled]
        return sources

    def get_by_id(self, source_id: str) -> Optional[DataSource]:
        return self._sources.get(source_id)

    def get_by_tag(self, tag: str) -> list[DataSource]:
        tag = tag.lower()
        return [
            s
            for s in self._sources.values()
            if s.enabled and tag in [t.lower() for t in s.tags]
        ]


registry = SourceRegistry()
