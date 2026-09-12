import pytest

from poweshift_backend.data.protected_dirs import check_protected_directories


def _dirs(tmp_path):
    reconstruction = tmp_path / "reconstruction_inputs"
    targets = tmp_path / "targets"
    pit = tmp_path / "pit_source"
    for path in (reconstruction, targets, pit):
        path.mkdir()
    return reconstruction, targets, pit


def test_passes_when_each_artifact_kind_stays_in_its_own_root(tmp_path) -> None:
    reconstruction, targets, pit = _dirs(tmp_path)
    (reconstruction / "stint_packages__2026-02-11.json").write_text("{}")
    (targets / "target_bundle__lap_time__2026-02-11.json").write_text("{}")
    (pit / "pit_projection__2026-02-11.json").write_text("{}")

    check_protected_directories(reconstruction, targets, pit)


def test_fails_when_a_target_artifact_leaks_into_the_reconstruction_input_root(tmp_path) -> None:
    reconstruction, targets, pit = _dirs(tmp_path)
    (reconstruction / "target_bundle__lap_time__2026-02-11.json").write_text("{}")

    with pytest.raises(ValueError, match="reconstruction-input root"):
        check_protected_directories(reconstruction, targets, pit)


def test_fails_when_a_pit_artifact_leaks_into_the_reconstruction_input_root(tmp_path) -> None:
    reconstruction, targets, pit = _dirs(tmp_path)
    (reconstruction / "pit_projection__2026-02-11.json").write_text("{}")

    with pytest.raises(ValueError, match="reconstruction-input root"):
        check_protected_directories(reconstruction, targets, pit)


def test_fails_when_a_pit_artifact_leaks_into_the_targets_root(tmp_path) -> None:
    reconstruction, targets, pit = _dirs(tmp_path)
    (targets / "pit_projection__2026-02-11.json").write_text("{}")

    with pytest.raises(ValueError, match="targets root"):
        check_protected_directories(reconstruction, targets, pit)


def test_a_target_artifact_is_allowed_in_the_targets_root(tmp_path) -> None:
    reconstruction, targets, pit = _dirs(tmp_path)
    (targets / "target_bundle__lap_time__2026-02-11.json").write_text("{}")

    check_protected_directories(reconstruction, targets, pit)


def test_tolerates_a_missing_root_directory(tmp_path) -> None:
    check_protected_directories(tmp_path / "absent_a", tmp_path / "absent_b", tmp_path / "absent_c")
