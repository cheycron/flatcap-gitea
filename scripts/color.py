"""Color helpers for the Flatcap Gitea build: sRGB, OKLab/OKLCH, WCAG contrast. Standard library only, deterministic."""
from __future__ import annotations

import math

RGBA = tuple[float, float, float, float]  # 0..1 each, straight (non-premultiplied) alpha


# --- parsing and formatting -------------------------------------------------

def parse(h: str) -> RGBA:
    h = h.strip().lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        raise ValueError(f"not a hex color: {h!r}")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return r, g, b, a


def is_hex(s: str) -> bool:
    s = s.strip()
    return s.startswith("#") and len(s) in (4, 5, 7, 9) and all(c in "0123456789abcdefABCDEF" for c in s[1:])


def fmt(c: RGBA, upper: bool = True) -> str:
    r, g, b, a = (min(1.0, max(0.0, v)) for v in c)
    s = "#" + "".join(f"{round(v * 255):02X}" for v in (r, g, b))
    if round(a * 255) != 255:
        s += f"{round(a * 255):02X}"
    return s if upper else s.lower()


# --- WCAG -------------------------------------------------------------------

def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(c: RGBA) -> float:
    r, g, b = (_lin(v) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: RGBA, bg: RGBA) -> float:
    """WCAG 2.x contrast ratio of two opaque colors (alpha is ignored: flatten first)."""
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def over(fg: RGBA, bg: RGBA) -> RGBA:
    """Composite fg (with its alpha) over an opaque bg."""
    a = fg[3]
    return (fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1.0)


# --- OKLab / OKLCH ----------------------------------------------------------

def to_oklab(c: RGBA) -> tuple[float, float, float]:
    r, g, b = (_lin(v) for v in c[:3])
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _rgb_unclipped(L: float, a: float, b: float) -> tuple[float, float, float]:
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def from_oklab(L: float, a: float, b: float, alpha: float = 1.0) -> RGBA:
    rgb = [min(1.0, max(0.0, v)) for v in _rgb_unclipped(L, a, b)]
    return _gam(rgb[0]), _gam(rgb[1]), _gam(rgb[2]), alpha


def to_oklch(c: RGBA) -> tuple[float, float, float]:
    L, a, b = to_oklab(c)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def from_oklch(L: float, C: float, h: float, alpha: float = 1.0) -> RGBA:
    """Chroma is reduced (never lightness or hue) until the color is inside sRGB."""
    eps = 1e-6

    def ok(c: float) -> bool:
        a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
        return all(-eps <= v <= 1 + eps for v in _rgb_unclipped(L, a, b))

    used = C
    if not ok(C):
        lo, hi = 0.0, C
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
        used = lo
    a, b = used * math.cos(math.radians(h)), used * math.sin(math.radians(h))
    return from_oklab(L, a, b, alpha)


def mix(c1: RGBA, c2: RGBA, t: float) -> RGBA:
    """Interpolate c1 -> c2 in OKLab (t = 0 gives c1, t = 1 gives c2). Alpha is interpolated linearly."""
    a, b = to_oklab(c1), to_oklab(c2)
    return from_oklab(*(a[i] + (b[i] - a[i]) * t for i in range(3)), c1[3] + (c2[3] - c1[3]) * t)
