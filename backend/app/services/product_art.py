"""Deterministic SVG product artwork (used for seeded products and products without photos)."""

from __future__ import annotations

import hashlib
from html import escape

PALETTES: dict[str, tuple[str, str, str]] = {
    "electronics": ("#1e3a8a", "#3b82f6", "#dbeafe"),
    "fashion": ("#831843", "#ec4899", "#fce7f3"),
    "home-kitchen": ("#7c2d12", "#f97316", "#ffedd5"),
    "sports-outdoors": ("#14532d", "#22c55e", "#dcfce7"),
    "beauty": ("#581c87", "#a855f7", "#f3e8ff"),
    "books": ("#713f12", "#eab308", "#fef9c3"),
    "toys": ("#164e63", "#06b6d4", "#cffafe"),
}
DEFAULT_PALETTE = ("#1f2937", "#6b7280", "#f3f4f6")


def _wrap(text: str, width: int = 22, max_lines: int = 3) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines


def render_product_svg(name: str, brand: str | None, root_category_slug: str | None, variant: int = 0) -> bytes:
    dark, mid, light = PALETTES.get(root_category_slug or "", DEFAULT_PALETTE)
    seed = int(hashlib.md5(f"{name}{variant}".encode(), usedforsecurity=False).hexdigest()[:8], 16)
    cx, cy, r = 420 + seed % 140, 120 + (seed >> 8) % 160, 150 + (seed >> 16) % 90
    initials = "".join(w[0] for w in (brand or name).split()[:2]).upper()
    lines = _wrap(name)
    text_y = 520 - 34 * (len(lines) - 1)
    tspans = "".join(
        f'<tspan x="48" y="{text_y + i * 34}">{escape(line)}</tspan>' for i, line in enumerate(lines)
    )
    angle = (seed >> 4) % 360
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" role="img" aria-label="{escape(name)}">
<defs>
<linearGradient id="g" gradientTransform="rotate({angle} .5 .5)"><stop offset="0" stop-color="{light}"/><stop offset="1" stop-color="#ffffff"/></linearGradient>
<linearGradient id="h" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{mid}"/><stop offset="1" stop-color="{dark}"/></linearGradient>
</defs>
<rect width="600" height="600" fill="url(#g)"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#h)" opacity="0.9"/>
<circle cx="{cx - r // 2}" cy="{cy + r // 2}" r="{r // 3}" fill="{mid}" opacity="0.35"/>
<rect x="{cx - 40}" y="{cy + r + 20}" width="120" height="12" rx="6" fill="{dark}" opacity="0.15"/>
<text x="{cx}" y="{cy + 22}" text-anchor="middle" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="72" font-weight="700" fill="#ffffff">{escape(initials)}</text>
<text x="48" y="{text_y - 58}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="20" font-weight="600" letter-spacing="3" fill="{mid}">{escape((brand or "").upper())}</text>
<text font-family="Inter,Segoe UI,Arial,sans-serif" font-size="30" font-weight="700" fill="{dark}">{tspans}</text>
</svg>"""
    return svg.encode()
