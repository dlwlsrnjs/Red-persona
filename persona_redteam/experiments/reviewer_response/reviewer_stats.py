"""Small dependency-light statistics helpers for reviewer-response analyses."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - radius, center + radius


def exact_mcnemar(left: Sequence[bool], right: Sequence[bool]) -> dict[str, float | int]:
    if len(left) != len(right):
        raise ValueError("paired vectors have different lengths")
    left_only = sum(a and not b for a, b in zip(left, right, strict=True))
    right_only = sum(b and not a for a, b in zip(left, right, strict=True))
    discordant = left_only + right_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, k) for k in range(min(left_only, right_only) + 1)) / 2**discordant
        p_value = min(1.0, 2 * tail)
    return {
        "left_only": left_only,
        "right_only": right_only,
        "discordant": discordant,
        "p_value_two_sided_exact": p_value,
    }


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    n = len(p_values)
    order = sorted(range(n), key=p_values.__getitem__)
    adjusted = [0.0] * n
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (n - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def cochran_q(matrix: Sequence[Sequence[bool]]) -> dict[str, float | int]:
    """Cochran's Q for n matched observations by k binary conditions."""
    if not matrix or not matrix[0]:
        raise ValueError("empty matrix")
    k = len(matrix[0])
    if any(len(row) != k for row in matrix):
        raise ValueError("ragged matrix")
    columns = [sum(row[j] for row in matrix) for j in range(k)]
    rows = [sum(row) for row in matrix]
    grand = sum(columns)
    denominator = k * grand - sum(value * value for value in rows)
    q = 0.0 if denominator == 0 else (k - 1) * (k * sum(value * value for value in columns) - grand * grand) / denominator
    try:
        import mpmath

        p_value = float(mpmath.gammainc((k - 1) / 2, q / 2, mpmath.inf, regularized=True))
    except ImportError:
        p_value = float("nan")
    return {"q": q, "df": k - 1, "p_value_chi_square": p_value}


def average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for index in order[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must be nonempty and equally sized")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    left_ss = sum((a - left_mean) ** 2 for a in left)
    right_ss = sum((b - right_mean) ** 2 for b in right)
    return numerator / math.sqrt(left_ss * right_ss) if left_ss and right_ss else float("nan")


def spearman(left: Sequence[float], right: Sequence[float]) -> float:
    return pearson(average_ranks(left), average_ranks(right))


def rate_record(values: Iterable[bool]) -> dict[str, float | int | list[float]]:
    materialized = list(values)
    count = sum(materialized)
    total = len(materialized)
    low, high = wilson_interval(count, total)
    return {
        "count": count,
        "total": total,
        "rate": count / total if total else float("nan"),
        "wilson_95": [low, high],
    }


def ordinal_level_at_least(value: object, threshold: int) -> bool:
    """Parse rubric levels such as ``R3``, ``B5``, or integer-like values."""
    match = re.search(r"(\d+)", str(value))
    return bool(match and int(match.group(1)) >= threshold)
