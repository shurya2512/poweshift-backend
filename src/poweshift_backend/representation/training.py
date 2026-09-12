"""Training-only teacher distillation for the bounded offline candidates."""

from dataclasses import dataclass
from hashlib import sha256
import json
from time import perf_counter

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from poweshift_backend.contracts.representation import ComparisonPolicy, ModelRecord
from poweshift_backend.representation.inputs import UpdateUnit
from poweshift_backend.representation.models import CandidateConfig, build_candidate


@dataclass(frozen=True)
class TeacherProfile:
    """A numerical profile fitted from one permitted training update unit."""

    unit: UpdateUnit
    target: np.ndarray
    numerical_fit_sha256: str
    training_input_sha256: str
    policy_id: str
    source_cutoff_s: float
    physical_target: np.ndarray
    profile_upper_bounds: np.ndarray

    def __post_init__(self) -> None:
        identifiers = (self.numerical_fit_sha256, self.training_input_sha256, self.policy_id)
        if any(len(value) != 64 or any(character not in "0123456789abcdef" for character in value) for value in identifiers):
            raise ValueError("teacher provenance must use sha256 identifiers")
        if self.source_cutoff_s != self.unit.completed_cutoff_s:
            raise ValueError("teacher provenance must pin its numerical fit and completed cutoff")
        if self.target.dtype != np.float32 or self.target.ndim != 1 or not np.isfinite(self.target).all():
            raise ValueError("teacher target must be a finite float32 vector")
        if np.any((self.target < 0.0) | (self.target > 1.0)):
            raise ValueError("teacher target must stay within decoder bounds")
        if self.physical_target.dtype != np.float32 or self.profile_upper_bounds.dtype != np.float32:
            raise ValueError("teacher physical targets and bounds must be float32")
        if self.physical_target.shape != self.target.shape or self.profile_upper_bounds.shape != self.target.shape:
            raise ValueError("teacher physical targets and bounds must match the decoder")
        if not np.isfinite(self.physical_target).all() or np.any(self.profile_upper_bounds <= 0.0):
            raise ValueError("teacher physical targets and bounds must be finite positive values")
        if not np.allclose(self.target, np.clip(self.physical_target / self.profile_upper_bounds, 0.0, 1.0)):
            raise ValueError("teacher target must use its frozen shared bounds")
        for values in (self.target, self.physical_target, self.profile_upper_bounds):
            values.setflags(write=False)


@dataclass(frozen=True)
class FrozenUpdateTransform:
    """Training-only standardisation saved with every candidate record."""

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray

    @property
    def identifier(self) -> str:
        payload = {"features": self.feature_names, "mean": self.mean.tolist(), "scale": self.scale.tolist()}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def apply(self, unit: UpdateUnit) -> np.ndarray:
        """Apply the saved transform without inspecting held-out values."""
        values = np.where(unit.valid, unit.features, 0.0).astype(np.float32, copy=True)
        values[unit.valid] = ((values[unit.valid] - np.broadcast_to(self.mean, values.shape)[unit.valid]) /
                              np.broadcast_to(self.scale, values.shape)[unit.valid]).astype(np.float32)
        return values


@dataclass(frozen=True)
class TrainingResult:
    """Frozen candidate, transform and bounded optimization evidence."""

    model: nn.Module
    transform: FrozenUpdateTransform
    model_record: ModelRecord
    losses: tuple[float, ...]
    optimizer_steps: int
    optimizer_seconds: float
    reset_reasons: tuple[str, ...]


