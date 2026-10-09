"""Latency statistics used for windows built from real probe results.

The percentile definition is nearest-rank on the sorted sample. It is
deterministic for a given sample, which matters because the same numbers appear
in the incident record, the demo, and the evaluation report.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence


def percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile of an already sorted sequence."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    index = max(0, min(len(sorted_values) - 1, int(round(fraction * (len(sorted_values) - 1)))))
    return float(sorted_values[index])


def summarise_durations(durations_ms: Iterable[float], error_count: int) -> Dict[str, float]:
    """Summarise raw observations.

    ``error_count`` must be supplied by the caller from the same sample set as
    ``durations_ms``; it is not inferred, so a mismatch cannot silently pass.
    """
    durations: List[float] = sorted(durations_ms)
    count = len(durations)
    if count == 0:
        return {
            "request_count": 0.0,
            "error_count": float(error_count),
            "error_rate": 0.0,
            "availability": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "mean_ms": 0.0,
            "max_ms": 0.0,
        }
    if error_count < 0 or error_count > count:
        raise ValueError("error_count must be between 0 and the sample count")

    return {
        "request_count": float(count),
        "error_count": float(error_count),
        "error_rate": error_count / count,
        "availability": (count - error_count) / count,
        "p50_ms": percentile(durations, 0.50),
        "p95_ms": percentile(durations, 0.95),
        "p99_ms": percentile(durations, 0.99),
        "mean_ms": sum(durations) / count,
        "max_ms": durations[-1],
    }
