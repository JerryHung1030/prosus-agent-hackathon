from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests


@dataclass(frozen=True)
class Prey:
    name: str
    price: Optional[int]
    link: str
    agency: Optional[str]
    source: str

    def __hash__(self) -> int:
        return hash(self.link)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Prey):
            return False
        return self.link == other.link


class Hunter:
    """Base class for hunters providing a shared HTTP session."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.session = requests.Session()

    def hunt(self) -> list[Prey]:
        raise NotImplementedError

    def build_json(self, prey: Prey) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        self.session.close()
