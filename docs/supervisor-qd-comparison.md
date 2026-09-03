# Supervisor raw-QD comparison

`scripts/compare-supervisor-qd.py` compares one or more supervisor
`metrics.jsonl` series without contacting a worker or a running experiment. It
produces three offline, self-contained HTML charts and one machine-readable
route summary. The plotted primary metric is always raw `qd.qdScore`.
Generation and normalized QD are not comparison axes or substitute outcomes.

Example:

```bash
python3 scripts/compare-supervisor-qd.py \
  --source adaptive=/path/to/adaptive/metrics.jsonl \
  --source fixed=/path/to/fixed/metrics.jsonl \
  --route adaptive-primary='Adaptive selector' \
  --route fixed-primary='Fixed baseline' \
  --output-dir artifacts/codex/overnight-qd-comparison
```

`--source` accepts either `LABEL=PATH` or a bare path. Repeat `--route` to
filter by an exact `activeRouteId` or a recorded route label. The optional value
after `=` is the display label. With no route filter, every identified route is
included. Each source/route pair remains a separate chart series.

The report excludes malformed records, samples without a route, capture time,
or finite raw QD, and source-order time regressions. It records those exclusions
in `route-summary.json`. Candidate-evaluation and domain-simulation views are
deduplicated independently and reject regressing counters. Elapsed wall time is
measured from the first valid sample for that source/route and intentionally
retains later plateau samples, because time spent at a plateau is real wall
time. Each axis reports its observed support and trapezoidal raw-QD AUC; the
script does not extrapolate before the first or after the last observed point.
