"""Frozen policy feature, action and recurrent-state schema."""

from dataclasses import dataclass

from poweshift_backend.contracts.action import Manoeuvre


@dataclass(frozen=True)
class PolicySchema:
    """Compatibility boundary for one recurrent actor and critic."""

    schema_id: str
    feature_names: tuple[str, ...]
    manoeuvres: tuple[Manoeuvre, ...]
    recurrent_width: int
    action_transform_id: str

    def __post_init__(self) -> None:
        if not self.schema_id or not self.action_transform_id or self.recurrent_width < 1:
            raise ValueError("policy schema identity and recurrent width are required")
        if not self.feature_names or len(self.feature_names) != len(set(self.feature_names)):
            raise ValueError("policy feature names must be nonempty and unique")
        if not self.manoeuvres or len(self.manoeuvres) != len(set(self.manoeuvres)):
            raise ValueError("policy manoeuvres must be nonempty and unique")
