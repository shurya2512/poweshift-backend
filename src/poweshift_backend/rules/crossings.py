"""Rule-line lookup with explicit missing-map refusal."""

from poweshift_backend.contracts.rules import RegulatoryRuleSnapshot


def require_line_map(snapshot: RegulatoryRuleSnapshot, line_map_id: str) -> str:
    """Return a declared line-map id or refuse coverage."""
    if line_map_id not in snapshot.line_maps:
        raise ValueError("required rule line map is unavailable")
    return line_map_id
