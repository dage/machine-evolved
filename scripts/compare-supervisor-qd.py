#!/usr/bin/env python3
"""Build self-contained raw-QD comparisons from supervisor metrics JSONL."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
from pathlib import Path
from typing import Any


PALETTE = (
    "#2563eb",
    "#dc2626",
    "#059669",
    "#7c3aed",
    "#d97706",
    "#0891b2",
    "#be185d",
    "#4d7c0f",
)

AXES = {
    "candidateEvaluations": {
        "sampleKey": "evaluations",
        "title": "Candidate evaluations",
        "file": "qd-vs-candidate-evaluations.html",
        "unit": "candidate evaluations",
    },
    "domainSimulations": {
        "sampleKey": "domainSimulations",
        "title": "Domain simulations",
        "file": "qd-vs-domain-simulations.html",
        "unit": "domain simulations",
    },
    "elapsedWallSeconds": {
        "sampleKey": None,
        "title": "Elapsed wall time",
        "file": "qd-vs-elapsed-wall-time.html",
        "unit": "seconds",
    },
}


def increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def nonnegative_count(value: Any) -> int | None:
    number = finite_number(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def capture_epoch(sample: dict[str, Any]) -> float | None:
    epoch = finite_number(sample.get("capturedAtEpochSeconds"))
    if epoch is not None and epoch >= 0:
        return epoch
    captured_at = sample.get("capturedAt")
    if not isinstance(captured_at, str) or not captured_at.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        epoch = parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return None
    return epoch if math.isfinite(epoch) and epoch >= 0 else None


def route_identity(sample: dict[str, Any]) -> tuple[str | None, str | None]:
    route = sample.get("route") if isinstance(sample.get("route"), dict) else {}
    route_id = sample.get("activeRouteId") or sample.get("routeId") or route.get("id")
    route_label = (
        sample.get("activeRouteLabel")
        or sample.get("routeLabel")
        or route.get("label")
        or route.get("phase")
    )
    route_id = str(route_id).strip() if route_id is not None else None
    route_label = str(route_label).strip() if route_label is not None else None
    return route_id or None, route_label or None


def parse_source(value: str) -> dict[str, Any]:
    label, separator, raw_path = value.partition("=")
    if separator:
        if not label.strip() or not raw_path.strip():
            raise argparse.ArgumentTypeError("--source must be [LABEL=]PATH")
        path = Path(raw_path).expanduser()
        return {"label": label.strip(), "path": path, "explicitLabel": True}
    if not value.strip():
        raise argparse.ArgumentTypeError("--source must be [LABEL=]PATH")
    path = Path(value).expanduser()
    inferred = path.parent.name if path.name == "metrics.jsonl" else path.stem
    return {"label": inferred or "metrics", "path": path, "explicitLabel": False}


def parse_route_selector(value: str) -> dict[str, str]:
    selector, separator, label = value.partition("=")
    if not selector.strip() or (separator and not label.strip()):
        raise argparse.ArgumentTypeError("--route must be ROUTE_ID_OR_LABEL[=DISPLAY_LABEL]")
    return {"selector": selector.strip(), "label": label.strip() if separator else selector.strip()}


def selector_for(
    route_id: str | None,
    route_label: str | None,
    selectors: list[dict[str, str]],
) -> dict[str, str] | None:
    matches = [item for item in selectors if item["selector"] in (route_id, route_label)]
    if len(matches) > 1 and len({item["label"] for item in matches}) > 1:
        raise ValueError(f"Route {route_id or route_label!r} matches conflicting display labels")
    return matches[0] if matches else None


def sample_signature(sample: dict[str, Any]) -> tuple[Any, ...]:
    return (
        sample["capturedAtEpochSeconds"],
        sample["evaluations"],
        sample["domainSimulations"],
        sample["rawQdScore"],
        sample["occupiedCells"],
        sample["bestFitness"],
    )


def load_source(
    source: dict[str, Any],
    selectors: list[dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = source["path"]
    source_summary = {
        "label": source["label"],
        "path": str(path),
        "lineCounts": {"total": 0, "blank": 0, "decodedObjects": 0},
        "includedCoreSamples": 0,
        "exclusions": {},
    }
    grouped: dict[str, dict[str, Any]] = {}

    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            source_summary["lineCounts"]["total"] += 1
            if not line.strip():
                source_summary["lineCounts"]["blank"] += 1
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                increment(source_summary["exclusions"], "malformedJson")
                continue
            if not isinstance(raw, dict):
                increment(source_summary["exclusions"], "nonObjectJson")
                continue
            source_summary["lineCounts"]["decodedObjects"] += 1
            route_id, route_label = route_identity(raw)
            if route_id is None and route_label is None:
                increment(source_summary["exclusions"], "missingRouteIdentity")
                continue
            selected = selector_for(route_id, route_label, selectors)
            if selectors and selected is None:
                increment(source_summary["exclusions"], "routeFiltered")
                continue
            captured_epoch = capture_epoch(raw)
            if captured_epoch is None:
                increment(source_summary["exclusions"], "invalidCapturedAt")
                continue
            qd = raw.get("qd")
            raw_qd = finite_number(qd.get("qdScore")) if isinstance(qd, dict) else None
            if raw_qd is None:
                increment(source_summary["exclusions"], "missingOrInvalidRawQd")
                continue

            identity = route_id or f"label:{route_label}"
            group = grouped.setdefault(identity, {
                "routeId": route_id,
                "routeLabel": route_label,
                "displayRouteLabel": selected["label"] if selected else (route_label or route_id),
                "samples": [],
                "exclusions": {},
            })
            if route_label and group["routeLabel"] is None:
                group["routeLabel"] = route_label
            sample = {
                "capturedAt": raw.get("capturedAt"),
                "capturedAtEpochSeconds": captured_epoch,
                "evaluations": nonnegative_count(raw.get("evaluations")),
                "domainSimulations": nonnegative_count(raw.get("domainSimulations")),
                "rawQdScore": raw_qd,
                "occupiedCells": nonnegative_count(qd.get("occupiedCells")) if isinstance(qd, dict) else None,
                "bestFitness": finite_number(qd.get("bestFitness")) if isinstance(qd, dict) else None,
                "line": line_number,
            }
            samples = group["samples"]
            if samples and captured_epoch < samples[-1]["capturedAtEpochSeconds"]:
                increment(group["exclusions"], "staleCapturedAt")
                increment(source_summary["exclusions"], "staleCapturedAt")
                continue
            if samples and captured_epoch == samples[-1]["capturedAtEpochSeconds"]:
                if sample_signature(sample) == sample_signature(samples[-1]):
                    reason = "duplicateSample"
                else:
                    reason = "duplicateCapturedAtReplaced"
                    samples[-1] = sample
                increment(group["exclusions"], reason)
                increment(source_summary["exclusions"], reason)
                continue
            samples.append(sample)

    groups = []
    for identity, group in grouped.items():
        source_summary["includedCoreSamples"] += len(group["samples"])
        group.update({
            "identity": identity,
            "sourceLabel": source["label"],
            "sourcePath": str(path),
            "seriesLabel": f'{source["label"]} / {group["displayRouteLabel"]}',
        })
        groups.append(group)
    groups.sort(key=lambda item: (item["seriesLabel"], item["identity"]))
    return source_summary, groups


def trapezoidal_auc(points: list[dict[str, float]]) -> float:
    return sum(
        (right["x"] - left["x"]) * (right["rawQdScore"] + left["rawQdScore"]) / 2
        for left, right in zip(points, points[1:])
    )


def monotonic_axis(
    samples: list[dict[str, Any]],
    axis_name: str,
) -> tuple[list[dict[str, float]], dict[str, int]]:
    axis = AXES[axis_name]
    exclusions: dict[str, int] = {}
    points: list[dict[str, float]] = []
    origin = samples[0]["capturedAtEpochSeconds"] if samples else 0.0
    for sample in samples:
        if axis["sampleKey"] is None:
            x_value = sample["capturedAtEpochSeconds"] - origin
        else:
            x_value = sample[axis["sampleKey"]]
            if x_value is None:
                increment(exclusions, "missingX")
                continue
        point = {
            "x": float(x_value),
            "rawQdScore": float(sample["rawQdScore"]),
            "capturedAtEpochSeconds": float(sample["capturedAtEpochSeconds"]),
        }
        if points and point["x"] < points[-1]["x"]:
            increment(exclusions, "staleX")
            continue
        if points and point["x"] == points[-1]["x"]:
            if point["rawQdScore"] == points[-1]["rawQdScore"]:
                increment(exclusions, "duplicateX")
            else:
                increment(exclusions, "duplicateXReplaced")
                points[-1] = point
            continue
        points.append(point)
    return points, exclusions


def axis_summary(points: list[dict[str, float]], exclusions: dict[str, int], unit: str) -> dict[str, Any]:
    first_x = points[0]["x"] if points else None
    last_x = points[-1]["x"] if points else None
    return {
        "pointCount": len(points),
        "xUnit": unit,
        "xStart": first_x,
        "xEnd": last_x,
        "xSpan": last_x - first_x if points else None,
        "trapezoidalRawQdAuc": trapezoidal_auc(points),
        "aucUnit": f"raw QD score * {unit}",
        "exclusions": exclusions,
    }


def build_report_data(
    sources: list[dict[str, Any]],
    selectors: list[dict[str, str]],
    generated_at: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_summaries = []
    groups = []
    labels = set()
    for source in sources:
        if source["label"] in labels:
            raise ValueError(f"Duplicate source label: {source['label']}")
        labels.add(source["label"])
        summary, loaded_groups = load_source(source, selectors)
        source_summaries.append(summary)
        groups.extend(loaded_groups)
    if not groups:
        raise ValueError("No valid raw-QD samples matched the selected routes")

    route_summaries = []
    chart_routes = []
    for group in groups:
        samples = group["samples"]
        axes = {}
        chart_axes = {}
        for axis_name, definition in AXES.items():
            points, exclusions = monotonic_axis(samples, axis_name)
            axes[axis_name] = axis_summary(points, exclusions, definition["unit"])
            chart_axes[axis_name] = points
        final = samples[-1]
        candidate_points = chart_axes["candidateEvaluations"]
        domain_points = chart_axes["domainSimulations"]
        elapsed_points = chart_axes["elapsedWallSeconds"]
        route_summaries.append({
            "seriesLabel": group["seriesLabel"],
            "sourceLabel": group["sourceLabel"],
            "sourcePath": group["sourcePath"],
            "routeId": group["routeId"],
            "routeLabel": group["routeLabel"],
            "displayRouteLabel": group["displayRouteLabel"],
            "sampleCounts": {
                "includedCoreSamples": len(samples),
                "coreExclusions": group["exclusions"],
            },
            "finalPrimaryMetrics": {
                "rawQdScore": final["rawQdScore"],
                "candidateEvaluations": candidate_points[-1]["x"] if candidate_points else None,
                "domainSimulations": domain_points[-1]["x"] if domain_points else None,
                "elapsedWallSeconds": elapsed_points[-1]["x"] if elapsed_points else None,
                "capturedAt": final["capturedAt"],
                "capturedAtEpochSeconds": final["capturedAtEpochSeconds"],
            },
            "finalDiagnostics": {
                "occupiedCells": final["occupiedCells"],
                "bestFitness": final["bestFitness"],
            },
            "rawQdAuc": axes,
        })
        chart_routes.append({
            "seriesLabel": group["seriesLabel"],
            "sourceLabel": group["sourceLabel"],
            "routeId": group["routeId"],
            "displayRouteLabel": group["displayRouteLabel"],
            "axes": chart_axes,
            "summary": route_summaries[-1],
        })

    report = {
        "schemaVersion": 1,
        "generatedAt": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        "primaryMetric": {
            "name": "rawQdScore",
            "sourceField": "qd.qdScore",
            "description": "Sum of finite occupied-cell fitness values; no normalized QD metric is substituted.",
        },
        "comparisonAxes": list(AXES),
        "generationUsedForComparison": False,
        "sourceCounts": source_summaries,
        "routes": route_summaries,
    }
    return report, chart_routes


def nice_step(span: float, target_ticks: int = 5) -> float:
    if not math.isfinite(span) or span <= 0:
        return 1.0
    rough = span / target_ticks
    power = 10 ** math.floor(math.log10(rough))
    normalized = rough / power
    multiplier = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    return multiplier * power


def tick_values(lower: float, upper: float) -> list[float]:
    step = nice_step(upper - lower)
    start = math.floor(lower / step) * step
    end = math.ceil(upper / step) * step
    values = []
    value = start
    while value <= end + step * 0.01 and len(values) < 20:
        values.append(value)
        value += step
    return values


def compact_number(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.3g}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.3g}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.3g}k"
    return f"{value:.4g}"


def format_elapsed(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.2f}h"
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    return f"{seconds:.0f}s"


def render_chart(title: str, axis_name: str, routes: list[dict[str, Any]]) -> str:
    width, height = 1120, 620
    left, right, top, bottom = 92.0, 1084.0, 36.0, 520.0
    plotted = [(route, route["axes"][axis_name]) for route in routes if route["axes"][axis_name]]
    all_points = [point for _, points in plotted for point in points]
    x_upper = max((point["x"] for point in all_points), default=1.0)
    if x_upper <= 0:
        x_upper = 1.0
    y_values = [point["rawQdScore"] for point in all_points] or [0.0, 1.0]
    y_lower = min(0.0, min(y_values))
    y_upper = max(0.0, max(y_values))
    if y_lower == y_upper:
        padding = max(1.0, abs(y_lower) * 0.1)
        y_lower -= padding
        y_upper += padding
    x_map = lambda value: left + value / x_upper * (right - left)
    y_map = lambda value: bottom - (value - y_lower) / (y_upper - y_lower) * (bottom - top)

    grid = []
    for value in tick_values(y_lower, y_upper):
        if value < y_lower - 1e-9 or value > y_upper + 1e-9:
            continue
        py = y_map(value)
        grid.append(f'<line class="grid" x1="{left}" x2="{right}" y1="{py:.2f}" y2="{py:.2f}"/>')
        grid.append(f'<text class="tick" x="{left - 12}" y="{py + 4:.2f}" text-anchor="end">{html.escape(compact_number(value))}</text>')
    for index in range(6):
        value = x_upper * index / 5
        px = x_map(value)
        label = format_elapsed(value) if axis_name == "elapsedWallSeconds" else compact_number(value)
        grid.append(f'<line class="axis" x1="{px:.2f}" x2="{px:.2f}" y1="{bottom}" y2="{bottom + 6}"/>')
        grid.append(f'<text class="tick" x="{px:.2f}" y="{bottom + 24}" text-anchor="middle">{html.escape(label)}</text>')

    marks = []
    legend = []
    rows = []
    for index, (route, points) in enumerate(plotted):
        color = PALETTE[index % len(PALETTE)]
        path = " ".join(
            ("M" if point_index == 0 else "L")
            + f' {x_map(point["x"]):.2f} {y_map(point["rawQdScore"]):.2f}'
            for point_index, point in enumerate(points)
        )
        label = html.escape(route["seriesLabel"])
        marks.append(f'<path class="series" style="--series:{color}" d="{path}"/>')
        last = points[-1]
        marks.append(
            f'<circle style="--series:{color}" cx="{x_map(last["x"]):.2f}" '
            f'cy="{y_map(last["rawQdScore"]):.2f}" r="4.5"/>'
        )
        legend.append(f'<span><i style="--series:{color}"></i>{label}</span>')
        axis = route["summary"]["rawQdAuc"][axis_name]
        rows.append(
            f'<tr><th>{label}</th><td>{len(points):,}</td><td>{compact_number(last["x"])}</td>'
            f'<td>{compact_number(last["rawQdScore"])}</td>'
            f'<td>{compact_number(axis["trapezoidalRawQdAuc"])}</td></tr>'
        )
    empty_note = '<p class="empty">No valid points were available for this axis.</p>' if not plotted else ""
    axis_title = AXES[axis_name]["title"]
    generated_rows = "".join(rows)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — Raw QD vs {html.escape(axis_title)}</title><style>
:root{{color-scheme:light dark;--bg:#f4f7fb;--fg:#172033;--muted:#617087;--panel:#fff;--line:#d8e0ea}}
@media(prefers-color-scheme:dark){{:root{{--bg:#08111d;--fg:#e7eef9;--muted:#96a6bb;--panel:#101b2a;--line:#29384c}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
main{{width:min(1220px,calc(100% - 28px));margin:28px auto 48px}}h1{{margin:0;font-size:clamp(25px,4vw,40px)}}
p{{margin:5px 0;color:var(--muted)}}.panel{{margin-top:20px;padding:17px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}}
svg{{display:block;width:100%;height:auto}}.grid{{stroke:var(--line);stroke-width:1}}.axis{{stroke:var(--muted)}}
.tick{{fill:var(--muted);font:12px system-ui,sans-serif}}.series{{fill:none;stroke:var(--series);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}}
circle{{fill:var(--series);stroke:var(--panel);stroke-width:2}}.legend{{display:flex;gap:18px;flex-wrap:wrap;margin:8px 4px 0;color:var(--muted)}}
.legend span{{display:flex;gap:7px;align-items:center}}.legend i{{width:20px;height:3px;background:var(--series)}}.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child{{text-align:left}}thead th{{color:var(--muted)}}.empty{{padding:40px;text-align:center}}
</style></head><body><main><h1>{html.escape(title)}</h1><p>Raw QD score vs {html.escape(axis_title.lower())}. Raw <code>qd.qdScore</code> is the primary outcome; samples are filtered and deduplicated without using generation.</p>
<section class="panel">{empty_note}<svg viewBox="0 0 {width} {height}" role="img" aria-label="Raw QD score by {html.escape(axis_title.lower())}">{''.join(grid)}<line class="axis" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/><line class="axis" x1="{left}" x2="{left}" y1="{top}" y2="{bottom}"/>{''.join(marks)}<text class="tick" x="{(left + right) / 2}" y="575" text-anchor="middle">{html.escape(axis_title)}</text><text class="tick" transform="translate(22 {(top + bottom) / 2}) rotate(-90)" text-anchor="middle">Raw QD score</text></svg><div class="legend">{''.join(legend)}</div></section>
<section class="panel table-wrap"><table><thead><tr><th>Route series</th><th>Points</th><th>Final x</th><th>Final raw QD</th><th>Trapezoidal raw-QD AUC</th></tr></thead><tbody>{generated_rows}</tbody></table></section>
</main></body></html>'''


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_report(output_dir: Path, title: str, report: dict[str, Any], routes: list[dict[str, Any]]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_paths = {}
    for axis_name, definition in AXES.items():
        path = output_dir / definition["file"]
        atomic_write(path, render_chart(title, axis_name, routes))
        chart_paths[axis_name] = str(path)
    summary_path = output_dir / "route-summary.json"
    atomic_write(summary_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return {"charts": chart_paths, "summary": str(summary_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        type=parse_source,
        metavar="[LABEL=]PATH",
        help="supervisor metrics JSONL; repeat to compare series",
    )
    parser.add_argument(
        "--route",
        action="append",
        default=[],
        type=parse_route_selector,
        metavar="ROUTE_ID_OR_LABEL[=DISPLAY_LABEL]",
        help="include a route by exact ID or recorded label; repeat as needed",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--title", default="Machine Evolved supervisor raw-QD comparison")
    args = parser.parse_args()
    try:
        report, routes = build_report_data(args.source, args.route)
        outputs = write_report(args.output_dir, args.title, report, routes)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "primaryMetric": report["primaryMetric"]["sourceField"],
        "routes": len(report["routes"]),
        **outputs,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
