#!/usr/bin/env python3
"""Generate a self-contained comparison of Machine Evolved progress logs."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path


PALETTE = ("#66d9ef", "#ffb454", "#8bd450", "#c792ea", "#f07178", "#82aaff")


def progress_file(path: Path) -> Path:
    return path / "progress.jsonl" if path.is_dir() else path


def load_series(path: Path, scale: float) -> list[dict[str, float | int]]:
    source = progress_file(path)
    by_generation: dict[int, dict[str, float | int]] = {}
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                generation = int(sample["generation"])
                evaluations = int(sample["evaluations"])
                best = float(sample["bestRobustFitness"])
                mean = float(sample["meanArchiveFitness"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if generation < 0 or evaluations < 0 or not all(map(math.isfinite, (best, mean))):
                continue
            by_generation[generation] = {
                "generation": generation,
                "evaluations": evaluations,
                "best": best * scale,
                "mean": mean * scale,
                "line": line_number,
            }
    points = [by_generation[key] for key in sorted(by_generation)]
    if not points:
        raise ValueError(f"No finite progress samples in {source}")
    return points


def nice_ceiling(value: float) -> float:
    if value <= 0:
        return 1
    power = 10 ** math.floor(math.log10(value))
    normalized = value / power
    step = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    return step * power


def chart_path(points: list[dict[str, float | int]], key: str, x, y, stepped: bool) -> str:
    result: list[str] = []
    for index, point in enumerate(points):
        px, py = x(float(point["generation"])), y(float(point[key]))
        if index == 0:
            result.append(f"M {px:.2f} {py:.2f}")
        elif stepped:
            result.append(f"H {px:.2f} V {py:.2f}")
        else:
            result.append(f"L {px:.2f} {py:.2f}")
    return " ".join(result)


def render_html(runs: list[tuple[str, Path, list[dict[str, float | int]]]], title: str, unit: str) -> str:
    width, height = 980, 520
    left, right, top, bottom = 72, 956, 28, 452
    max_generation = max(int(points[-1]["generation"]) for _, _, points in runs)
    max_value = nice_ceiling(max(float(point[key]) for _, _, points in runs for point in points for key in ("best", "mean")))
    x = lambda value: left + (value / max_generation) * (right - left)
    y = lambda value: bottom - (value / max_value) * (bottom - top)

    grid: list[str] = []
    for index in range(6):
        ratio = index / 5
        generation = round(max_generation * ratio)
        value = max_value * ratio
        px, py = x(generation), y(value)
        grid.append(f'<line class="grid" x1="{left}" x2="{right}" y1="{py:.2f}" y2="{py:.2f}"/>')
        grid.append(f'<text class="tick" x="{left - 10}" y="{py + 4:.2f}" text-anchor="end">{value:g} {html.escape(unit)}</text>')
        grid.append(f'<line class="axis" x1="{px:.2f}" x2="{px:.2f}" y1="{bottom}" y2="{bottom + 5}"/>')
        grid.append(f'<text class="tick" x="{px:.2f}" y="{bottom + 21}" text-anchor="middle">{generation:,}</text>')

    marks: list[str] = []
    legend: list[str] = []
    rows: list[str] = []
    for index, (label, path, points) in enumerate(runs):
        color = PALETTE[index % len(PALETTE)]
        safe_label = html.escape(label)
        marks.append(f'<path class="best" style="--series:{color}" d="{chart_path(points, "best", x, y, True)}"/>')
        marks.append(f'<path class="mean" style="--series:{color}" d="{chart_path(points, "mean", x, y, False)}"/>')
        last = points[-1]
        marks.append(f'<circle style="--series:{color}" cx="{x(float(last["generation"])):.2f}" cy="{y(float(last["best"])):.2f}" r="5"/>')
        legend.append(f'<span><i style="--series:{color}"></i>{safe_label}: solid best, dashed mean</span>')
        rows.append(
            f'<tr><th>{safe_label}</th><td>{int(last["generation"]):,}</td>'
            f'<td>{int(last["evaluations"]):,}</td><td>{float(last["best"]):.2f} {html.escape(unit)}</td>'
            f'<td>{float(last["mean"]):.2f} {html.escape(unit)}</td></tr>'
        )

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{color-scheme:light dark;--bg:#f7f8f8;--fg:#172027;--muted:#63717a;--panel:#fff;--line:#d6dde1}}
@media(prefers-color-scheme:dark){{:root{{--bg:#061018;--fg:#e9f7fc;--muted:#8ba3af;--panel:#0b1821;--line:#203541}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
main{{width:min(1100px,calc(100% - 28px));margin:28px auto}}h1{{margin:0 0 4px;font-size:clamp(24px,4vw,38px)}}p{{margin:4px 0;color:var(--muted)}}
.panel{{margin-top:20px;padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}svg{{display:block;width:100%;height:auto}}
.grid{{stroke:var(--line);stroke-width:1}}.axis{{stroke:var(--muted);stroke-width:1}}.tick{{fill:var(--muted);font:12px system-ui,sans-serif}}
.best,.mean{{fill:none;stroke:var(--series);stroke-linejoin:round}}.best{{stroke-width:3}}.mean{{stroke-width:2;stroke-dasharray:7 5;opacity:.9}}circle{{fill:var(--series);stroke:var(--panel);stroke-width:2}}
.legend{{display:flex;gap:18px;flex-wrap:wrap;margin:10px 2px 2px;color:var(--muted)}}.legend span{{display:flex;gap:7px;align-items:center}}.legend i{{width:18px;height:3px;background:var(--series)}}
.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child{{text-align:left}}thead th{{color:var(--muted)}}
</style></head><body><main><h1>{html.escape(title)}</h1><p>Best robust fitness and mean fitness of occupied MAP-Elites cells. One fitness unit is scaled to {html.escape(unit)}.</p>
<section class="panel"><svg viewBox="0 0 {width} {height}" role="img" aria-label="Training fitness comparison over generations">{''.join(grid)}<line class="axis" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/>{''.join(marks)}<text class="tick" x="{(left + right) / 2}" y="505" text-anchor="middle">Generation</text></svg><div class="legend">{''.join(legend)}</div></section>
<section class="panel table-wrap"><table><thead><tr><th>Run</th><th>Generation</th><th>Evaluations</th><th>Best</th><th>Mean</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
</main></body></html>'''


def parse_run(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator or not label.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--run must be LABEL=PATH")
    return label.strip(), Path(raw_path).expanduser()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, type=parse_run, metavar="LABEL=PATH")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="Machine Evolved training comparison")
    parser.add_argument("--scale", type=float, default=0.01, help="fitness-to-display-unit multiplier")
    parser.add_argument("--unit", default="m")
    args = parser.parse_args()
    if len(args.run) < 2:
        parser.error("provide at least two --run values")
    if not math.isfinite(args.scale) or args.scale <= 0:
        parser.error("--scale must be a positive finite number")
    runs = [(label, path, load_series(path, args.scale)) for label, path in args.run]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(render_html(runs, args.title, args.unit), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "output": str(args.output),
        "runs": [{"label": label, "source": str(progress_file(path)), "samples": len(points), "latest": points[-1]} for label, path, points in runs],
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
