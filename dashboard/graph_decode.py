from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=8)
def all_edges(n: int) -> tuple[tuple[int, int], ...]:
    return tuple((i, j) for i in range(1, n + 1) for j in range(1, n + 1) if i != j)


def mask_to_edges(mask: int, n: int) -> list[tuple[int, int]]:
    edges = all_edges(n)
    return [edges[k] for k in range(len(edges)) if (mask >> k) & 1]


def edges_to_mask(edges: list[tuple[int, int]], n: int) -> int:
    index = {e: k for k, e in enumerate(all_edges(n))}
    m = 0
    for e in edges:
        m |= 1 << index[e]
    return m
