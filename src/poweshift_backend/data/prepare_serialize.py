"""Write Phase 2 artifacts as reproducible parquet tables plus JSON manifests."""

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from poweshift_backend.data.export import write_manifest, write_table
from poweshift_backend.events.timeline import TimelineEvent
from poweshift_backend.geometry.reference import TrackProfile
from poweshift_backend.information.projector import PitProjection
from poweshift_backend.prepare.windows import StintPackage
from poweshift_backend.targets.bundle import TargetBundle


def write_stint_packages(packages: list[StintPackage], session_key: str, out_dir: Path) -> dict:
    """Write one session's stint packages as a long table plus a metadata manifest."""
    rows = []
    package_records = []
    for package in packages:
        package_id = f"{package.entry}__{package.run_id}__{package.chunk_index}"
        for row_index in range(package.X.shape[0]):
            row = {"package_id": package_id, "row_index": row_index, "dt_s": float(package.dt_s[row_index]), "padding": bool(package.padding[row_index])}
            for col, name in enumerate(package.feature_names):
                row[f"X__{name}"] = float(package.X[row_index, col])
                row[f"valid__{name}"] = bool(package.valid[row_index, col])
                row[f"origin__{name}"] = int(package.origin[row_index, col])
            rows.append(row)
        package_records.append(
            {
                "package_id": package_id,
                "entry": package.entry,
                "session_key": package.session_key,
                "run_id": package.run_id,
                "chunk_index": package.chunk_index,
                "start_time_s": package.start_time_s,
                "end_time_s": package.end_time_s,
                "completed_cutoff_s": package.completed_cutoff_s,
                "feature_names": list(package.feature_names),
                "tyre": asdict(package.tyre),
                "programme_context": package.programme_context,
                "quality_context": package.quality_context,
                "availability_convention": package.availability_convention,
                "split": package.split,
                "provenance": package.provenance.model_dump(mode="json"),
            }
        )
    table_path = out_dir / f"stint_packages__{session_key}.parquet"
    table_sha256 = write_table(pd.DataFrame(rows), table_path)
    manifest_path = out_dir / f"stint_packages__{session_key}.json"
    manifest_sha256 = write_manifest(
        {"session_key": session_key, "table_path": str(table_path), "table_sha256": table_sha256, "packages": package_records}, manifest_path
    )
    return {"table_path": str(table_path), "table_sha256": table_sha256, "manifest_path": str(manifest_path), "manifest_sha256": manifest_sha256, "n_packages": len(packages)}


def write_event_timeline(events: list[TimelineEvent], session_key: str, out_dir: Path) -> dict:
    """Write one session's timestamped events as a JSON manifest, ordered by time."""
    ordered = sorted(events, key=lambda event: event.time_s)
    manifest_path = out_dir / f"event_timeline__{session_key}.json"
    manifest_sha256 = write_manifest(
        {"session_key": session_key, "events": [event.model_dump(mode="json") for event in ordered]}, manifest_path
    )
    return {"manifest_path": str(manifest_path), "manifest_sha256": manifest_sha256, "n_events": len(ordered)}


def write_track_profile(profile: TrackProfile, source_label: str, out_dir: Path) -> dict:
    """Write the shared TrackProfile as a small table plus a metadata manifest."""
    table = pd.DataFrame(
        {
            "reference_progress": profile.reference_progress,
            "actual_distance_m": profile.actual_distance_m,
            "curvature_m_inv": profile.curvature_m_inv,
            "curvature_valid_mask": profile.curvature_valid_mask,
        }
    )
    table_path = out_dir / f"track_profile__{source_label}.parquet"
    table_sha256 = write_table(table, table_path)
    manifest_path = out_dir / f"track_profile__{source_label}.json"
    manifest_sha256 = write_manifest(
        {
            "source_label": source_label,
            "table_path": str(table_path),
            "table_sha256": table_sha256,
            "provenance": profile.provenance.model_dump(mode="json"),
            "coordinate_transform": profile.coordinate_transform.model_dump(mode="json"),
        },
        manifest_path,
    )
    return {"table_path": str(table_path), "table_sha256": table_sha256, "manifest_path": str(manifest_path), "manifest_sha256": manifest_sha256}


def write_target_bundle(bundle: TargetBundle, session_key: str, out_dir: Path) -> dict:
    """Write one target-kind bundle for one session as an isolated JSON manifest."""
    manifest_path = out_dir / f"target_bundle__{bundle.target_kind.value}__{session_key}.json"
    manifest_sha256 = write_manifest(bundle.model_dump(mode="json"), manifest_path)
    return {"manifest_path": str(manifest_path), "manifest_sha256": manifest_sha256, "n_records": len(bundle.records)}


def write_pit_projection(projection: PitProjection, session_key: str, out_dir: Path) -> dict:
    """Write one session's isolated pit-source projection as its own JSON manifest."""
    manifest_path = out_dir / f"pit_projection__{session_key}.json"
    manifest_sha256 = write_manifest(projection.model_dump(mode="json"), manifest_path)
    return {"manifest_path": str(manifest_path), "manifest_sha256": manifest_sha256, "n_records": len(projection.records)}
