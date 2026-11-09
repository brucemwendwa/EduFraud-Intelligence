"""Measures detection performance, but only on data that is permitted to support a claim.

This never collects data. An operator supplies a labelled dataset and a manifest stating its
governance. Synthetic data can exercise this code, yet its output says it is not a performance
claim. Real data must have a recorded consent basis, approval, and labels that did not come from
this system's own scores. Run: python -m app.detection.evaluation --manifest m.json --examples e.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Literal

EVALUATION_FRAMEWORK_VERSION = "2026.11.1"
THRESHOLDS = {"medium": 30.0, "high": 60.0, "critical": 80.0}
MIN_EXAMPLES_PER_CLASS = 100
ClaimStatus = Literal["not_a_performance_claim", "insufficient_labels", "governed_evaluation"]


class UngovernedDatasetError(ValueError):
    """The dataset's manifest does not permit it to be evaluated."""


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    is_synthetic: bool
    contains_direct_identifiers: bool
    labels_independent_of_system: bool
    consent_basis: str | None = None
    approved_by: str | None = None
    approved_on: date | None = None
    label_source: str | None = None


@dataclass(frozen=True)
class Example:
    score: float
    is_fraud: bool


@dataclass(frozen=True)
class Interval:
    value: float | None
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class ThresholdResult:
    level: str
    threshold: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: Interval
    recall: Interval
    false_positive_rate: Interval


@dataclass(frozen=True)
class EvaluationReport:
    framework_version: str
    dataset_id: str
    claim_status: ClaimStatus
    notice: str
    examples: int
    positives: int
    negatives: int
    thresholds: list[ThresholdResult]


def validate_manifest(manifest: DatasetManifest) -> None:
    if manifest.contains_direct_identifiers:
        raise UngovernedDatasetError("Remove direct identifiers before evaluation.")
    if manifest.is_synthetic:
        return
    missing = [
        name
        for name, value in (
            ("consent_basis", manifest.consent_basis),
            ("approved_by", manifest.approved_by),
            ("approved_on", manifest.approved_on),
            ("label_source", manifest.label_source),
        )
        if not value
    ]
    if missing:
        raise UngovernedDatasetError(f"Real data needs recorded governance. Missing: {', '.join(missing)}.")
    if not manifest.labels_independent_of_system:
        raise UngovernedDatasetError("Labels derived from this system's own scores would make the evaluation circular.")


def _wilson(successes: int, total: int, z: float = 1.96) -> Interval:
    if total == 0:
        return Interval(None, None, None)
    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return Interval(round(p, 4), round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def _at_threshold(level: str, threshold: float, examples: list[Example]) -> ThresholdResult:
    tp = sum(e.score >= threshold and e.is_fraud for e in examples)
    fp = sum(e.score >= threshold and not e.is_fraud for e in examples)
    tn = sum(e.score < threshold and not e.is_fraud for e in examples)
    fn = sum(e.score < threshold and e.is_fraud for e in examples)
    return ThresholdResult(
        level=level,
        threshold=threshold,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision=_wilson(tp, tp + fp),
        recall=_wilson(tp, tp + fn),
        false_positive_rate=_wilson(fp, fp + tn),
    )


def evaluate(manifest: DatasetManifest, examples: list[Example]) -> EvaluationReport:
    validate_manifest(manifest)
    positives = sum(e.is_fraud for e in examples)
    negatives = len(examples) - positives
    status: ClaimStatus
    if manifest.is_synthetic:
        status = "not_a_performance_claim"
        notice = "Synthetic data: this checks the evaluation pipeline and says nothing about real-world performance."
    elif min(positives, negatives) < MIN_EXAMPLES_PER_CLASS:
        status = "insufficient_labels"
        notice = f"Fewer than {MIN_EXAMPLES_PER_CLASS} examples in a class: do not report these figures as performance."
    else:
        status = "governed_evaluation"
        notice = (
            "Applies only to this dataset and these versions. Fairness across student groups is evaluated separately."
        )
    return EvaluationReport(
        framework_version=EVALUATION_FRAMEWORK_VERSION,
        dataset_id=manifest.dataset_id,
        claim_status=status,
        notice=notice,
        examples=len(examples),
        positives=positives,
        negatives=negatives,
        thresholds=[_at_threshold(level, value, examples) for level, value in THRESHOLDS.items()],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True, help="CSV with columns: score,is_fraud (0 or 1)")
    args = parser.parse_args()
    raw = json.loads(args.manifest.read_text())
    if raw.get("approved_on"):
        raw["approved_on"] = date.fromisoformat(raw["approved_on"])
    with args.examples.open(newline="") as handle:
        rows = [Example(float(r["score"]), r["is_fraud"].strip() == "1") for r in csv.DictReader(handle)]
    print(json.dumps(asdict(evaluate(DatasetManifest(**raw), rows)), indent=2))


if __name__ == "__main__":
    main()
