import copy
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("prepare-staged-forks.py")
SPEC = importlib.util.spec_from_file_location("prepare_staged_forks", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def checkpoint():
    creatures = []
    for index, fitness in enumerate((10.0, 8.0, None)):
        creatures.append({
            "fitness": fitness,
            "data": {"metadata": {"creatureId": f"c{index}", "morphologyId": f"m{index}"}, "opaque": index},
            "evaluation": {"behavior": {"airborneFraction": 0.1, "rotationParticipation": 0.2}},
        })
    return {
        "algorithm": {"type": "MapElites", "arguments": {
            "population": {"size": 3, "generation": 4, "evaluations": 12},
            "mutation": {"config": {}, "adaptiveSelector": {"enabled": True}},
        }},
        "experiment": {
            "seed": 1,
            "profile": "warmup",
            "evaluationDomains": [{"id": "nominal", "physics": {}}, {"id": "slick", "physics": {}}, {"id": "rough", "physics": {}}],
            "trainerState": {"pythonRandomState": [3, [1, 2], None], "evaluationHistory": [1], "evaluationSimulations": 36},
        },
        "structure": {"creatures": creatures},
    }


class PrepareStagedForksTests(unittest.TestCase):
    def test_pair_preserves_opaque_bank_and_rng_while_resetting_results(self):
        source = checkpoint()
        r3, r5, manifest = MODULE.prepare_pair(copy.deepcopy(source), 240910)
        self.assertEqual(r3["structure"]["creatures"], r5["structure"]["creatures"])
        self.assertEqual([entry["data"] for entry in r3["structure"]["creatures"]], [entry["data"] for entry in source["structure"]["creatures"]])
        self.assertTrue(all(entry["fitness"] is None for entry in r3["structure"]["creatures"]))
        self.assertTrue(all("evaluation" not in entry for entry in r3["structure"]["creatures"]))
        self.assertEqual(r3["experiment"]["trainerState"], r5["experiment"]["trainerState"])
        self.assertEqual(manifest["storedControllerBankCount"], 3)
        self.assertNotIn("adaptiveSelector", r3["algorithm"]["arguments"]["mutation"])

    def test_r5_adds_only_two_declared_gravity_domains(self):
        r3, r5, _ = MODULE.prepare_pair(checkpoint(), 240911)
        self.assertEqual(r5["experiment"]["evaluationDomains"][:3], r3["experiment"]["evaluationDomains"])
        self.assertEqual([domain["id"] for domain in r5["experiment"]["evaluationDomains"][3:]], ["gravity-99", "gravity-101"])


if __name__ == "__main__":
    unittest.main()
