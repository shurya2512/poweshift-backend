"""Bounded saved-model comparison on admitted known-input motion intervals."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import torch

from poweshift_backend.contracts.representation import ComparisonPolicy, ModelRecord
from poweshift_backend.driver.controller import DriverDemand, DriverMode
from poweshift_backend.physics.forces import mechanics_derivative
from poweshift_backend.physics.integrate import integrate
from poweshift_backend.physics.state import MechanicsState, RoadInput
from poweshift_backend.reconstruction.baseline import fit_effective_profile, runtime_from_profile
from poweshift_backend.reconstruction.inputs import Phase3Inputs
from poweshift_backend.representation.evaluation import CandidateScore, EvaluationEntry, choose_candidate, evaluate_sequential
from poweshift_backend.representation.inputs import UpdateUnit
from poweshift_backend.representation.models import CandidateConfig, build_candidate
from poweshift_backend.representation.promotion import ProfileVersion, PromotionDecision, promote_profile, retain_baseline
from poweshift_backend.representation.run import _precompute_window, _training_units, _update_input_identifier
from poweshift_backend.representation.training import FrozenUpdateTransform, policy_identifier
from poweshift_backend.representation.update import UpdateState, apply_quality_aware_update, assess_update_quality


_FEATURE_NAMES = ("speed_ms", "throttle_pct", "brake")
_PROFILE_COMPONENT_NAMES = ("propulsion", "resistance", "braking", "grip")
_QUALITY_THRESHOLD = 0.8
_REQUIRED_REGIMES = ("braking", "coast", "propulsion")


def run_comparison(inputs: Phase3Inputs, entry: str, artifact_dir: Path, output_path: Path) -> dict[str, object]:
    """Compare saved candidates without changing their weights or retraining them."""
    manifest = _load_manifest(artifact_dir)
    if manifest["entry"] != entry or manifest["policy"].get("metric") != "speed_mae_ms":
        raise ValueError("saved artifact does not match the requested entry and metric")
    policy = ComparisonPolicy.model_validate(manifest["policy"])
    if manifest["policy_id"] != policy_identifier(policy):
        raise ValueError("saved policy hash does not match its policy")
    source_binding = _write_source_binding(inputs, entry, artifact_dir, manifest)
    protocol = _write_protocol(artifact_dir, entry, policy, manifest["policy_id"], source_binding)
    models = {kind: _load_model(artifact_dir, manifest, kind) for kind in ("gru", "transformer")}
    reports = {split: _entries(inputs, entry, split, 4) for split in ("selection", "final_evaluation")}
    scores = []
    evaluated = {}
    for kind, loaded in models.items():
        selection = _evaluate(inputs, policy, reports["selection"], loaded, frozen=False)
        frozen = _evaluate(inputs, policy, reports["selection"], loaded, frozen=True)
        scores.extend((_score("baseline", "selection", selection), _score(kind, "selection", selection), _score(kind, "selection", frozen, "frozen")))
        evaluated[kind] = {"selection": selection, "frozen": frozen}
    decision = choose_candidate(policy, tuple(scores))
    selected = decision.selected_candidate
    final = _evaluate(
        inputs,
        policy,
        reports["final_evaluation"],
        models.get(selected, models["gru"]),
        frozen=selected == "baseline",
        baseline_only=selected == "baseline",
    )
    matched_updates = all(value["selection"].baseline_refits == value["selection"].candidate_updates for value in evaluated.values())
    eligible_regimes = {f"{entry}:{regime}" for regime in _REQUIRED_REGIMES}
    supported = eligible_regimes.issubset(next(iter(evaluated.values()))["selection"].metrics)
    registry = _registry(inputs, entry, policy, decision, models, reports["selection"], evaluated, manifest, matched_updates, supported)
    retention = "candidate_eligible_for_promotion" if selected != "baseline" and matched_updates and supported else "baseline_retained"
    blocker = None if retention == "candidate_eligible_for_promotion" else "selection retained baseline" if selected == "baseline" else "selection lacks all eligible regimes" if not supported else "baseline refit evidence did not match candidate updates"
    payload = {
        "policy_id": manifest["policy_id"],
        "mode": "known_input_reconstruction",
        "entry": entry,
        "effective_manifest_sha256": inputs.manifest.effective_manifest_sha256,
        "evaluation_run_cap_per_split": 4,
        "pre_scoring_protocol": protocol,
        "source_binding": source_binding,
        "selection": {kind: _report(value["selection"], kind) for kind, value in evaluated.items()},
        "frozen": {kind: _report(value["frozen"], kind) for kind, value in evaluated.items()},
        "selected_candidate": selected,
        "final_report": _report(final, selected),
        "retention": retention,
        "promotion_blocker": blocker,
        "registry": registry,
    }
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if output_path.exists() and sha256(output_path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable comparison differs: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    return {"report_path": str(output_path), "report_sha256": digest, **payload}


def _load_manifest(directory: Path) -> dict:
    path = directory / "training_manifest.json"
    value = json.loads(path.read_text())
    for kind in ("gru", "transformer"):
        item = value["models"][kind]
        path = Path(item["path"])
        if path.resolve() != (directory / f"{kind}.pt").resolve():
            raise ValueError("manifest checkpoint path differs from the loaded checkpoint")
        if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("saved artifact hash does not match its manifest")
        record = _model_record(value["model_records"][kind])
        if record.candidate != kind or record.policy_id != value["policy_id"]:
            raise ValueError("model record does not match the saved candidate and policy")
        _transform_from_manifest(value["transforms"][kind], record)
        if record.profile_component_names != _PROFILE_COMPONENT_NAMES or len(record.profile_upper_bounds) != len(_PROFILE_COMPONENT_NAMES):
            raise ValueError("model record does not match the saved physical profile configuration")
        if not all(np.isfinite(record.profile_upper_bounds)) or not all(value > 0.0 for value in record.profile_upper_bounds):
            raise ValueError("model record has invalid physical profile bounds")
    item = value["training_inputs"]
    path = Path(item["path"])
    if path.resolve() != (directory / "training_inputs.npz").resolve():
        raise ValueError("manifest training-input path differs from the verified input artifact")
    if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise ValueError("saved artifact hash does not match its manifest")
    return value


def _load_model(directory: Path, manifest: dict, kind: str):
    record = _model_record(manifest["model_records"][kind])
    config = CandidateConfig(3, record.latent_width, record.hidden_width, record.layers, record.heads, record.feedforward_width, len(record.profile_component_names), record.variance_floor)
    model = build_candidate(kind, config)
    state = torch.load(directory / f"{kind}.pt", map_location="cpu", weights_only=True)
    if _model_record(state["model_record"]) != record:
        raise ValueError("checkpoint model record does not match its manifest")
    model.load_state_dict(state["model_state_dict"])
    model.eval()
    return model, record, _transform_from_manifest(manifest["transforms"][kind], record)


def _model_record(value: dict) -> ModelRecord:
    return ModelRecord.model_validate_json(json.dumps(value))


def _transform_from_manifest(value: dict, record: ModelRecord) -> FrozenUpdateTransform:
    features = tuple(value["features"])
    mean = np.array(value["mean"], dtype=np.float32)
    scale = np.array(value["scale"], dtype=np.float32)
    if features != _FEATURE_NAMES or record.feature_names != features:
        raise ValueError("saved transform does not match the supported feature configuration")
    if mean.shape != (len(features),) or scale.shape != (len(features),):
        raise ValueError("saved transform does not match the supported feature configuration")
    if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0.0):
        raise ValueError("saved transform has invalid finite bounds")
    transform = FrozenUpdateTransform(features, mean, scale)
    if transform.identifier != record.transform_id:
        raise ValueError("saved transform identifier does not match its model record")
    return transform


def _write_source_binding(inputs: Phase3Inputs, entry: str, directory: Path, manifest: dict) -> dict[str, object]:
    units = {(unit.session_key, unit.run_id): _precompute_window(unit) for unit in _units(inputs, entry, "training")}
    teachers = manifest["teachers"]
    input_hashes = []
    fit_hashes = []
    for teacher in teachers:
        key = (teacher["session_key"], teacher["run_id"])
        unit = units.get(key)
        if unit is None or unit.completed_cutoff_s != teacher["completed_cutoff_s"] or _update_input_identifier(unit) != teacher["training_input_sha256"]:
            raise ValueError("admitted training inputs do not match the saved teacher hashes")
        input_hashes.append(teacher["training_input_sha256"])
        fit_hashes.append(teacher["numerical_fit_sha256"])
    with np.load(directory / "training_inputs.npz", allow_pickle=False) as saved:
        if tuple(str(value) for value in saved["input_sha256"]) != tuple(input_hashes):
            raise ValueError("saved training inputs do not match the teacher input hashes")
        if tuple(str(value) for value in saved["fit_sha256"]) != tuple(fit_hashes):
            raise ValueError("saved training inputs do not match the teacher fit hashes")
    combined_inputs = _combined_identifier(input_hashes)
    combined_fits = _combined_identifier(fit_hashes)
    if any(record["training_input_sha256"] != combined_inputs or record["teacher_fit_sha256"] != combined_fits for record in manifest["model_records"].values()):
        raise ValueError("model records do not match the saved teacher hashes")
    payload = {
        "version": 1,
        "entry": entry,
        "effective_manifest_sha256": inputs.manifest.effective_manifest_sha256,
        "training_input_artifact_sha256": manifest["training_inputs"]["sha256"],
        "teacher_input_sha256": input_hashes,
        "teacher_fit_sha256": fit_hashes,
        "verification": "derived after training from admitted inputs; the original training manifest did not pin this source manifest",
    }
    return _write_immutable_json(directory / "source_binding_v1.json", payload)


def _write_protocol(directory: Path, entry: str, policy: ComparisonPolicy, policy_id: str, source_binding: dict[str, object]) -> dict[str, object]:
    payload = {
        "version": 1,
        "entry": entry,
        "policy_id": policy_id,
        "metric": policy.metric,
        "mode": "known_input_reconstruction",
        "evaluation_run_cap_per_split": 4,
        "quality_threshold": _QUALITY_THRESHOLD,
        "required_selection_regimes": _REQUIRED_REGIMES,
        "exclusion_treatment": "candidate and baseline must retain identical coverage and exclusions; unsupported regimes block promotion",
        "telemetry_only_ablation": "the callback is the identical candidate predictor because this experiment has no external features",
        "source_binding_sha256": source_binding["sha256"],
    }
    return _write_immutable_json(directory / "comparison_protocol_v1.json", payload)


def _write_immutable_json(path: Path, payload: dict[str, object]) -> dict[str, object]:
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if path.exists() and sha256(path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable artifact differs: {path}")
    path.write_text(content)
    return {"path": str(path), "sha256": digest, **payload}


def _combined_identifier(identifiers: list[str]) -> str:
    return sha256(json.dumps(tuple(identifiers), separators=(",", ":")).encode()).hexdigest()


def _entries(inputs: Phase3Inputs, entry: str, split: str, budget: int) -> tuple[tuple[EvaluationEntry, ...], dict]:
    units = _units(inputs, entry, split)
    prior = units[0]
    chunks = {(item.session_key, item.run_id): item for item in inputs.chunks if item.entry == entry and item.split == split and item.chunk_index == 0}
    rows, metadata = [], {}
    for index, target in enumerate(units[1 : budget + 1]):
        chunk = chunks.get((target.session_key, target.run_id))
        if chunk is None or len(chunk.time_s) < 2 or not all(chunk.valid[name][0] for name in ("speed_ms", "throttle_pct", "brake")):
            continue
        regime = "braking" if chunk.controls["brake"][0] > 0 else "propulsion" if chunk.controls["throttle_pct"][0] > 0 else "coast"
        rows.append(EvaluationEntry(_precompute_window(prior), regime, float(chunk.speed_ms[1]), float(target.completed_cutoff_s), index, _precompute_window(target)))
        metadata[(prior.session_key, prior.run_id)] = chunk
        prior = target
    return tuple(rows), metadata


def _units(inputs: Phase3Inputs, entry: str, split: str) -> tuple[UpdateUnit, ...]:
    if split == "training":
        return _training_units(inputs, entry)[0]
    copied = tuple(replace(chunk, split="training") if chunk.split == split else chunk for chunk in inputs.chunks if chunk.entry == entry and chunk.split == split)
    staged = Phase3Inputs(inputs.manifest, copied, inputs.continuations, inputs.alignment_support)
    return tuple(replace(unit, split=split) for unit in _training_units(staged, entry)[0])


def _evaluate(inputs, policy, entry_data, loaded, frozen, baseline_only=False):
    entries, metadata = entry_data
    model, record, transform = loaded
    baseline = None
    state = UpdateState(record.teacher_fit_sha256, record.transform_id, np.zeros(record.latent_width, dtype=np.float32))
    frozen_values = None
    def predict(context, candidate):
        nonlocal frozen_values, baseline
        if baseline is None:
            baseline = _fit_prefix(inputs, context, policy)
        chunk = metadata[(context.session_key, context.run_id)]
        unit = UpdateUnit(context.entry, context.session_key, context.run_id, context.split, context.completed_cutoff_s, context.features, context.valid, context.padding)
        if candidate and frozen_values is None:
            with torch.no_grad():
                profile, latent = model.update(torch.from_numpy(transform.apply(unit)).unsqueeze(0), torch.from_numpy(np.array(unit.valid & ~unit.padding[:, None], copy=True)).unsqueeze(0), torch.from_numpy(np.array(state.latent, copy=True)).unsqueeze(0))
            values = profile[0].numpy() * np.array(record.profile_upper_bounds)
        elif candidate:
            values = frozen_values
        if candidate and frozen_values is None and frozen:
            frozen_values = values
        if candidate:
            runtime = replace(baseline.runtime, forces=replace(baseline.runtime.forces, max_drive_force_n=float(values[0]), drag_n_per_ms2=float(values[1]), max_brake_force_n=float(values[2])), tyre=replace(baseline.runtime.tyre, longitudinal_mu=float(values[3]), lateral_mu=float(values[3])))
        else:
            runtime = baseline.runtime
        initial = MechanicsState(float(chunk.time_s[0]), float(chunk.speed_ms[0]), 0.0, 0.0, 30.0)
        demand = DriverDemand(float(np.clip(chunk.controls["throttle_pct"][0] / 100, 0, 1)), float(np.clip(chunk.controls["brake"][0], 0, 1)), 0.5, DriverMode.KNOWN_INPUT)
        return integrate(initial, float(chunk.time_s[1]), lambda current: mechanics_derivative(current, demand, RoadInput(0.0, 1.0), runtime.mass, runtime.geometry, runtime.forces, runtime.tyre, runtime.solve_config), runtime.integration)[-1].speed_ms
    def update(context):
        nonlocal state
        quality = assess_update_quality(context.valid, context.padding, _QUALITY_THRESHOLD)
        if frozen or baseline_only: return apply_quality_aware_update(state, state.latent, replace(quality, status="low"), state.model_id, state.transform_id)
        unit = UpdateUnit(context.entry, context.session_key, context.run_id, context.split, context.completed_cutoff_s, context.features, context.valid, context.padding)
        with torch.no_grad():
            _, latent = model.update(torch.from_numpy(transform.apply(unit)).unsqueeze(0), torch.from_numpy(np.array(unit.valid & ~unit.padding[:, None], copy=True)).unsqueeze(0), torch.from_numpy(np.array(state.latent, copy=True)).unsqueeze(0))
        result = apply_quality_aware_update(state, latent[0].numpy().astype(np.float32), quality, state.model_id, state.transform_id)
        state = result.state
        return result
    def refit(context):
        nonlocal baseline
        baseline = _fit_prefix(inputs, context, policy)
        return 1
    evaluation_policy = policy.model_copy(update={"per_update_refit_budget": 0}) if frozen else policy
    candidate_predict = lambda context: predict(context, not baseline_only)
    return evaluate_sequential(evaluation_policy, entries, baseline_predict=lambda context: predict(context, False), candidate_predict=candidate_predict, baseline_refit=refit, candidate_update=update, candidate_model=model, telemetry_only_predict=candidate_predict, update_quality=lambda context: assess_update_quality(context.valid, context.padding, _QUALITY_THRESHOLD))


def _fit_prefix(inputs, context, policy):
    source = [replace(chunk, split="training") for chunk in inputs.chunks if chunk.entry == context.entry and chunk.split in ("training", "selection", "final_evaluation") and (chunk.session_key, float(chunk.time_s[-1])) <= (context.session_key, context.completed_cutoff_s)]
    return fit_effective_profile(Phase3Inputs(inputs.manifest, tuple(source), (), inputs.alignment_support), 24, context.entry, policy.numerical)


def _registry(inputs, entry, policy, decision, models, selection_entries, evaluated, manifest, matched_updates, supported):
    source = tuple(chunk for chunk in inputs.chunks if chunk.entry == entry and chunk.split == "training")
    baseline = fit_effective_profile(Phase3Inputs(inputs.manifest, source, (), inputs.alignment_support), 24, entry, policy.numerical)
    components = {component.name: component.value for component in baseline.profile.components}
    records = manifest["model_records"]
    common = next(iter(records.values()))
    baseline_version = ProfileVersion(
        entry,
        "baseline",
        1,
        True,
        manifest["policy_id"],
        tuple(float(components[name]) for name in _PROFILE_COMPONENT_NAMES),
        _PROFILE_COMPONENT_NAMES,
        "numerical_baseline",
        common["training_input_sha256"],
        common["teacher_fit_sha256"],
        inputs.manifest.effective_manifest_sha256,
    )
    if decision.selected_candidate == "baseline":
        versions = retain_baseline((baseline_version,), policy, decision)
        action = {"action": "retain_baseline", "reason": "selection retained baseline"}
    elif not matched_updates or not supported:
        versions = retain_baseline((baseline_version,), policy, replace(decision, selected_candidate="baseline"))
        action = {"action": "promotion_blocked", "reason": "selection evidence lacks matched required coverage"}
    else:
        candidate = decision.selected_candidate
        candidate_values = _candidate_values(models[candidate], selection_entries)
        report = evaluated[candidate]["selection"]
        coverage = {key: value.count for key, value in report.metrics.items()}
        promotion = PromotionDecision(
            entry,
            candidate,
            policy,
            manifest["policy_id"],
            models[candidate][1],
            True,
            inputs.manifest.effective_manifest_sha256,
            tuple(sorted({chunk.entry for chunk in inputs.chunks})),
            decision,
            decision.selection_baseline_metric,
            decision.selected_candidate_metric,
            coverage,
            coverage,
            candidate_values,
        )
        versions = promote_profile((baseline_version,), promotion)
        action = {"action": "promote_profile", "reason": "selection met the frozen promotion rule"}
    return {
        "versions": [asdict(version) for version in versions],
        "archived_candidate_checkpoints": manifest["models"],
        "candidate_model_records": records,
        "action": action,
    }


def _candidate_values(loaded, entry_data) -> tuple[float, ...]:
    entries, _ = entry_data
    if not entries:
        raise ValueError("promotion needs at least one scored entry")
    model, record, transform = loaded
    context = entries[0].prefix
    unit = UpdateUnit(context.entry, context.session_key, context.run_id, context.split, context.completed_cutoff_s, context.features, context.valid, context.padding)
    valid = np.array(unit.valid & ~unit.padding[:, None], copy=True)
    with torch.no_grad():
        profile, _ = model.update(torch.from_numpy(transform.apply(unit)).unsqueeze(0), torch.from_numpy(valid).unsqueeze(0), torch.zeros((1, record.latent_width), dtype=torch.float32))
    return tuple(float(value) for value in profile[0].numpy() * np.array(record.profile_upper_bounds))


def _score(candidate, split, report, mode="sequential"):
    coverage = {key: value.count for key, value in report.metrics.items()}
    errors = [value.baseline_absolute_error if candidate == "baseline" else value.candidate_absolute_error for value in report.metrics.values()]
    return CandidateScore(candidate, split, sum(errors) / sum(coverage.values()), coverage, mode, report.exclusions)


def _report(report, candidate_kind):
    return {
        "candidate_kind": candidate_kind,
        "accepted_units": report.accepted_units,
        "coverage": {key: value.count for key, value in report.metrics.items()},
        "entry_regime": {
            key: {
                "count": value.count,
                "baseline_absolute_error": value.baseline_absolute_error,
                "candidate_absolute_error": value.candidate_absolute_error,
                "run_ids": value.run_coverage,
                "exclusions": value.exclusions,
            }
            for key, value in report.metrics.items()
        },
        "baseline_mae": sum(value.baseline_absolute_error for value in report.metrics.values()) / max(report.accepted_units, 1),
        "candidate_mae": sum(value.candidate_absolute_error for value in report.metrics.values()) / max(report.accepted_units, 1),
        "exclusions": report.exclusions,
        "telemetry_only_ablation": dict(report.telemetry_only_ablation),
        "telemetry_only_ablation_status": "neutral_identical_predictor_no_external_features",
        "withheld_updates": report.withheld_updates,
        "reset_evidence": report.reset_evidence,
        "baseline_refits": report.baseline_refits,
        "candidate_updates": report.candidate_updates,
    }
