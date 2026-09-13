"""Bounded real-data gate for the representation comparison path."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import torch

from poweshift_backend.contracts.representation import ComparisonPolicy, NumericalPolicy
from poweshift_backend.reconstruction.baseline import fit_effective_profile
from poweshift_backend.reconstruction.comparison import measure_numerical_checks, select_numerical_policy
from poweshift_backend.reconstruction.inputs import Phase3Inputs
from poweshift_backend.representation.inputs import RunClosure, UpdateSegment, UpdateUnit, assemble_update_units
from poweshift_backend.representation.models import CandidateConfig
from poweshift_backend.representation.training import TeacherProfile, policy_identifier, train_distilled_candidate


@dataclass(frozen=True)
class Phase4Outcome:
    """A ready or blocked comparison gate with its measured reason."""

    entry: str
    status: str
    reason: str | None
    policy: ComparisonPolicy | None
    policy_id: str | None
    checks: tuple[dict[str, object], ...]

    def json(self) -> str:
        """Serialize a stable report that can be retained without source mutation."""
        value = asdict(self)
        value["policy"] = self.policy.model_dump(mode="json") if self.policy else None
        return json.dumps(value, sort_keys=True)


def run_phase4_gate(inputs: Phase3Inputs, entry: str) -> Phase4Outcome:
    """Measure readiness before allocating neural training or evaluation work."""
    policies = (
        NumericalPolicy(step_s=0.04, axle_tolerance_n=0.1, event_time_tolerance_s=1e-12),
        NumericalPolicy(step_s=0.02, axle_tolerance_n=0.05, event_time_tolerance_s=1e-12),
    )
    entry_inputs = Phase3Inputs(
        inputs.manifest,
        tuple(chunk for chunk in inputs.chunks if chunk.entry == entry),
        tuple(item for item in inputs.continuations if item[1] == entry),
        inputs.alignment_support,
    )
    if not entry_inputs.chunks:
        return Phase4Outcome(entry, "blocked", "entry is absent from admitted evidence", None, None, ())
    baseline = fit_effective_profile(entry_inputs, sample_budget=24, entry=entry, numerical_policy=policies[0])
    try:
        checks = measure_numerical_checks(entry_inputs, baseline, policies)
        selected = select_numerical_policy(policies, checks, maximum_difference_ms=0.01)
    except ValueError as error:
        return Phase4Outcome(entry, "blocked", str(error), None, None, ())
    policy = ComparisonPolicy(
        numerical=selected,
        metric="speed_mae_ms",
        minimum_relative_improvement=0.05,
        evaluation_reuse="reused_evaluation",
        per_update_refit_budget=1,
    )
    policy_id = policy_identifier(policy)
    report_checks = tuple(
        {
            "regime": check.regime,
            "reference_difference_ms": check.reference_difference_ms,
            "refined_step_difference_ms": check.refined_step_difference_ms,
            "stricter_axle_difference_ms": check.stricter_axle_difference_ms,
        }
        for check in checks
        if check.policy == selected
    )
    return Phase4Outcome(entry, "ready", None, policy, policy_id, report_checks)


def run_smoke(inputs: Phase3Inputs, entry: str, policy: ComparisonPolicy, policy_id: str) -> dict[str, object]:
    """Run exactly 100 optimizer steps per candidate on one admitted completed training run."""
    if policy_id != policy_identifier(policy):
        raise ValueError("smoke policy identifier does not match the selected policy")
    units, refused_runs = _training_units(inputs, entry)
    if not units:
        raise ValueError("admitted entry has no completed training run")
    unit = _precompute_window(max(units, key=_unit_order_key))
    teacher = build_training_teacher(inputs, unit, policy, policy_id, shared_profile_upper_bounds(inputs, entry, policy.numerical))
    torch.set_num_threads(1)
    config = CandidateConfig(feature_width=3)
    results = {kind: train_distilled_candidate(kind, config, (teacher,), policy, feature_names=("speed_ms", "throttle_pct", "brake"), policy_id=policy_id, optimizer_steps=100) for kind in ("gru", "transformer")}
    return {
        "provenance": {
            "entry": entry,
            "policy_id": policy_id,
            "teacher_fit_sha256": teacher.numerical_fit_sha256,
            "training_input_sha256": teacher.training_input_sha256,
            "source_cutoff_s": teacher.source_cutoff_s,
            "refused_run_count": refused_runs,
        },
        **{kind: {"steps": result.optimizer_steps, "seconds": result.optimizer_seconds, "steps_per_second": result.optimizer_steps / result.optimizer_seconds, "final_loss": result.losses[-1], "reset_reasons": result.reset_reasons} for kind, result in results.items()},
    }


def run_full_training(
    inputs: Phase3Inputs, entry: str, policy: ComparisonPolicy, policy_id: str, output_dir: Path
) -> dict[str, object]:
    """Train both candidates on a bounded chronological set and save immutable artifacts."""
    if policy_id != policy_identifier(policy):
        raise ValueError("full training policy identifier does not match the selected policy")
    units, refused_runs = _training_units(inputs, entry)
    ordered = sorted(units, key=_unit_order_key)
    if not ordered:
        raise ValueError("admitted entry has no completed training run")
    selected = tuple(ordered[-policy.candidate_max_units:])
    bounds = shared_profile_upper_bounds(inputs, entry, policy.numerical)
    teachers = tuple(build_training_teacher(inputs, _precompute_window(unit), policy, policy_id, bounds) for unit in selected)
    torch.set_num_threads(1)
    config = CandidateConfig(feature_width=3)
    results = {
        kind: train_distilled_candidate(
            kind, config, teachers, policy, feature_names=("speed_ms", "throttle_pct", "brake"),
            policy_id=policy_id, optimizer_steps=1000,
        )
        for kind in ("gru", "transformer")
    }
    artifacts = _save_training_artifacts(output_dir, entry, policy, policy_id, teachers, results)
    return {
        "artifacts": artifacts,
        "provenance": {
            "entry": entry,
            "policy_id": policy_id,
            "profile_component_names": ("propulsion", "resistance", "braking", "grip"),
            "profile_upper_bounds": bounds.tolist(),
            "selected_teacher_count": len(teachers),
            "refused_run_count": refused_runs,
            "teacher_fit_sha256": _identifier([teacher.numerical_fit_sha256 for teacher in teachers]),
            "training_input_sha256": _identifier([teacher.training_input_sha256 for teacher in teachers]),
        },
        **{
            kind: {
                "steps": result.optimizer_steps,
                "seconds": result.optimizer_seconds,
                "steps_per_second": result.optimizer_steps / result.optimizer_seconds,
                "final_loss": result.losses[-1],
                "reset_reasons": result.reset_reasons,
            }
            for kind, result in results.items()
        },
    }


def build_training_teacher(
    inputs: Phase3Inputs, unit: UpdateUnit, policy: ComparisonPolicy, policy_id: str, profile_upper_bounds: np.ndarray
) -> TeacherProfile:
    """Fit a numerical teacher from the chronological training prefix for one unit."""
    if unit.split != "training" or policy_id != policy_identifier(policy):
        raise ValueError("teacher policy and training unit must match the selected policy")
    eligible_units, _ = _training_units(inputs, unit.entry)
    eligible_keys = {
        (candidate.session_key, candidate.run_id)
        for candidate in eligible_units
        if _unit_order_key(candidate) <= _unit_order_key(unit)
    }
    if (unit.session_key, unit.run_id) not in eligible_keys:
        raise ValueError("teacher source does not contain its completed update run")
    source = tuple(
        chunk for chunk in inputs.chunks
        if chunk.entry == unit.entry and chunk.split == "training"
        and (chunk.session_key, chunk.run_id) in eligible_keys and _precedes_unit(chunk, unit)
    )
    fit_inputs = Phase3Inputs(inputs.manifest, source, (), inputs.alignment_support)
    baseline = fit_effective_profile(fit_inputs, min(24, policy.training_teacher_budget), unit.entry, policy.numerical)
    components = {item.name: item.value for item in baseline.profile.components}
    physical_target = np.array(
        [components["propulsion"], components["resistance"], components["braking"], components["grip"]],
        dtype=np.float32,
    )
    target = np.clip(physical_target / profile_upper_bounds, 0.0, 1.0).astype(np.float32)
    input_sha256 = _update_input_identifier(unit)
    source_sha256 = _source_identifier(source)
    fit_sha256 = _identifier({"source": source_sha256, "policy": policy_id, "cutoff_s": unit.completed_cutoff_s, "components": components, "settings": baseline.settings})
    return TeacherProfile(unit, target, fit_sha256, input_sha256, policy_id, unit.completed_cutoff_s, physical_target, profile_upper_bounds)


def shared_profile_upper_bounds(inputs: Phase3Inputs, entry: str, numerical_policy: NumericalPolicy) -> np.ndarray:
    """Freeze decoder bounds from the admitted training corpus."""
    units, _ = _training_units(inputs, entry)
    identities = {(unit.session_key, unit.run_id) for unit in units}
    source = tuple(chunk for chunk in inputs.chunks if chunk.entry == entry and chunk.split == "training" and (chunk.session_key, chunk.run_id) in identities)
    baseline = fit_effective_profile(Phase3Inputs(inputs.manifest, source, (), inputs.alignment_support), 24, entry, numerical_policy)
    upper = baseline.settings["bound_recipe"]["bounds"]["upper"]
    bounds = np.array([upper[0], upper[2], upper[1], upper[3]], dtype=np.float32)
    bounds.setflags(write=False)
    return bounds


def _save_training_artifacts(output_dir: Path, entry: str, policy: ComparisonPolicy, policy_id: str, teachers, results) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_path = output_dir / "training_inputs.npz"
    inputs_candidate = output_dir / "training_inputs.candidate.npz"
    np.savez_compressed(
        inputs_candidate,
        features=np.stack([teacher.unit.features for teacher in teachers]),
        valid=np.stack([teacher.unit.valid for teacher in teachers]),
        padding=np.stack([teacher.unit.padding for teacher in teachers]),
        targets=np.stack([teacher.target for teacher in teachers]),
        physical_targets=np.stack([teacher.physical_target for teacher in teachers]),
        profile_upper_bounds=teachers[0].profile_upper_bounds,
        session_keys=np.array([teacher.unit.session_key for teacher in teachers]),
        run_ids=np.array([teacher.unit.run_id for teacher in teachers]),
        fit_sha256=np.array([teacher.numerical_fit_sha256 for teacher in teachers]),
        input_sha256=np.array([teacher.training_input_sha256 for teacher in teachers]),
    )
    inputs_digest = sha256(inputs_candidate.read_bytes()).hexdigest()
    if inputs_path.exists() and sha256(inputs_path.read_bytes()).hexdigest() != inputs_digest:
        inputs_candidate.unlink()
        raise FileExistsError(f"immutable training inputs differ: {inputs_path}")
    inputs_candidate.replace(inputs_path)
    model_paths = {}
    for kind, result in results.items():
        path = output_dir / f"{kind}.pt"
        candidate = path.with_suffix(".candidate")
        torch.save({"model_state_dict": result.model.state_dict(), "model_record": result.model_record.model_dump(mode="json")}, candidate)
        digest = sha256(candidate.read_bytes()).hexdigest()
        if path.exists() and sha256(path.read_bytes()).hexdigest() != digest:
            candidate.unlink()
            raise FileExistsError(f"immutable model differs: {path}")
        candidate.replace(path)
        model_paths[kind] = {"path": str(path), "sha256": digest}
    manifest = {
        "entry": entry,
        "policy": policy.model_dump(mode="json"),
        "policy_id": policy_id,
        "models": model_paths,
        "training_inputs": {"path": str(inputs_path), "sha256": inputs_digest},
        "teachers": [
            {
                "session_key": teacher.unit.session_key,
                "run_id": teacher.unit.run_id,
                "completed_cutoff_s": teacher.source_cutoff_s,
                "numerical_fit_sha256": teacher.numerical_fit_sha256,
                "training_input_sha256": teacher.training_input_sha256,
            }
            for teacher in teachers
        ],
        "transforms": {
            kind: {"features": result.transform.feature_names, "mean": result.transform.mean.tolist(), "scale": result.transform.scale.tolist()}
            for kind, result in results.items()
        },
        "model_records": {kind: result.model_record.model_dump(mode="json") for kind, result in results.items()},
        "training_resets": {kind: result.reset_reasons for kind, result in results.items()},
    }
    manifest_path = output_dir / "training_manifest.json"
    content = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if manifest_path.exists() and sha256(manifest_path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable manifest differs: {manifest_path}")
    manifest_path.write_text(content)
    return {"manifest_path": str(manifest_path), "manifest_sha256": digest, "training_inputs_path": str(inputs_path), "training_inputs_sha256": inputs_digest}


def _training_units(inputs: Phase3Inputs, entry: str) -> tuple[tuple[UpdateUnit, ...], int]:
    chunks = [chunk for chunk in inputs.chunks if chunk.entry == entry and chunk.split == "training"]
    grouped: dict[tuple[str, str], list] = {}
    for chunk in chunks:
        grouped.setdefault((chunk.session_key, chunk.run_id), []).append(chunk)
    permitted = set(inputs.continuations)
    units = []
    refused = 0
    for (session_key, run_id), run in grouped.items():
        ordered = sorted(run, key=lambda chunk: chunk.chunk_index)
        cutoff_s = float(ordered[-1].time_s[-1])
        closure = RunClosure(
            entry, session_key, run_id, "training", tuple(chunk.chunk_index for chunk in ordered), cutoff_s,
            tuple((earlier.chunk_index, later.chunk_index) for earlier, later in zip(ordered, ordered[1:]) if (session_key, entry, run_id, earlier.chunk_index, later.chunk_index) in permitted),
        )
        segments = tuple(
            UpdateSegment(
                entry, chunk.session_key, chunk.run_id, chunk.chunk_index, cutoff_s,
                float(chunk.time_s[0]), float(chunk.time_s[-1]), "training",
                np.column_stack((chunk.speed_ms, chunk.controls["throttle_pct"], chunk.controls["brake"])).astype(np.float32),
                np.column_stack((chunk.valid["speed_ms"], chunk.valid["throttle_pct"], chunk.valid["brake"])).astype(np.bool_),
                np.zeros(len(chunk.time_s), dtype=np.bool_),
            )
            for chunk in ordered
        )
        try:
            units.extend(assemble_update_units(segments, (closure,)))
        except ValueError:
            refused += 1
    return tuple(units), refused


def _precompute_window(unit: UpdateUnit, window: int = 64) -> UpdateUnit:
    features = unit.features[-window:].copy()
    valid = unit.valid[-window:].copy()
    padding = unit.padding[-window:].copy()
    missing = window - len(features)
    if missing > 0:
        features = np.concatenate((np.zeros((missing, features.shape[1]), dtype=np.float32), features))
        valid = np.concatenate((np.zeros((missing, valid.shape[1]), dtype=np.bool_), valid))
        padding = np.concatenate((np.ones(missing, dtype=np.bool_), padding))
    return UpdateUnit(unit.entry, unit.session_key, unit.run_id, unit.split, unit.completed_cutoff_s, features, valid, padding)


def _precedes_unit(chunk, unit: UpdateUnit) -> bool:
    return chunk.session_key < unit.session_key or (
        chunk.session_key == unit.session_key and float(chunk.time_s[-1]) <= unit.completed_cutoff_s
    )


def _unit_order_key(unit: UpdateUnit) -> tuple[str, float, str]:
    return unit.session_key, unit.completed_cutoff_s, unit.run_id


def _update_input_identifier(unit: UpdateUnit) -> str:
    return _identifier({"entry": unit.entry, "session": unit.session_key, "run": unit.run_id, "cutoff_s": unit.completed_cutoff_s, "features": unit.features.tolist(), "valid": unit.valid.tolist(), "padding": unit.padding.tolist()})


def _source_identifier(chunks) -> str:
    return _identifier([{"session": chunk.session_key, "run": chunk.run_id, "index": chunk.chunk_index, "time_s": chunk.time_s.tolist(), "speed_ms": chunk.speed_ms.tolist(), "controls": {name: values.tolist() for name, values in sorted(chunk.controls.items())}, "valid": {name: values.tolist() for name, values in sorted(chunk.valid.items())}} for chunk in chunks])


def _identifier(value: object) -> str:
    from hashlib import sha256
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