def train_distilled_candidate(
    kind: str,
    config: CandidateConfig,
    teachers: tuple[TeacherProfile, ...],
    policy: ComparisonPolicy,
    *,
    feature_names: tuple[str, ...],
    policy_id: str,
    optimizer_steps: int | None = None,
) -> TrainingResult:
    """Fit one candidate only to numerical teachers from the training partition."""
    if not teachers:
        raise ValueError("candidate training needs at least one teacher profile")
    if policy_id != policy_identifier(policy) or any(teacher.policy_id != policy_id for teacher in teachers):
        raise ValueError("teacher policy does not match the selected comparison policy")
    if any(teacher.unit.split != "training" for teacher in teachers):
        raise ValueError("teacher profiles must come from training evidence only")
    if any(teacher.unit.features.shape[1] != config.feature_width for teacher in teachers):
        raise ValueError("teacher features do not match the candidate record")
    if len(teachers) > policy.candidate_max_units:
        raise ValueError("teacher count exceeds the frozen candidate unit budget")
    if any(len(teacher.target) != config.profile_width for teacher in teachers):
        raise ValueError("teacher target does not match the bounded decoder")
    bounds = teachers[0].profile_upper_bounds
    if any(not np.array_equal(teacher.profile_upper_bounds, bounds) for teacher in teachers[1:]):
        raise ValueError("teacher profiles must share frozen physical bounds")
    transform = _fit_transform(feature_names, tuple(teacher.unit for teacher in teachers))
    torch.manual_seed(policy.candidate_seed)
    model = build_candidate(kind, config)
    optimizer = torch.optim.Adam(model.parameters(), lr=policy.candidate_learning_rate, foreach=False)
    requested_steps = optimizer_steps or policy.candidate_epochs * len(teachers)
    if requested_steps < 1:
        raise ValueError("optimizer step budget must be positive")
    losses = []
    reset_reasons = []
    previous = None
    prior_teacher = None
    started = perf_counter()
    for step in range(requested_steps):
        teacher = teachers[step % len(teachers)]
        if prior_teacher is None or step % len(teachers) == 0:
            previous = torch.zeros((1, config.latent_width), dtype=torch.float32)
            reset_reasons.append("training_pass")
        elif teacher.unit.entry != prior_teacher.unit.entry:
            previous = torch.zeros((1, config.latent_width), dtype=torch.float32)
            reset_reasons.append("entry_boundary")
        elif teacher.unit.session_key != prior_teacher.unit.session_key:
            previous = torch.zeros((1, config.latent_width), dtype=torch.float32)
            reset_reasons.append("session_boundary")
        features = torch.from_numpy(transform.apply(teacher.unit)).unsqueeze(0)
        valid = torch.tensor(teacher.unit.valid & ~teacher.unit.padding[:, None], dtype=torch.bool).unsqueeze(0)
        target = torch.tensor(teacher.target, dtype=torch.float32).unsqueeze(0)
        optimizer.zero_grad()
        profile, variance, next_latent = model.distribution(features, valid, previous)
        loss = F.gaussian_nll_loss(profile, target, variance, full=True)
        if not torch.isfinite(loss):
            raise ValueError("candidate optimization produced a nonfinite NLL")
        loss.backward()
        if any(parameter.grad is not None and not torch.isfinite(parameter.grad).all() for parameter in model.parameters()):
            raise ValueError("candidate optimization produced a nonfinite gradient")
        optimizer.step()
        losses.append(float(loss.detach()))
        previous = next_latent.detach()
        prior_teacher = teacher
    elapsed = perf_counter() - started
    if elapsed > policy.candidate_runtime_budget_s:
        raise ValueError("candidate optimization exceeded the frozen runtime budget")
    model.eval()
    return TrainingResult(
        model=model,
        transform=transform,
        model_record=ModelRecord(
            candidate=kind,
            feature_names=feature_names,
            transform_id=transform.identifier,
            policy_id=policy_id,
            training_input_sha256=_combined_identifier(teacher.training_input_sha256 for teacher in teachers),
            teacher_fit_sha256=_combined_identifier(teacher.numerical_fit_sha256 for teacher in teachers),
            profile_component_names=("propulsion", "resistance", "braking", "grip"),
            profile_upper_bounds=tuple(float(value) for value in bounds),
            latent_width=config.latent_width,
            hidden_width=config.hidden_width,
            layers=config.layers,
            heads=config.heads,
            feedforward_width=config.feedforward_width,
            variance_floor=config.variance_floor,
            objective="gaussian_nll_full",
        ),
        losses=tuple(losses),
        optimizer_steps=requested_steps,
        optimizer_seconds=elapsed,
        reset_reasons=tuple(dict.fromkeys(reset_reasons)),
    )


def policy_identifier(policy: ComparisonPolicy) -> str:
    """Hash the exact selected comparison policy."""
    return sha256(json.dumps(policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _combined_identifier(identifiers) -> str:
    return sha256(json.dumps(tuple(identifiers), separators=(",", ":")).encode()).hexdigest()


def _fit_transform(feature_names: tuple[str, ...], units: tuple[UpdateUnit, ...]) -> FrozenUpdateTransform:
    if not feature_names or any(unit.features.shape[1] != len(feature_names) for unit in units):
        raise ValueError("feature names must match every training update unit")
    values = np.concatenate([unit.features for unit in units])
    valid = np.concatenate([unit.valid & ~unit.padding[:, None] for unit in units])
    mean = np.zeros(len(feature_names), dtype=np.float32)
    scale = np.ones(len(feature_names), dtype=np.float32)
    for index in range(len(feature_names)):
        column = values[valid[:, index], index]
        if column.size:
            mean[index] = column.mean(dtype=np.float64)
            standard_deviation = column.std(dtype=np.float64)
            scale[index] = standard_deviation if standard_deviation > 0.0 else 1.0
    mean.setflags(write=False)
    scale.setflags(write=False)
    return FrozenUpdateTransform(feature_names, mean, scale)
