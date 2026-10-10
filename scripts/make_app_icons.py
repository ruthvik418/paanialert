"""Draw the PaaniAlert app icons (a teal water drop) as PNGs in dashboard/public/icons/.

    python scripts/make_app_icons.py

Pure Python (no Pillow): the drop is the favicon's SVG path, flattened to a polygon and
filled with 8x vertical / exact horizontal anti-aliasing. Re-run it after changing the colours.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "dashboard" / "public" / "icons"
BG = (0x0D, 0x12, 0x12)     # --bg in styles.css (also the manifest's theme/background colour)
DROP = (0x56, 0xB7, 0xA7)   # --teal
SUB = 8                     # sub-rows per pixel


def drop_outline(n: int = 96) -> list[tuple[float, float]]:
    """The favicon path in a 24x24 box: M12 2 C9 7 5 10.5 5 14.5 A7 7 0 0 0 19 14.5 C19 10.5 15 7 12 2z."""
    def bezier(p0, p1, p2, p3):
        for i in range(1, n + 1):
            t = i / n
            u = 1 - t
            yield tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))

    pts = [(12.0, 2.0)]
    pts += bezier((12, 2), (9, 7), (5, 10.5), (5, 14.5))
    pts += [(12 - 7 * math.cos(a), 14.5 + 7 * math.sin(a)) for a in (math.pi * i / n for i in range(1, n + 1))]
    pts += bezier((19, 14.5), (19, 10.5), (15, 7), (12, 2))
    return pts


def rounded_square(size: float, radius: float, n: int = 24) -> list[tuple[float, float]]:
    pts = []
    for cx, cy, start in ((size - radius, radius, -90), (size - radius, size - radius, 0),
                          (radius, size - radius, 90), (radius, radius, 180)):
        pts += [(cx + radius * math.cos(math.radians(start + 90 * i / n)),
                 cy + radius * math.sin(math.radians(start + 90 * i / n))) for i in range(n + 1)]
    return pts


def coverage(poly: list[tuple[float, float]], size: int) -> list[list[float]]:
    """Fraction of each pixel inside the polygon (even-odd scanline fill)."""
    cov = [[0.0] * size for _ in range(size)]
    edges = list(zip(poly, poly[1:] + poly[:1]))
    for py in range(size):
        row = cov[py]
        for s in range(SUB):
            y = py + (s + 0.5) / SUB
            xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                        for (x0, y0), (x1, y1) in edges if (y0 <= y < y1) or (y1 <= y < y0))
            for a, b in zip(xs[::2], xs[1::2]):
                a, b = max(a, 0.0), min(b, float(size))
                for px in range(int(a), min(int(math.ceil(b)), size)):
                    row[px] += (min(b, px + 1) - max(a, px)) / SUB
    return cov


def icon(size: int, drop_height: float, full_bleed: bool) -> bytes:
    """drop_height is a fraction of the icon; the drop is centred optically (its circle sits on the centre)."""
    scale = drop_height * size / 19          # the path spans y 2..21.5
    ox = size / 2 - 12 * scale
    oy = size / 2 - 12.5 * scale
    drop = coverage([(ox + x * scale, oy + y * scale) for x, y in drop_outline()], size)
    back = None if full_bleed else coverage(rounded_square(size, size * 0.22), size)
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            d = min(drop[y][x], 1.0)
            a = 1.0 if back is None else min(back[y][x], 1.0)
            row += bytes(round(bg + (fg - bg) * d) for bg, fg in zip(BG, DROP)) + bytes([round(255 * a)])
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, height, bleed in (
        ("icon-192.png", 192, 0.62, False),
        ("icon-512.png", 512, 0.62, False),
        ("icon-maskable-512.png", 512, 0.50, True),   # stays inside the 80% safe circle
        ("apple-touch-icon.png", 180, 0.56, True),    # iOS rounds the corners itself
    ):
        (OUT / name).write_bytes(icon(size, height, bleed))
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
