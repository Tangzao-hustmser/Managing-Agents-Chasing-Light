"""Lightweight in-process locks for critical write paths."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock, RLock
from typing import Dict, Iterator

_registry_lock = Lock()
_entity_locks: Dict[str, RLock] = {}


@contextmanager
def acquire_entity_lock(lock_key: str) -> Iterator[None]:
    """Serialize writes for one logical entity key within this process."""
    if not lock_key:
        raise ValueError("lock_key is required")

    with _registry_lock:
        lock = _entity_locks.get(lock_key)
        if lock is None:
            lock = RLock()
            _entity_locks[lock_key] = lock

    lock.acquire()
    try:
        yield
    finally:
        lock.release()
