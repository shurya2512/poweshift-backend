import json

import torch
import pytest

from poweshift_backend.representation.qualifying_batches import _diagnostic_controls_and_curvature, build_qualifying_smoke_artifact


def test_builder_refuses_a_route_bound_to_another_qualifying_export(tmp_path) -> None:
    export = tmp_path / "qualifying_export.json"
    export.write_text(json.dumps({"kind": "source_bound_qualifying_export_v1"}))
    route = tmp_path / "static_route_manifest.json"
    route.write_text(json.dumps({"source_binding": {"manifest_sha256": "0" * 64}}))

    with pytest.raises(ValueError, match="route must bind"):
        build_qualifying_smoke_artifact(export, route, tmp_path / "artifact.pt", tmp_path / "binding.json")


def test_diagnostic_hotfix_marks_and_neutralizes_unsupported_inputs() -> None:
    controls = torch.tensor([[[0.4, 0.0]], [[1.04, 1.0]]], dtype=torch.float64)
    fixed_controls, fixed_curvature = _diagnostic_controls_and_curvature(
        controls, torch.tensor([0.02, -0.01], dtype=torch.float64)
    )

    assert fixed_controls[..., 0].tolist() == [[0.4], [1.0]]
    assert fixed_controls[..., 1].tolist() == [[0.0], [0.2]]
    assert fixed_curvature.tolist() == [0.0, 0.0]
