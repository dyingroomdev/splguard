from __future__ import annotations

import itertools
import time
from collections import Counter
from typing import Mapping


_COUNTERS: Counter[str] = Counter()
_START_TIME = time.time()


def increment(name: str, value: int = 1) -> None:
    if value:
        _COUNTERS[name] += value


def get_counters() -> Mapping[str, int]:
    return dict(_COUNTERS)


def set_value(name: str, value: int) -> None:
    _COUNTERS[name] = value


def reset_counters() -> None:
    _COUNTERS.clear()


def uptime_seconds() -> float:
    return max(0.0, time.time() - _START_TIME)
