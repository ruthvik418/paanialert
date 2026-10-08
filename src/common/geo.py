"""Geohash cells for grouping reports by area.

A precision-6 cell is about 1.2 km × 0.6 km. A cell plus its 8 neighbours is a
neighbourhood-sized area that DynamoDB can query cheaply, one cell at a time.
Pure Python on purpose: no compiled dependency to break the Lambda build.
"""
from __future__ import annotations

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
PRECISION = 6


def encode(lat: float, lon: float, precision: int = PRECISION) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    bit, ch, even = 0, 0, True
    out = []
    while len(out) < precision:
        rng, val = (lon_range, lon) if even else (lat_range, lat)
        mid = (rng[0] + rng[1]) / 2
        if val >= mid:
            ch = (ch << 1) | 1
            rng[0] = mid
        else:
            ch <<= 1
            rng[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(_BASE32[ch])
            bit, ch = 0, 0
    return "".join(out)


def decode(cell: str) -> tuple[float, float, float, float]:
    """Return (lat, lon, lat_half_height, lon_half_width) of the cell's centre."""
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    even = True
    for c in cell:
        idx = _BASE32.index(c)
        for shift in range(4, -1, -1):
            rng = lon_range if even else lat_range
            mid = (rng[0] + rng[1]) / 2
            if (idx >> shift) & 1:
                rng[0] = mid
            else:
                rng[1] = mid
            even = not even
    lat = (lat_range[0] + lat_range[1]) / 2
    lon = (lon_range[0] + lon_range[1]) / 2
    return lat, lon, (lat_range[1] - lat_range[0]) / 2, (lon_range[1] - lon_range[0]) / 2


def geohash6(lat: float, lon: float) -> str:
    return encode(lat, lon, PRECISION)


def centre(cell: str) -> tuple[float, float]:
    lat, lon, _, _ = decode(cell)
    return lat, lon


def neighbourhood(cell: str) -> list[str]:
    """The cell and its 8 neighbours, the cell itself first."""
    lat, lon, dlat, dlon = decode(cell)
    cells = [cell]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            n = encode(lat + dy * 2 * dlat, lon + dx * 2 * dlon, len(cell))
            if n not in cells:
                cells.append(n)
    return cells
