"""Strict resolution of source-supported two-corner routes."""

from poweshift_backend.contracts.route import TwoCornerRoute


def resolve_two_corner_route(
    routes: tuple[TwoCornerRoute, ...],
    route_id: str,
    required_line_maps: frozenset[str],
) -> TwoCornerRoute:
    """Resolve one route and every required source line map."""
    matches = tuple(route for route in routes if route.route_id == route_id)
    if len(matches) != 1:
        raise ValueError("supported route geometry must resolve exactly once")
    route = matches[0]
    missing = required_line_maps - route.line_maps
    if missing:
        raise ValueError("required route line maps are unavailable")
    return route
