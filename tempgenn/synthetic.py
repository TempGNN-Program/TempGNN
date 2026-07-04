from __future__ import annotations

from typing import List, Tuple

import numpy as np

from .graph import TemporalGraph


def generate_synthetic_graph(
    vertices: int = 5000,
    edges: int = 50000,
    hot_fraction: float = 0.005,
    hot_endpoint_probability: float = 0.72,
    seed: int = 7,
) -> TemporalGraph:
    """Generate a temporal graph with hot-vertex overlap.

    The paper observes that a tiny set of hot vertices accounts for a large
    fraction of state/feature accesses. This generator creates that pressure
    intentionally so packet overlap is visible in board-free experiments.
    """

    if vertices < 2:
        raise ValueError("vertices must be at least 2")
    if edges < 1:
        raise ValueError("edges must be positive")

    rng = np.random.default_rng(seed)
    hot_count = max(1, int(vertices * hot_fraction))
    hot_vertices = np.arange(hot_count, dtype=np.int64)
    all_vertices = np.arange(vertices, dtype=np.int64)

    timestamps = np.cumsum(rng.exponential(scale=1.0, size=edges))
    generated: List[Tuple[int, int, float]] = []

    for ts in timestamps:
        if rng.random() < hot_endpoint_probability:
            src = int(rng.choice(hot_vertices))
        else:
            src = int(rng.choice(all_vertices))

        if rng.random() < hot_endpoint_probability:
            dst = int(rng.choice(hot_vertices))
        else:
            dst = int(rng.choice(all_vertices))

        if dst == src:
            dst = (dst + 1 + int(rng.integers(0, vertices - 1))) % vertices
        generated.append((src, dst, float(ts)))

    return TemporalGraph(generated)
