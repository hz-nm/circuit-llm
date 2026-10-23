"""Min/max-preserving decimation of traces that share one x axis."""

from __future__ import annotations

from collections.abc import Sequence


def _bucket_extremes(series: Sequence[float], start: int, stop: int) -> tuple[int, int, float]:
    """Indices of the minimum and maximum of ``series[start:stop]`` and the range between them."""
    low = high = start
    for i in range(start + 1, stop):
        if series[i] < series[low]:
            low = i
        elif series[i] > series[high]:
            high = i
    return low, high, series[high] - series[low]


def _global_range(series: Sequence[float]) -> float:
    spread = max(series) - min(series)
    return spread if spread > 0 else 1.0


def decimation_indices(series: Sequence[Sequence[float]], max_points: int) -> list[int]:
    """Choose at most ``max_points`` sample indices shared by all ``series``.

    The interior is split into equal buckets and each bucket keeps two samples: the
    minimum and maximum of whichever series varies most within it (relative to that
    series' overall range), so narrow spikes survive. The end points are always kept.
    """
    if max_points < 4:
        raise ValueError("max_points must be at least 4")
    length = len(series[0]) if series else 0
    if length <= max_points:
        return list(range(length))

    spreads = [_global_range(s) for s in series]
    buckets = (max_points - 2) // 2
    interior = length - 2
    chosen: set[int] = {0, length - 1}
    for bucket in range(buckets):
        start = 1 + bucket * interior // buckets
        stop = 1 + (bucket + 1) * interior // buckets
        if start >= stop:
            continue
        best_low, best_high, best_score = start, start, -1.0
        for values, spread in zip(series, spreads, strict=True):
            low, high, local = _bucket_extremes(values, start, stop)
            if local / spread > best_score:
                best_low, best_high, best_score = low, high, local / spread
        chosen.update((best_low, best_high))
    return sorted(chosen)


def take(values: Sequence[float], indices: Sequence[int]) -> list[float]:
    return [values[i] for i in indices]
