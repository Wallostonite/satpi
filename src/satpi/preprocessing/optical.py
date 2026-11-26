"""Optical indices (pure numpy; band IO lives behind the geo extra)."""

from __future__ import annotations

import numpy as np


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """McFeeters NDWI = (G - NIR) / (G + NIR); water > ~0."""
    g = green.astype(float)
    n = nir.astype(float)
    return (g - n) / np.clip(g + n, 1e-6, None)


def mndwi(green: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """Xu MNDWI = (G - SWIR) / (G + SWIR); more robust in built-up areas."""
    g = green.astype(float)
    s = swir.astype(float)
    return (g - s) / np.clip(g + s, 1e-6, None)
