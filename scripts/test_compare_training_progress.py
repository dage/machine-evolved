import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("compare-training-progress.py")
SPEC = importlib.util.spec_from_file_location("compare_training_progress", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CompareTrainingProgressTests(unittest.TestCase):
    def test_latest_sample_per_generation_and_invalid_rows_are_handled(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "progress.jsonl"
            source.write_text("\n".join((
                json.dumps({"generation": 1, "evaluations": 10, "bestRobustFitness": 100, "meanArchiveFitness": 50}),
                "not json",
                json.dumps({"generation": 1, "evaluations": 12, "bestRobustFitness": 110, "meanArchiveFitness": 55}),
                json.dumps({"generation": 2, "evaluations": 20, "bestRobustFitness": None, "meanArchiveFitness": 60}),
                json.dumps({"generation": 3, "evaluations": 30, "bestRobustFitness": 125, "meanArchiveFitness": 65}),
            )), encoding="utf-8")
            points = MODULE.load_series(source, 0.01)
            self.assertEqual([point["generation"] for point in points], [1, 3])
            self.assertEqual(points[0]["evaluations"], 12)
            self.assertAlmostEqual(points[0]["best"], 1.1)

    def test_render_contains_both_series_and_escapes_labels(self):
        points = [{"generation": 1, "evaluations": 2, "best": 3.0, "mean": 2.0, "line": 1}]
        output = MODULE.render_html([("A < B", Path("run"), points), ("C", Path("run2"), points)], "Comparison", "m")
        self.assertIn("A &lt; B", output)
        self.assertIn('class="best"', output)
        self.assertIn('class="mean"', output)
        self.assertNotIn("A < B", output)


if __name__ == "__main__":
    unittest.main()
