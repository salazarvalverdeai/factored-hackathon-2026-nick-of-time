"""Draws the pitch charts as SVG from the CSVs in this folder (no data access, standard library only).

    python queries/pitch/make_charts.py

Every number in a chart is read from a `pNN_*.csv` next to this file; the chart footers cite the query by its
number (p08 = `p08_*.sql`).
Output: docs/assets/pitch/*.svg, referenced by docs/problem_in_numbers.md.
"""
import csv
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs" / "assets" / "pitch"

W = 720
SURFACE, BORDER = "#fcfcfb", "#e1e0d9"
INK, INK_2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, BLUE_TRACK, ORANGE, GRAY = "#2a78d6", "#cde2fb", "#eb6834", "#c3c2b7"
BLUE_DARK, BLUE_LIGHT = "#184f95", "#86b6ef"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def rows(name):
    with open(HERE / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def text(x, y, s, size=12, fill=INK_2, anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{escape(str(s))}</text>')


def hbar(x, y, w, h, fill, r=4):
    """Horizontal bar: square at the baseline, rounded at the data end."""
    r = min(r, w / 2, h / 2)
    return (f'<path d="M{x:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} '
            f'V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z" fill="{fill}"/>')


def swatch(x, y, fill):
    return f'<rect x="{x}" y="{y - 9}" width="10" height="10" rx="2" fill="{fill}"/>'


def save(name, height, title, subtitle, body, source):
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
        f'font-family=\'{FONT}\' role="img" aria-label="{escape(title)}">',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="8" fill="{SURFACE}" stroke="{BORDER}"/>',
        text(32, 36, title, 16, INK, weight="600"),
        text(32, 56, subtitle, 12, INK_2),
        *body,
        text(32, height - 16, source, 11, MUTED),
        "</svg>",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("\n".join(svg) + "\n", encoding="utf-8")
    print(f"wrote docs/assets/pitch/{name}")


def chart_share():
    r = rows("p01_w3_share_complaints.csv")[0]
    n, n_w3, pct = int(r["n_complaints"]), int(r["n_w3"]), float(r["pct_w3"])
    x0, width = 32, 656
    body = [
        text(32, 118, f"{pct:.1f}%", 48, INK, weight="600"),
        text(196, 98, f"{n_w3:,} of {n:,} complaints", 13, INK),
        text(196, 118, f"about {float(r['w3_per_month']):.0f} per month over {r['n_full_months']} full months", 12, INK_2),
        f'<rect x="{x0}" y="142" width="{width}" height="20" rx="4" fill="{BLUE_TRACK}"/>',
        hbar(x0, 142, width * pct / 100, 20, BLUE),
        text(x0, 184, "Unrecognized or wrongful charges (W3)", 12, INK_2),
        text(x0 + width, 184, f"All other complaints · {100 - pct:.1f}%", 12, INK_2, "end"),
    ]
    save("01_share_of_complaints.svg", 226,
         "More than a third of complaints are unrecognized or wrongful charges",
         "Share of all the bank's complaints in the dataset", body,
         "[data] p01")


def chart_contacts():
    fcr, fup, dur = (rows(f) for f in ("p02_fcr_complaint_vs_bank.csv", "p03_complaint_follow_up.csv",
                                        "p04_complaint_duration_vs_bank.csv"))
    panels = [
        ("Resolved at first contact (FCR, % of contacts)", [float(r["fcr_pct"]) for r in fcr], 100, "{:.1f}%"),
        ("Requires follow-up (% of contacts)", [float(r["follow_up_pct"]) for r in fup], 100, "{:.1f}%"),
        ("Median contact duration (minutes, scale 0–10)", [float(r["duration_p50_min"]) for r in dur], 10, "{:.2f} min"),
    ]
    x0, width = 32, 560
    body = [swatch(32, 84, BLUE), text(48, 84, "Complaint contacts (reason “Queja”)", 12, INK_2),
            swatch(280, 84, GRAY), text(296, 84, "Whole bank", 12, INK_2)]
    for i, (label, values, top, fmt) in enumerate(panels):
        y = 116 + i * 88
        body.append(text(x0, y, label, 12, INK, weight="600"))
        for j, (value, fill) in enumerate(zip(values, (BLUE, GRAY))):
            by = y + 10 + j * 20
            w = width * value / top
            body += [hbar(x0, by, w, 18, fill), text(x0 + w + 8, by + 13, fmt.format(value), 12, INK)]
        body.append(f'<line x1="{x0}" y1="{y + 6}" x2="{x0}" y2="{y + 52}" stroke="{AXIS}"/>')
    n_c, n_b = int(fcr[0]["denominator"]), int(fcr[1]["denominator"])
    save("02_complaint_contacts_vs_bank.svg", 400,
         "Complaint contacts resolve less, last longer and leave follow-up",
         f"Call-center contacts: {n_c:,} complaint contacts against {n_b:,} in the whole bank", body,
         "[data] p02 · p03 · p04")


def chart_thresholds():
    data = [(int(r["threshold"]), float(r["precision_pct"]), float(r["recall_with_score_pct"]))
            for r in rows("p08_fraud_score_thresholds.csv")]
    left, right, top, bottom = 64, 600, 112, 332
    sx = lambda v: left + (v - 20) / 75 * (right - left)
    sy = lambda v: bottom - v / 100 * (bottom - top)
    body = [f'<line x1="{left + 4}" y1="80" x2="{left + 24}" y2="80" stroke="{BLUE}" stroke-width="2"/>',
            text(left + 30, 84, "Precision: flagged transactions that are fraud", 12, INK_2),
            f'<line x1="348" y1="80" x2="368" y2="80" stroke="{ORANGE}" stroke-width="2"/>',
            text(374, 84, "Recall: frauds with a score that are flagged", 12, INK_2)]
    for v in (0, 25, 50, 75, 100):
        body += [f'<line x1="{left}" y1="{sy(v):.1f}" x2="{right}" y2="{sy(v):.1f}" stroke="{GRID}"/>',
                 text(left - 8, sy(v) + 4, f"{v}%", 11, MUTED, "end")]
    for v in (30, 50):  # zone boundaries from contracts/policies.yaml
        body.append(f'<line x1="{sx(v):.1f}" y1="{top}" x2="{sx(v):.1f}" y2="{bottom}" stroke="{AXIS}"/>')
    for v, label in ((25, "human"), (40, "medium zone"), (72.5, "high zone")):
        body.append(text(sx(v), bottom - 8, label, 11, MUTED, "middle"))
    body.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{AXIS}"/>')
    for t, _, _ in data:
        body.append(text(sx(t), bottom + 16, t, 11, MUTED, "middle"))
    body.append(text((left + right) / 2, bottom + 36, "fraud_score threshold (flag transactions at or above)", 11, MUTED, "middle"))
    for col, fill, name in ((1, BLUE, "Precision"), (2, ORANGE, "Recall")):
        pts = [(sx(d[0]), sy(d[col])) for d in data]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        body.append(f'<polyline points="{path}" fill="none" stroke="{fill}" stroke-width="2" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>')
        body += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{fill}" stroke="{SURFACE}" stroke-width="2"/>'
                 for x, y in pts]
        body.append(text(pts[-1][0] + 10, pts[-1][1] + 4, name, 12, INK))
    (x30, p30, r30), (x50, p50, r50) = data[0], data[1]
    body += [text(sx(x30) - 10, sy(p30) + 4, f"{p30:.1f}%", 12, INK, "end"),
             text(sx(x30) - 10, sy(r30) + 4, f"{r30:.1f}%", 12, INK, "end"),
             text(sx(x50), sy(p50) - 10, f"{p50:.0f}%", 12, INK, "middle"),
             text(sx(x50) + 10, sy(r50) - 6, f"{r50:.1f}%", 12, INK)]
    save("03_fraud_score_thresholds.svg", 404,
         "At a score of 50 or more every flagged transaction was fraud",
         "Historical precision and recall of the bank's fraud_score, by threshold", body,
         "[data] p08 · synthetic dataset, whole window, not a held-out set")


def chart_zones():
    thr = {int(r["threshold"]): r for r in rows("p08_fraud_score_thresholds.csv")}
    total, scored = int(thr[30]["n_frauds_all"]), int(thr[30]["n_frauds_with_score"])
    at30, at50 = int(thr[30]["n_frauds_flagged"]), int(thr[50]["n_frauds_flagged"])
    no_score = int(rows("p07_fraud_per_month.csv")[0]["n_frauds_without_score"])
    assert scored + no_score == total
    segments = [
        ("High zone · score ≥ 50", "block the card, verify, open the case", at50, BLUE_DARK, "#ffffff"),
        ("Medium zone · score 30–49", "customer confirms; analyst approves the block", at30 - at50, BLUE, "#ffffff"),
        ("Human zone · score < 30", "open the case and hand off to an analyst", scored - at30, BLUE_LIGHT, INK),
        ("Human zone · no score", "open the case and hand off to an analyst", no_score, GRAY, INK),
    ]
    x0, width, gap = 32, 656, 2
    body, x = [], x0
    for i, (_, _, n, fill, ink) in enumerate(segments):
        w = width * n / total - (gap if i < len(segments) - 1 else 0)
        body += [f'<rect x="{x:.1f}" y="84" width="{w:.1f}" height="24" rx="2" fill="{fill}"/>',
                 text(x + w / 2, 100, f"{100 * n / total:.1f}%", 12, ink, "middle", "600")]
        x += w + gap
    body += [text(50, 142, "Zone (contracts/policies.yaml)", 11, MUTED), text(236, 142, "What the system does", 11, MUTED),
             text(604, 142, "Frauds", 11, MUTED, "end"), text(688, 142, "Share", 11, MUTED, "end"),
             f'<line x1="32" y1="150" x2="688" y2="150" stroke="{GRID}"/>']
    for i, (name, action, n, fill, _) in enumerate(segments):
        y = 172 + i * 24
        body += [swatch(32, y, fill), text(50, y, name, 12, INK), text(236, y, action, 12, INK_2),
                 text(604, y, f"{n:,}", 12, INK, "end"), text(688, y, f"{100 * n / total:.1f}%", 12, INK, "end")]
    save("04_frauds_by_zone.svg", 290,
         f"Where the {total:,} labeled frauds fall in the three zones",
         "Share of all transactions labeled as fraud, by the score the bank gave them", body,
         "[data] p08 · p07")


if __name__ == "__main__":
    chart_share()
    chart_contacts()
    chart_thresholds()
    chart_zones()
