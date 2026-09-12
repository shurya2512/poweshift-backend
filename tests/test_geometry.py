from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.acquisition import SessionIdentity
from poweshift_backend.contracts.preparation import ArtifactProvenance, CoverageState
from poweshift_backend.geometry.reference import UNSUPPORTED_GEOMETRY, TrackProfile, build_track_profile


def _provenance(**overrides) -> ArtifactProvenance:
    session = SessionIdentity(
        year=2026,
        test_number=1,
        day_number=1,
        date=date(2026, 2, 11),
        venue="Bahrain",
        session_kind="preseason_test",
    )
    fields = {
        "source_identity": session,
        "source_rows": ("0", "1", "2", "3"),
        "coverage_state": CoverageState.ADMITTED,
        "config_version": "geometry-v1",
    }
    fields.update(overrides)
    return ArtifactProvenance(**fields)


def _straight_line_native() -> pd.DataFrame:
    # 3 metres of straight travel in native 1/10 metre units.
    return pd.DataFrame({"X": [0.0, 10.0, 20.0, 30.0], "Y": [0.0, 0.0, 0.0, 0.0]})


def _quarter_circle_native(radius_m: float = 100.0, points: int = 50) -> pd.DataFrame:
    theta = np.linspace(0.0, np.pi / 2, points)
    x_m = radius_m * np.cos(theta)
    y_m = radius_m * np.sin(theta)
    return pd.DataFrame({"X": x_m / 0.1, "Y": y_m / 0.1})


def test_build_track_profile_scales_native_decimetre_coordinates_to_metric_distance() -> None:
    profile = build_track_profile(_straight_line_native(), _provenance())

    assert profile.coordinate_transform.scale == 0.1
    assert profile.coordinate_transform.source_unit == "decimetre"
    np.testing.assert_allclose(profile.actual_distance_m, [0.0, 1.0, 2.0, 3.0])
    np.testing.assert_allclose(profile.reference_progress, [0.0, 1 / 3, 2 / 3, 1.0])


def test_build_track_profile_reports_near_zero_curvature_on_a_straight_reference_path() -> None:
    profile = build_track_profile(_straight_line_native(), _provenance())

    np.testing.assert_allclose(profile.curvature_m_inv, 0.0, atol=1e-9)


def test_build_track_profile_marks_only_the_first_and_last_curvature_samples_as_unsupported() -> None:
    profile = build_track_profile(_quarter_circle_native(), _provenance())

    assert profile.curvature_valid_mask.dtype == np.bool_
    assert list(profile.curvature_valid_mask) == (
        [False] + [True] * (len(profile.curvature_valid_mask) - 2) + [False]
    )


def test_build_track_profile_computes_curvature_matching_the_known_radius_of_a_curved_path() -> None:
    radius_m = 100.0
    profile = build_track_profile(_quarter_circle_native(radius_m=radius_m), _provenance())

    valid_curvature = profile.curvature_m_inv[profile.curvature_valid_mask]
    assert np.median(np.abs(valid_curvature)) == pytest.approx(1.0 / radius_m, rel=1e-6)
    assert np.isfinite(profile.curvature_m_inv).all()


def test_build_track_profile_marks_grade_and_width_as_unavailable_never_a_number() -> None:
    profile = build_track_profile(_straight_line_native(), _provenance())

    assert "grade" in UNSUPPORTED_GEOMETRY
    assert "width" in UNSUPPORTED_GEOMETRY
    assert "corner_boundaries" in UNSUPPORTED_GEOMETRY
    assert "connected_routes" in UNSUPPORTED_GEOMETRY
    assert "pit_branch" in UNSUPPORTED_GEOMETRY
    assert "rule_line_mappings" in UNSUPPORTED_GEOMETRY

    with pytest.raises(ValidationError, match="width"):
        TrackProfile(
            provenance=profile.provenance,
            coordinate_transform=profile.coordinate_transform,
            reference_progress=profile.reference_progress,
            actual_distance_m=profile.actual_distance_m,
            curvature_m_inv=profile.curvature_m_inv,
            curvature_valid_mask=profile.curvature_valid_mask,
            width=1.2,
        )


def test_track_profile_cannot_accept_an_unsupported_geometry_override_at_construction() -> None:
    profile = build_track_profile(_straight_line_native(), _provenance())

    with pytest.raises(ValidationError, match="unsupported_geometry"):
        TrackProfile(
            provenance=profile.provenance,
            coordinate_transform=profile.coordinate_transform,
            reference_progress=profile.reference_progress,
            actual_distance_m=profile.actual_distance_m,
            curvature_m_inv=profile.curvature_m_inv,
            curvature_valid_mask=profile.curvature_valid_mask,
            unsupported_geometry=frozenset(),
        )


def test_build_track_profile_rejects_a_reference_path_shorter_than_two_points() -> None:
    with pytest.raises(ValueError, match="at least two"):
        build_track_profile(pd.DataFrame({"X": [0.0], "Y": [0.0]}), _provenance())


def test_build_track_profile_rejects_coordinates_that_do_not_advance() -> None:
    stalled = pd.DataFrame({"X": [0.0, 0.0], "Y": [0.0, 0.0]})

    with pytest.raises(ValueError, match="strictly advance"):
        build_track_profile(stalled, _provenance())


def test_track_profile_is_frozen_against_later_attribute_assignment() -> None:
    profile = build_track_profile(_straight_line_native(), _provenance())

    with pytest.raises(ValidationError):
        profile.actual_distance_m = np.array([0.0])


def test_track_profile_arrays_reject_in_place_writes() -> None:
    profile = build_track_profile(_straight_line_native(), _provenance())

    with pytest.raises(ValueError, match="read-only"):
        profile.actual_distance_m[0] = 99.0
