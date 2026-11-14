"""Ellipse fitting and head-circumference measurement for HC18 (shared by preparation, evaluation and serving).

A direct least-squares ellipse fit (Fitzgibbon, Pilu and Fisher 1999; Halir and Flusser's stable form) to boundary
points; circumference by Ramanujan's approximation, converted to millimetres with the image's own pixel size. Points on
the image border are excluded, so a head that leaves the image is still fitted by its visible outline.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage


def fit_ellipse(points_xy: np.ndarray) -> dict:
    x, y = points_xy[:, 0].astype(float), points_xy[:, 1].astype(float)
    mx, my = x.mean(), y.mean()
    scale = max(x.std(), y.std(), 1e-9)
    u, v = (x - mx) / scale, (y - my) / scale
    d1 = np.stack([u * u, u * v, v * v], axis=1)
    d2 = np.stack([u, v, np.ones_like(u)], axis=1)
    s1, s2, s3 = d1.T @ d1, d1.T @ d2, d2.T @ d2
    t = -np.linalg.solve(s3, s2.T)
    m = s1 + s2 @ t
    m = np.array([m[2] / 2, -m[1], m[0] / 2])
    _, vectors = np.linalg.eig(m)
    vectors = vectors.real
    condition = 4 * vectors[0] * vectors[2] - vectors[1] ** 2
    candidates = np.flatnonzero(condition > 0)
    if not len(candidates):
        raise ValueError("no ellipse fits these points")
    a1 = vectors[:, candidates[0]]
    a, b, c, d, e, f = np.concatenate([a1, t @ a1])
    denominator = b * b - 4 * a * c
    u0, v0 = (2 * c * d - b * e) / denominator, (2 * a * e - b * d) / denominator
    f0 = a * u0 * u0 + b * u0 * v0 + c * v0 * v0 + d * u0 + e * v0 + f
    eigenvalues = np.linalg.eigvalsh(np.array([[a, b / 2], [b / 2, c]]))
    if np.any(-f0 / eigenvalues <= 0):
        raise ValueError("degenerate conic")
    semi_axes = np.sqrt(-f0 / eigenvalues) * scale
    return {"coefficients": [a, b, c, d, e, f], "centre": (u0 * scale + mx, v0 * scale + my), "semi_axes_px": sorted(semi_axes.tolist()),
            "normalisation": (mx, my, scale)}


def boundary_points(mask: np.ndarray) -> np.ndarray:
    """Boundary pixels of a binary mask, without pixels on the image border."""
    edge = mask & ~ndimage.binary_erosion(mask)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = False
    ys, xs = np.nonzero(edge)
    return np.stack([xs, ys], axis=1)


def filled_mask(shape: tuple[int, int], ellipse: dict) -> np.ndarray:
    a, b, c, d, e, f = ellipse["coefficients"]
    mx, my, scale = ellipse["normalisation"]
    gy, gx = np.mgrid[0:shape[0], 0:shape[1]]
    u, v = (gx - mx) / scale, (gy - my) / scale
    value = a * u * u + b * u * v + c * v * v + d * u + e * v + f
    centre_value = np.sign(a * ((ellipse["centre"][0] - mx) / scale) ** 2 + 0)  # placeholder, replaced below
    cu, cv = (ellipse["centre"][0] - mx) / scale, (ellipse["centre"][1] - my) / scale
    centre_value = a * cu * cu + b * cu * cv + c * cv * cv + d * cu + e * cv + f
    return np.sign(value) == np.sign(centre_value)


def circumference_mm(ellipse: dict, pixel_size_mm: float) -> float:
    a, b = ellipse["semi_axes_px"]
    perimeter = math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))
    return perimeter * pixel_size_mm
