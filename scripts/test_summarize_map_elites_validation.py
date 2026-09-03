import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("summarize-map-elites-validation.py")
SPEC = importlib.util.spec_from_file_location("summarize_map_elites_validation", MODULE_PATH)
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


class SummaryTest(unittest.TestCase):
    def test_summarizes_parity_and_jump_aware_acceptance(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            selection = root / "selection"
            replays = root / "replays"
            analyses = root / "analysis"
            (selection / "configs").mkdir(parents=True)
            replays.mkdir()
            analyses.mkdir()
            config = selection / "configs" / "rank-1.json"
            config.write_text("{}\n")
            (selection / "selection-manifest.json").write_text(json.dumps({
                "candidates": [{
                    "config": {"path": "configs/rank-1.json"},
                    "sourceOverallRank": 1,
                    "sourceMorphologyRank": 1,
                    "selectedOverall": True,
                    "creatureId": "creature-1",
                    "morphologyId": "m0",
                    "fitness": 8.0,
                    "sourceDomainScores": [9.0, 8.0, 7.0],
                    "expectedReplayFitness": 9.0,
                }]
            }))
            (replays / "rank-1.json").write_text(json.dumps({
                "configuredFitness": 9.0,
            }))
            (analyses / "rank-1.json").write_text(json.dumps({
                "replayedFitnessSimulationUnits": 9.000001,
                "maxDistanceMeters": 0.09,
                "finalToMaxDistanceRatio": 0.95,
                "pathEfficiency": 0.8,
                "nearGroundTimeFraction": 0.2,
                "unsupportedPathFraction": 0.75,
                "rootSpinRateRadiansPerSecond": 4.0,
                "maxCapsuleRotationRateRadiansPerSecond": 5.0,
                "rollingExplainedFraction": 0.3,
                "rollingSignatureEnabled": True,
                "rollingSignature": False,
                "credibility": {
                    "passes": True,
                    "maxSpinRateRadiansPerSecond": 10.0,
                    "maxCapsuleRotationRateRadiansPerSecond": 10.0,
                    "maxUnsupportedPathFraction": 1.0,
                },
            }))
            result = SUMMARY.summarize(
                "route",
                selection,
                replays,
                analyses,
                minimum_final_to_max=0.9,
                max_spin_rate=10.0,
                max_capsule_rotation_rate=10.0,
                max_unsupported_path_fraction=1.0,
            )
            self.assertEqual(result["parityPassCount"], 1)
            self.assertEqual(result["jumpAwarePassCount"], 1)
            self.assertEqual(result["rollingSignatureCount"], 0)
            self.assertEqual(result["acceptedBestRobustFitness"], 8.0)
            self.assertEqual(result["candidates"][0]["worstDomainScore"], 7.0)


if __name__ == "__main__":
    unittest.main()
