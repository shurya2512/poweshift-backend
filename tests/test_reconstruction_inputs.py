import json
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from poweshift_backend.reconstruction.inputs import load_admitted_inputs


def _write_json(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload, sort_keys=True))
    return sha256(path.read_bytes()).hexdigest()


def _write_evidence(tmp_path: Path, *, package_split: str = "training") -> tuple[Path, Path]:
    bundle = tmp_path / "bundle.json"
    bundle_hash = _write_json(bundle, {"sessions": []})
    coverage = tmp_path / "coverage.json"
    coverage_hash = _write_json(
        coverage,
        {
            "choice": "admit_named_entries",
            "admitted_entries": {"2026-02-11": ["1"]},
            "excluded_entries": {"2026-02-11": {}},
            "reviewer": "reviewer",
            "recorded_on": "2026-09-12",
            "bundle_sha256": bundle_hash,
        },
    )
    preprocessing = tmp_path / "preprocessing.json"
    preprocessing_hash = _write_json(
        preprocessing,
        {
            "gap_limit_s": 1.16,
            "staleness_limit_s": 0.24,
            "smoothing_limit_s": 0.44,
            "window_limit_s": 190.761,
            "availability_convention": "current_past_prefix",
        },
    )
    table = tmp_path / "packages.parquet"
    pd.DataFrame(
        {
            "package_id": ["1__run__0", "1__run__0", "1__run__1", "1__run__1"],
            "row_index": [0, 1, 0, 1],
            "dt_s": [0.0, 0.25, 0.0, 0.25],
            "padding": [False, False, False, False],
            "X__speed_ms": [10.0, 11.0, 12.0, 13.0],
            "valid__speed_ms": [True, True, True, True],
            "X__throttle_pct": [40.0, 41.0, 42.0, 43.0],
            "valid__throttle_pct": [True, True, True, True],
            "X__brake": [0.0, 0.0, 1.0, 1.0],
            "valid__brake": [True, True, True, True],
            "X__n_gear": [4.0, 4.0, 5.0, 5.0],
            "valid__n_gear": [True, True, True, True],
        }
    ).to_parquet(table)
    packages = tmp_path / "packages.json"
    packages_hash = _write_json(
        packages,
        {
            "session_key": "2026-02-11",
            "table_path": str(table),
            "table_sha256": sha256(table.read_bytes()).hexdigest(),
            "packages": [
                {
                    "package_id": "1__run__0",
                    "entry": "1",
                    "run_id": "run",
                    "chunk_index": 0,
                    "start_time_s": 10.0,
                    "end_time_s": 10.25,
                    "split": package_split,
                    "feature_names": ["speed_ms", "throttle_pct", "brake", "n_gear"],
                    "tyre": {"compound": "MEDIUM"},
                    "provenance": {"source_identity": {"date": "2026-02-11"}, "source_rows": ["0", "1", "2", "3"]},
                },
                {
                    "package_id": "1__run__1",
                    "entry": "1",
                    "run_id": "run",
                    "chunk_index": 1,
                    "start_time_s": 10.5,
                    "end_time_s": 10.75,
                    "split": package_split,
                    "feature_names": ["speed_ms", "throttle_pct", "brake", "n_gear"],
                    "tyre": {"compound": "MEDIUM"},
                    "provenance": {"source_identity": {"date": "2026-02-11"}, "source_rows": ["0", "1", "2", "3"]},
                },
            ],
        },
    )
    track_table = tmp_path / "track.parquet"
    pd.DataFrame({"reference_progress": [0.0, 1.0]}).to_parquet(track_table)
    track = tmp_path / "track.json"
    track_hash = _write_json(
        track,
        {"table_path": str(track_table), "table_sha256": sha256(track_table.read_bytes()).hexdigest()},
    )
    evidence = tmp_path / "phase2.json"
    evidence_hash = _write_json(
        evidence,
        {
            "bundle_path": str(bundle),
            "bundle_sha256": bundle_hash,
            "coverage_disposition": {"path": str(coverage), "sha256": coverage_hash},
            "preprocessing_spec": {"path": str(preprocessing), "sha256": preprocessing_hash},
            "track_profile": {"manifest_path": str(track), "manifest_sha256": track_hash},
            "split_manifest": {
                "training": "Test 1",
                "selection": "2026-02-18",
                "final_evaluation": ["2026-02-19", "2026-02-20"],
            },
            "sessions": [
                {
                    "session_key": "2026-02-11",
                    "identity": {"date": "2026-02-11"},
                    "admitted_entries": ["1"],
                    "stint_packages": {"manifest_path": str(packages), "manifest_sha256": packages_hash},
                }
            ],
        },
    )
    split = {
        "training": "Test 1",
        "selection": "2026-02-18",
        "final_evaluation": ["2026-02-19", "2026-02-20"],
    }
    effective = sha256(
        json.dumps(
            {
                "coverage_disposition_sha256": coverage_hash,
                "preprocessing_spec_sha256": preprocessing_hash,
                "phase2_evidence_manifest_sha256": evidence_hash,
                "split_manifest": split,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    admission = tmp_path / "phase3_admission.json"
    _write_json(
        admission,
        {
            "phase2_evidence_manifest_sha256": evidence_hash,
            "coverage_disposition_sha256": coverage_hash,
            "preprocessing_spec_sha256": preprocessing_hash,
            "split_manifest": split,
            "effective_manifest_sha256": effective,
            "approved_by": "human",
            "approved_defaults": {
                "gap_limit_s": 1.16,
                "smoothing_limit_s": 0.44,
                "window_limit_s": 190.761,
                "staleness_policy": "recorded_not_used",
            },
        },
    )
    return evidence, admission


def test_load_admitted_inputs_uses_physical_speed_and_anchored_chunk_time(tmp_path: Path) -> None:
    inputs = load_admitted_inputs(*_write_evidence(tmp_path))

    assert inputs.chunks[0].time_s.tolist() == [10.0, 10.25]
    assert inputs.chunks[1].time_s.tolist() == [10.5, 10.75]
    assert inputs.chunks[0].speed_ms.tolist() == [10.0, 11.0]
    assert inputs.chunks[1].controls["throttle_pct"].tolist() == [42.0, 43.0]
    assert inputs.chunks[1].source_rows == ("2", "3")
    assert inputs.continuations == (("2026-02-11", "1", "run", 0, 1),)


def test_load_admitted_inputs_rejects_a_changed_pinned_table(tmp_path: Path) -> None:
    evidence, admission = _write_evidence(tmp_path)
    pd.DataFrame({"changed": [1]}).to_parquet(tmp_path / "packages.parquet")

    with pytest.raises(ValueError, match="does not match"):
        load_admitted_inputs(evidence, admission)


def test_load_admitted_inputs_derives_split_from_source_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="split"):
        load_admitted_inputs(*_write_evidence(tmp_path, package_split="final_evaluation"))


def test_load_admitted_inputs_never_joins_separate_runs(tmp_path: Path) -> None:
    evidence, admission = _write_evidence(tmp_path)
    manifest = json.loads((tmp_path / "packages.json").read_text())
    manifest["packages"][1]["run_id"] = "other-run"
    manifest_hash = _write_json(tmp_path / "packages.json", manifest)
    phase = json.loads(evidence.read_text())
    phase["sessions"][0]["stint_packages"]["manifest_sha256"] = manifest_hash
    evidence_hash = _write_json(evidence, phase)
    approved = json.loads(admission.read_text())
    approved["phase2_evidence_manifest_sha256"] = evidence_hash
    approved["effective_manifest_sha256"] = sha256(
        json.dumps(
            {
                "coverage_disposition_sha256": approved["coverage_disposition_sha256"],
                "preprocessing_spec_sha256": approved["preprocessing_spec_sha256"],
                "phase2_evidence_manifest_sha256": evidence_hash,
                "split_manifest": approved["split_manifest"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    _write_json(admission, approved)

    assert load_admitted_inputs(evidence, admission).continuations == ()


def test_load_admitted_inputs_rejects_an_unapproved_evidence_manifest(tmp_path: Path) -> None:
    evidence, admission = _write_evidence(tmp_path)
    phase = json.loads(evidence.read_text())
    phase["sessions"] = []
    _write_json(evidence, phase)

    with pytest.raises(ValueError, match="approval"):
        load_admitted_inputs(evidence, admission)


def test_load_admitted_inputs_rejects_limits_outside_the_approved_defaults(tmp_path: Path) -> None:
    evidence, admission = _write_evidence(tmp_path)
    preprocessing = json.loads((tmp_path / "preprocessing.json").read_text())
    preprocessing["gap_limit_s"] = 2.0
    preprocessing_hash = _write_json(tmp_path / "preprocessing.json", preprocessing)
    phase = json.loads(evidence.read_text())
    phase["preprocessing_spec"]["sha256"] = preprocessing_hash
    evidence_hash = _write_json(evidence, phase)
    approved = json.loads(admission.read_text())
    approved["preprocessing_spec_sha256"] = preprocessing_hash
    approved["phase2_evidence_manifest_sha256"] = evidence_hash
    approved["effective_manifest_sha256"] = sha256(
        json.dumps(
            {
                "coverage_disposition_sha256": approved["coverage_disposition_sha256"],
                "preprocessing_spec_sha256": preprocessing_hash,
                "phase2_evidence_manifest_sha256": evidence_hash,
                "split_manifest": approved["split_manifest"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    _write_json(admission, approved)

    with pytest.raises(ValueError, match="approved defaults"):
        load_admitted_inputs(evidence, admission)
