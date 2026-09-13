"""Powertrain enforcement at source-defined rule boundaries."""

from datetime import datetime

from poweshift_backend.contracts.powertrain import PowertrainAllocation
from poweshift_backend.contracts.rules import RegulatoryRuleSnapshot


def enforce_powertrain_rules(
    snapshot: RegulatoryRuleSnapshot,
    allocation: PowertrainAllocation,
    season: int,
    event_id: str,
    session: str,
    at: datetime,
    line_map_id: str,
    mode: str,
) -> None:
    """Refuse incompatible context, boundaries, modes or power."""
    if not snapshot.applies_to(season, event_id, session, at):
        raise ValueError("rule snapshot does not apply to this historical context")
    if line_map_id not in snapshot.line_maps:
        raise ValueError("required rule line map is unavailable")
    if mode in snapshot.unsupported_modes:
        raise ValueError("requested rule mode is unsupported")
    for limit in snapshot.limits:
        if limit.line_map_id is not None and limit.line_map_id != line_map_id:
            continue
        if limit.name == "motor_power" and abs(allocation.electrical.motor_dc_power_w) > limit.value:
            raise ValueError("motor power exceeds the applicable rule limit")
