from __future__ import annotations

from typing import Collection

from hunters.hunter import Prey
from utils.io import append_history_line, read_history_set


class History:
    """URL-only history file helper."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._cache = read_history_set(self.file_path)

    def get_all(self) -> set[str]:
        return set(self._cache)

    def filter(self, preys: Collection[Prey]) -> list[Prey]:
        return [prey for prey in preys if prey.link not in self._cache]

    def add(self, url: str) -> None:
        if url in self._cache:
            return
        append_history_line(self.file_path, url)
        self._cache.add(url)
