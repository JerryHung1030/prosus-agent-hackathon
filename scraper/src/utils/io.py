"""Utility helpers for atomic file IO used by the scraper."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any


write_lock = threading.Lock()


def _ensure_path(path: str | os.PathLike[str]) -> Path:
    return Path(path)


def read_json_array(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    file_path = _ensure_path(path)
    if not file_path.exists():
        return []
    try:
        with file_path.open('r', encoding='utf-8') as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        logging.warning('Could not parse %s as JSON (%s); treating as empty array.', file_path, exc)
        return []
    except OSError as exc:
        logging.warning('Could not read %s (%s); treating as empty array.', file_path, exc)
        return []

    if isinstance(data, list):
        return data

    logging.warning('Expected list in %s but found %s; treating as empty array.', file_path, type(data).__name__)
    return []


def write_json_array_atomic(path: str | os.PathLike[str], items: list[dict[str, Any]]) -> None:
    file_path = _ensure_path(path)
    tmp_path = file_path.with_name(file_path.name + '.tmp')

    file_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(items, ensure_ascii=False, indent=2)

    with write_lock:
        with tmp_path.open('w', encoding='utf-8') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, file_path)


def append_history_line(path: str | os.PathLike[str], url: str) -> None:
    file_path = _ensure_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    line = url.strip()
    if not line:
        return
    with write_lock:
        with file_path.open('a', encoding='utf-8') as handle:
            handle.write(f'{line}\n')
            handle.flush()
            os.fsync(handle.fileno())


def read_history_set(path: str | os.PathLike[str]) -> set[str]:
    file_path = _ensure_path(path)
    if not file_path.exists():
        return set()
    try:
        with file_path.open('r', encoding='utf-8') as handle:
            return {line.strip() for line in handle if line.strip()}
    except OSError as exc:
        logging.warning('Could not read history file %s (%s); returning empty set.', file_path, exc)
        return set()
