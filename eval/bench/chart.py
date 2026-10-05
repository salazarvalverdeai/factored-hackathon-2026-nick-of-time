"""Cost-versus-quality chart of B1 as a static SVG (spec 15 AC-04): one point per measured arm with its p95, the
Pareto frontier highlighted and direct-labeled, the others named in a hover title. Brand colors (docs/brand/BRAND.md)."""
from __future__ import annotations

import math
from html import escape

W, H, L, R, T, B = 760, 460, 70, 190, 64, 58
INK, MUTED, GRID, FRONTIER, OTHER, SURFACE = "#111827", "#64748B", "#E2E8F0", "#7C3AED", "#8391A7", "#FFFFFF"
ZERO_GAP = 36                                    # px left of the log axis where the no-cost arms sit


def svg(rows: list[dict], subtitle: str) -> str:
    pts = [r for r in rows if r.get("metrics") and r["metrics"]["accuracy"]["value"] is not None]
    costs = [r["metrics"]["cost_per_1000_usd"] for r in pts if r["metrics"]["cost_per_1000_usd"]]
    lo, hi = (math.log10(min(costs)) - 0.2, math.log10(max(costs)) + 0.2) if costs else (-2, 1)
    accs = [r["metrics"]["accuracy"]["ci_low"] for r in pts] or [0.5]
    y0 = max(0.0, math.floor(min(accs) * 10) / 10)

    def x(c):
        return L + (0 if not c else ZERO_GAP + (W - L - R - ZERO_GAP) * (math.log10(c) - lo) / (hi - lo))

    def y(a):
        return T + (H - T - B) * (1 - (a - y0) / (1 - y0))

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Sora, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
           f'<text x="{L}" y="24" font-size="15" font-weight="600" fill="{INK}">B1 understand: cost vs accuracy</text>',
           f'<text x="{L}" y="42" font-size="11" fill="{MUTED}">{escape(subtitle)}</text>']
    for k in range(int(y0 * 10), 11):
        yy = y(k / 10)
        out += [f'<line x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{GRID}"/>',
                f'<text x="{L - 8}" y="{yy + 4:.1f}" font-size="10" fill="{MUTED}" text-anchor="end">{k / 10:.1f}</text>']
    ticks = [(0, "0")] + [(10 ** e, f"{10 ** e:g}") for e in range(math.ceil(lo), math.floor(hi) + 1)]
    for c, label in ticks:
        out.append(f'<text x="{x(c):.1f}" y="{H - B + 16}" font-size="10" fill="{MUTED}" text-anchor="middle">{label}</text>')
    out += [f'<text x="{(L + W - R) / 2}" y="{H - 16}" font-size="11" fill="{MUTED}" text-anchor="middle">'
            'USD per 1,000 messages (log scale; 0 = no LLM)</text>',
            f'<text transform="translate(18 {(T + H - B) / 2}) rotate(-90)" font-size="11" fill="{MUTED}" '
            'text-anchor="middle">Intent accuracy (95% Wilson CI)</text>']
    front = sorted((r for r in pts if r.get("pareto")), key=lambda r: r["metrics"]["cost_per_1000_usd"])
    if len(front) > 1:
        line = " ".join(f'{x(r["metrics"]["cost_per_1000_usd"]):.1f},{y(r["metrics"]["accuracy"]["value"]):.1f}'
                        for r in front)
        out.append(f'<polyline points="{line}" fill="none" stroke="{FRONTIER}" stroke-width="2" stroke-opacity="0.5"/>')
    for r in sorted(pts, key=lambda r: bool(r.get("pareto"))):
        m = r["metrics"]
        px, py, color = x(m["cost_per_1000_usd"]), y(m["accuracy"]["value"]), FRONTIER if r.get("pareto") else OTHER
        tip = (f'{r["arm"]}: accuracy {m["accuracy"]["value"]}, USD {m["cost_per_1000_usd"]} per 1k, '
               f'p95 {m["p95_ms"]} ms')
        out += [f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{y(m["accuracy"]["ci_low"]):.1f}" '
                f'y2="{y(m["accuracy"]["ci_high"]):.1f}" stroke="{color}" stroke-opacity="0.35"/>',
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{color}" stroke="{SURFACE}" stroke-width="2">'
                f'<title>{escape(tip)}</title></circle>']
        if r.get("pareto"):
            out.append(f'<text x="{px + 9:.1f}" y="{py + 4:.1f}" font-size="10" fill="{INK}">'
                       f'{escape(r["arm"])} · p95 {m["p95_ms"]:g} ms</text>')
    lx = W - R + 20
    for i, (color, name) in enumerate(((FRONTIER, "Pareto frontier"), (OTHER, "Other arms (hover for p95)"))):
        out += [f'<circle cx="{lx}" cy="{T + 8 + 20 * i}" r="5" fill="{color}"/>',
                f'<text x="{lx + 10}" y="{T + 12 + 20 * i}" font-size="10" fill="{INK}">{name}</text>']
    return "\n".join(out + ["</svg>"]) + "\n"
