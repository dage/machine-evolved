#!/usr/bin/env python3
"""Summarize deterministic MAP-Elites replay and motion-validation outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    with path.open() as source:
        return json.load(source)


def close_enough(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-8, abs_tol=1e-4)


def summarize(
    route_id: str,
    selection_dir: Path,
    replay_dir: Path,
    analysis_dir: Path,
    *,
    minimum_final_to_max: float,
    max_spin_rate: float,
    max_capsule_rotation_rate: float,
    max_unsupported_path_fraction: float,
) -> dict:
    manifest_path = selection_dir / "selection-manifest.json"
    manifest = load_json(manifest_path)
    candidates = []
    for selected in manifest["candidates"]:
        file_name = Path(selected["config"]["path"]).name
        replay_path = replay_dir / file_name
        analysis_path = analysis_dir / file_name
        replay = load_json(replay_path)
        analysis = load_json(analysis_path)
        credibility = analysis["credibility"]
        configured_fitness = float(selected["expectedReplayFitness"])
        measured_fitness = float(analysis["replayedFitnessSimulationUnits"])
        parity = close_enough(configured_fitness, measured_fitness)
        thresholds_match = (
            close_enough(float(credibility["maxSpinRateRadiansPerSecond"]), max_spin_rate)
            and close_enough(
                float(credibility["maxCapsuleRotationRateRadiansPerSecond"]),
                max_capsule_rotation_rate,
            )
            and close_enough(
                float(credibility["maxUnsupportedPathFraction"]),
                max_unsupported_path_fraction,
            )
            and analysis.get("rollingSignatureEnabled") is True
        )
        if not thresholds_match:
            raise ValueError(f"Analysis profile mismatch: {analysis_path}")
        accepted = (
            parity
            and credibility["passes"] is True
            and float(analysis["finalToMaxDistanceRatio"]) >= minimum_final_to_max
            and analysis["rollingSignature"] is False
        )
        domain_scores = [float(value) for value in selected.get("sourceDomainScores", [])]
        candidates.append({
            "sourceOverallRank": selected["sourceOverallRank"],
            "sourceMorphologyRank": selected["sourceMorphologyRank"],
            "selectedOverall": selected["selectedOverall"],
            "creatureId": selected["creatureId"],
            "morphologyId": selected["morphologyId"],
            "robustFitness": float(selected["fitness"]),
            "domainScores": domain_scores,
            "worstDomainScore": min(domain_scores) if domain_scores else None,
            "expectedNominalFitness": configured_fitness,
            "measuredNominalFitness": measured_fitness,
            "fitnessParityVerified": parity,
            "jumpAwareValidationPasses": accepted,
            "maxDistanceMeters": float(analysis["maxDistanceMeters"]),
            "finalToMaxDistanceRatio": float(analysis["finalToMaxDistanceRatio"]),
            "pathEfficiency": float(analysis["pathEfficiency"]),
            "nearGroundTimeFraction": float(analysis["nearGroundTimeFraction"]),
            "unsupportedPathFraction": float(analysis["unsupportedPathFraction"]),
            "rootSpinRateRadiansPerSecond": float(
                analysis["rootSpinRateRadiansPerSecond"]
            ),
            "maxCapsuleRotationRateRadiansPerSecond": float(
                analysis["maxCapsuleRotationRateRadiansPerSecond"]
            ),
            "rollingExplainedFraction": float(analysis["rollingExplainedFraction"]),
            "rollingSignature": analysis["rollingSignature"],
            "configSha256": sha256(selection_dir / selected["config"]["path"]),
            "replaySha256": sha256(replay_path),
            "analysisSha256": sha256(analysis_path),
            "replayConfiguredFitnessSimulationUnits": float(replay["configuredFitness"]),
        })
    candidates.sort(key=lambda item: item["sourceOverallRank"])
    accepted_fitness = sorted(
        (
            item["robustFitness"]
            for item in candidates
            if item["jumpAwareValidationPasses"]
        ),
        reverse=True,
    )
    all_fitness = [item["robustFitness"] for item in candidates]
    return {
        "schemaVersion": 1,
        "routeId": route_id,
        "selectionManifestSha256": sha256(manifest_path),
        "exportedUniqueCandidates": len(candidates),
        "parityPassCount": sum(item["fitnessParityVerified"] for item in candidates),
        "jumpAwarePassCount": len(accepted_fitness),
        "rollingSignatureCount": sum(item["rollingSignature"] for item in candidates),
        "rawBestRobustFitness": max(all_fitness) if all_fitness else None,
        "acceptedBestRobustFitness": accepted_fitness[0] if accepted_fitness else None,
        "acceptedTop5MeanRobustFitness": (
            sum(accepted_fitness[:5]) / min(5, len(accepted_fitness))
            if accepted_fitness else None
        ),
        "validationProfile": {
            "id": "low-gravity-jump-aware-v1",
            "maxSpinRateRadiansPerSecond": max_spin_rate,
            "maxCapsuleRotationRateRadiansPerSecond": max_capsule_rotation_rate,
            "maxUnsupportedPathFraction": max_unsupported_path_fraction,
            "finalToMaxDistanceRatioMinimum": minimum_final_to_max,
            "rollingSignatureEnabled": True,
            "note": (
                "Allows intended low-gravity airborne travel while retaining spin, "
                "capsule-rotation, final-progress, and rolling-signature gates."
            ),
        },
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--selection-dir", required=True, type=Path)
    parser.add_argument("--replay-dir", required=True, type=Path)
    parser.add_argument("--analysis-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-final-to-max", type=float, default=0.9)
    parser.add_argument("--max-spin-rate", type=float, default=10.0)
    parser.add_argument("--max-capsule-rotation-rate", type=float, default=10.0)
    parser.add_argument("--max-unsupported-path-fraction", type=float, default=1.0)
    args = parser.parse_args()
    result = summarize(
        args.route_id,
        args.selection_dir,
        args.replay_dir,
        args.analysis_dir,
        minimum_final_to_max=args.minimum_final_to_max,
        max_spin_rate=args.max_spin_rate,
        max_capsule_rotation_rate=args.max_capsule_rotation_rate,
        max_unsupported_path_fraction=args.max_unsupported_path_fraction,
    )
    serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(serialized)
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
