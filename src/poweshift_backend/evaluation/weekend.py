"""Separate descriptive scoring for frozen weekend inference."""

from hashlib import sha256
import json
from pathlib import Path

from poweshift_backend.contracts.runtime import (
    RecommendationFrame,
    WeekendEvaluationReport,
    WeekendRunManifest,
    WeekendRunReport,
)
from poweshift_backend.runtime.artifacts import ArtifactRegistry


def score_weekend_inference(
    manifest: WeekendRunManifest,
    registry: ArtifactRegistry,
    run_output: Path,
    output: Path,
) -> WeekendEvaluationReport:
    """Open protected outcomes only after matching frozen inference."""
    if output.exists():
        raise FileExistsError(f"weekend evaluation output already exists: {output}")
    run_report = WeekendRunReport.model_validate_json((run_output / "report.json").read_text())
    recommendations_path = run_output / "recommendations.jsonl"
    content = recommendations_path.read_bytes()
    if run_report.run_id != manifest.run_id or run_report.target_id != manifest.target_id:
        raise ValueError("run report does not match the evaluation manifest")
    if run_report.status != "completed":
        raise ValueError("only completed inference can be scored")
    if sha256(content).hexdigest() != run_report.recommendations_sha256:
        raise ValueError("frozen recommendations differ from the run report")
    target_ref = registry.reference(manifest.target_id, "protected_target")
    target_path = registry.resolve(manifest.target_id, "protected_target")
    target = json.loads(target_path.read_text())
    recommendations = [
        RecommendationFrame.model_validate_json(line)
        for line in content.decode().splitlines()
        if line
    ]
    sequences = target.get("sequences")
    manoeuvres = target.get("manoeuvres")
    deployments = target.get("deployment_fractions")
    if not isinstance(sequences, list) or not isinstance(manoeuvres, list) or not isinstance(deployments, list):
        raise ValueError("protected target arrays are missing")
    if not len(sequences) == len(manoeuvres) == len(deployments) == len(recommendations):
        raise ValueError("protected targets do not align with frozen recommendations")
    if sequences != [item.sequence for item in recommendations]:
        raise ValueError("protected target sequence differs from frozen inference")
    agreement = sum(item.intent == expected for item, expected in zip(recommendations, manoeuvres, strict=True))
    deployment_error = sum(
        abs(item.deployment_fraction - float(expected))
        for item, expected in zip(recommendations, deployments, strict=True)
    )
    report = WeekendEvaluationReport(
        run_id=manifest.run_id,
        status="measured_descriptive",
        partition=manifest.partition,
        target_id=manifest.target_id,
        target_sha256=target_ref.sha256,
        recommendations_sha256=run_report.recommendations_sha256,
        matched_count=len(recommendations),
        manoeuvre_agreement_rate=agreement / len(recommendations),
        deployment_mae=deployment_error / len(recommendations),
        strategy_claim=False,
        limitations=(
            "action agreement is descriptive and does not prove causal strategy quality",
            "retrospective timing excludes live transport latency",
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n")
    return report
