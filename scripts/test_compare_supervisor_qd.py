import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("compare-supervisor-qd.py")
SPEC = importlib.util.spec_from_file_location("compare_supervisor_qd", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample(timestamp, route_id="adaptive", route_label="Adaptive route", evaluations=10,
           simulations=30, qd_score=5.0, occupied=2, best=4.0):
    return {
        "capturedAt": f"2026-09-04T00:{int(timestamp) % 60:02d}:00+00:00",
        "capturedAtEpochSeconds": timestamp,
        "activeRouteId": route_id,
        "activeRouteLabel": route_label,
        "evaluations": evaluations,
        "domainSimulations": simulations,
        "generation": 999999,
        "qd": {
            "qdScore": qd_score,
            "occupiedCells": occupied,
            "bestFitness": best,
            "normalizedQdScore": 0.999,
        },
    }


class CompareSupervisorQdTests(unittest.TestCase):
    def write_source(self, directory, lines, name="metrics.jsonl"):
        path = Path(directory) / name
        path.write_text("\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        return path

    def test_filters_and_records_missing_stale_and_duplicate_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            first = sample(100)
            path = self.write_source(directory, [
                "",
                "not json",
                [],
                {"capturedAtEpochSeconds": 90, "qd": {"qdScore": 1}},
                sample(95, route_id="other"),
                first,
                first,
                sample(130),
                sample(120, evaluations=12, simulations=36, qd_score=6),
                sample(160, evaluations=20, simulations=25, qd_score=8),
                sample(190, evaluations=None, simulations=None, qd_score=9),
                {**sample(220), "qd": None},
            ])
            sources = [MODULE.parse_source(f"nightly={path}")]
            selectors = [MODULE.parse_route_selector("adaptive=Adaptive QD")]
            report, routes = MODULE.build_report_data(
                sources, selectors, generated_at="2026-09-04T01:00:00+00:00"
            )

            self.assertEqual(report["primaryMetric"]["sourceField"], "qd.qdScore")
            self.assertFalse(report["generationUsedForComparison"])
            source = report["sourceCounts"][0]
            self.assertEqual(source["lineCounts"], {"total": 12, "blank": 1, "decodedObjects": 9})
            self.assertEqual(source["includedCoreSamples"], 4)
            self.assertEqual(source["exclusions"]["malformedJson"], 1)
            self.assertEqual(source["exclusions"]["nonObjectJson"], 1)
            self.assertEqual(source["exclusions"]["missingRouteIdentity"], 1)
            self.assertEqual(source["exclusions"]["routeFiltered"], 1)
            self.assertEqual(source["exclusions"]["duplicateSample"], 1)
            self.assertEqual(source["exclusions"]["staleCapturedAt"], 1)
            self.assertEqual(source["exclusions"]["missingOrInvalidRawQd"], 1)

            route = report["routes"][0]
            self.assertEqual(route["seriesLabel"], "nightly / Adaptive QD")
            candidate = route["rawQdAuc"]["candidateEvaluations"]
            domain = route["rawQdAuc"]["domainSimulations"]
            elapsed = route["rawQdAuc"]["elapsedWallSeconds"]
            self.assertEqual(candidate["pointCount"], 2)
            self.assertEqual(candidate["exclusions"], {"duplicateX": 1, "missingX": 1})
            self.assertEqual(candidate["trapezoidalRawQdAuc"], 65.0)
            self.assertEqual(domain["pointCount"], 1)
            self.assertEqual(domain["exclusions"], {"duplicateX": 1, "staleX": 1, "missingX": 1})
            self.assertEqual(domain["trapezoidalRawQdAuc"], 0)
            self.assertEqual(elapsed["pointCount"], 4)
            self.assertEqual(elapsed["trapezoidalRawQdAuc"], 600.0)
            self.assertEqual(route["finalPrimaryMetrics"]["rawQdScore"], 9.0)
            self.assertEqual(route["finalPrimaryMetrics"]["candidateEvaluations"], 20.0)
            self.assertEqual(route["finalPrimaryMetrics"]["domainSimulations"], 30.0)
            self.assertEqual(route["finalPrimaryMetrics"]["elapsedWallSeconds"], 90.0)
            self.assertNotIn("generation", json.dumps(route).lower())
            self.assertEqual(len(routes), 1)

    def test_same_counter_with_new_qd_replaces_axis_point(self):
        points, exclusions = MODULE.monotonic_axis([
            {
                "capturedAtEpochSeconds": 10.0,
                "evaluations": 4,
                "domainSimulations": 12,
                "rawQdScore": 2.0,
            },
            {
                "capturedAtEpochSeconds": 20.0,
                "evaluations": 4,
                "domainSimulations": 12,
                "rawQdScore": 3.0,
            },
            {
                "capturedAtEpochSeconds": 30.0,
                "evaluations": 8,
                "domainSimulations": 24,
                "rawQdScore": 5.0,
            },
        ], "candidateEvaluations")
        self.assertEqual([point["x"] for point in points], [4.0, 8.0])
        self.assertEqual(points[0]["rawQdScore"], 3.0)
        self.assertEqual(exclusions, {"duplicateXReplaced": 1})
        self.assertEqual(MODULE.trapezoidal_auc(points), 16.0)

    def test_cli_writes_three_offline_charts_and_json_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = self.write_source(directory, [
                sample(100, evaluations=0, simulations=0, qd_score=-2),
                sample(130, evaluations=10, simulations=30, qd_score=6),
            ])
            output = directory / "report"
            result = subprocess.run([
                sys.executable,
                str(SCRIPT),
                "--source", f"test={source}",
                "--route", "adaptive=Adaptive",
                "--output-dir", str(output),
                "--title", "A < B",
            ], check=True, capture_output=True, text=True)
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["primaryMetric"], "qd.qdScore")
            self.assertEqual(manifest["routes"], 1)
            self.assertEqual(set(path.name for path in output.iterdir()), {
                "qd-vs-candidate-evaluations.html",
                "qd-vs-domain-simulations.html",
                "qd-vs-elapsed-wall-time.html",
                "route-summary.json",
            })
            for chart in output.glob("*.html"):
                content = chart.read_text(encoding="utf-8")
                self.assertIn("A &lt; B", content)
                self.assertIn("Raw QD", content)
                self.assertNotIn("https://", content)
                self.assertNotIn("<script src=", content)
            summary = json.loads((output / "route-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["routes"][0]["finalPrimaryMetrics"]["rawQdScore"], 6.0)
            self.assertEqual(
                summary["routes"][0]["rawQdAuc"]["candidateEvaluations"]["trapezoidalRawQdAuc"],
                20.0,
            )

    def test_iso_capture_time_is_accepted_when_epoch_is_missing(self):
        raw = sample(1)
        raw.pop("capturedAtEpochSeconds")
        raw["capturedAt"] = "2026-09-04T03:02:01Z"
        self.assertEqual(MODULE.capture_epoch(raw), 1788490921.0)


if __name__ == "__main__":
    unittest.main()
