import pytest

from poweshift_backend.contracts.powertrain import EvidenceOrigin
from poweshift_backend.contracts.route import RouteSegment, TwoCornerRoute
from poweshift_backend.geometry.routes import resolve_two_corner_route


def _segments() -> tuple[RouteSegment, RouteSegment]:
    return (
        RouteSegment("corner-1", "a", "b", 120.0, "geometry-a", "a" * 64, (("timing_line", 20.0),)),
        RouteSegment("corner-2", "b", "c", 180.0, "geometry-a", "a" * 64, (("pit_entry", 150.0),)),
    )


def test_two_corner_route_requires_connectivity_and_continuation() -> None:
    route = TwoCornerRoute("route-a", _segments(), 80.0, EvidenceOrigin.SOURCE_DERIVED)

    assert route.total_length_m == pytest.approx(380.0)
    broken = (_segments()[0], RouteSegment("corner-2", "x", "c", 180.0, "geometry-a", "a" * 64, ()))
    with pytest.raises(ValueError, match="connected"):
        TwoCornerRoute("route-b", broken, 80.0, EvidenceOrigin.SOURCE_DERIVED)


def test_route_resolver_refuses_missing_geometry_or_rule_line() -> None:
    route = TwoCornerRoute("route-a", _segments(), 80.0, EvidenceOrigin.SOURCE_DERIVED)

    assert resolve_two_corner_route((route,), "route-a", frozenset({"timing_line"})) is route
    with pytest.raises(ValueError, match="line"):
        resolve_two_corner_route((route,), "route-a", frozenset({"unknown"}))
    with pytest.raises(ValueError, match="geometry"):
        resolve_two_corner_route((), "route-a", frozenset())
