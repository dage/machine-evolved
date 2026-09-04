import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("prepare-staged-validation.py")
PREPARE_SCRIPT = Path(__file__).with_name("prepare-population-robustness.py")
SPEC = importlib.util.spec_from_file_location("prepare_staged_validation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def checkpoint():
    creatures = []
    for index, fitness in enumerate((10.0, 8.0, None)):
        creatures.append({
            "fitness": fitness,
            "data": {"metadata": {"creatureId": f"c{index}", "morphologyId": "m0"}, "opaque": index},
        })
    return {
        "algorithm": {"type": "MapElites", "arguments": {
            "population": {"size": 2, "generation": 4, "evaluations": 10},
            "archive": {},
            "mutation": {"config": {}},
        }},
        "experiment": {
            "profile": "fork-R3-1",
            "seed": 1,
            "physics": {
                "gravityZ": -100.0,
                "capsuleMassScale": 0.0001,
                "groundFriction": 0.8,
            },
            "evaluationDomains": [{"id": "nominal", "physics": {}}],
            "trainerState": {"pythonRandomState": [1], "evaluationHistory": []},
        },
        "structure": {"creatures": creatures},
    }


class PrepareStagedValidationTests(unittest.TestCase):
    def test_appends_every_case_once_and_records_exact_archive_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            experiment = repo / "artifacts" / "experiment"
            experiment.mkdir(parents=True)
            routes = {"schemaVersion": 1, "routes": [{
                "id": "fork-R3-1",
                "phase": "matched-continuation",
                "config": "unused.json",
                "runName": "fork-R3-1",
                "evaluationCap": 10,
                "seed": 1,
                "retainFiles": [],
            }]}
            (experiment / "routes.json").write_text(json.dumps(routes))
            run = repo / "training-runs" / "fork-R3-1"
            run.mkdir(parents=True)
            (run / "summary.json").write_text(json.dumps({
                "status": "completed", "evaluations": 10, "evaluatedCreatures": 2,
            }))
            (run / "config.json").write_text(json.dumps(checkpoint()))

            first = MODULE.prepare(repo, experiment, PREPARE_SCRIPT)
            second = MODULE.prepare(repo, experiment, PREPARE_SCRIPT)
            resulting_routes = json.loads((experiment / "routes.json").read_text())["routes"]

            self.assertEqual(first["preparedValidationRouteCount"], len(MODULE.CASES))
            self.assertEqual(second["preparedValidationRouteCount"], len(MODULE.CASES))
            self.assertEqual(len(resulting_routes), 1 + len(MODULE.CASES))
            self.assertTrue(all(route["evaluationCap"] == 2 for route in resulting_routes[1:]))
            configs = list((experiment / "route-configs").glob("*.json"))
            self.assertEqual(len(configs), len(MODULE.CASES))
            nominal = json.loads((experiment / "route-configs" / "validate-fork-R3-1-nominal.json").read_text())
            self.assertEqual(len(nominal["structure"]["creatures"]), 2)
            self.assertTrue(all(entry["fitness"] is None for entry in nominal["structure"]["creatures"]))

    def test_incomplete_source_is_not_queued(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            experiment = repo / "artifacts" / "experiment"
            experiment.mkdir(parents=True)
            routes = {"schemaVersion": 1, "routes": [{
                "id": "fork-R3-1", "phase": "matched-continuation", "config": "unused.json",
                "runName": "fork-R3-1", "evaluationCap": 10, "seed": 1, "retainFiles": [],
            }]}
            (experiment / "routes.json").write_text(json.dumps(routes))
            result = MODULE.prepare(repo, experiment, PREPARE_SCRIPT)
            self.assertEqual(result["preparedValidationRouteCount"], 0)
            self.assertEqual(len(json.loads((experiment / "routes.json").read_text())["routes"]), 1)


if __name__ == "__main__":
    unittest.main()
