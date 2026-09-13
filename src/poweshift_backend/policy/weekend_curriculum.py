"""Freeze chronological practice and race policy curricula."""

import json
from pathlib import Path


def ordered_training_sessions(sessions: tuple[dict, ...] | list[dict]) -> tuple[dict, ...]:
    """Order training sessions by event, with practice before race."""
    identifiers = [str(item.get("session_id", "")) for item in sessions]
    if len(set(identifiers)) != len(identifiers) or any(
        item.get("session_kind") not in {"practice", "race"}
        or not item.get("event_date")
        or not item.get("event_name")
        or not item.get("session_id")
        for item in sessions
    ):
        raise ValueError("curriculum sessions need unique training identities")
    return tuple(sorted(
        sessions,
        key=lambda item: (
            str(item["event_date"]),
            str(item["event_name"]),
            0 if item["session_kind"] == "practice" else 1,
            str(item["session_id"]),
        ),
    ))


def freeze_curriculum_manifest(path: Path, payload: dict) -> None:
    """Write one immutable manifest after checking split firewalls."""
    if payload.get("source_partition") != "training":
        raise ValueError("curriculum manifest requires the training partition")
    sessions = ordered_training_sessions(payload.get("sessions", []))
    if list(sessions) != payload.get("sessions", []):
        raise ValueError("curriculum manifest sessions are not chronological")
    for session in sessions:
        for split in session.get("profiles", {}).values():
            training = set(split.get("training_trace_ids", ()))
            validation = set(split.get("validation_trace_ids", ()))
            if training & validation:
                raise ValueError("race training and validation traces must be disjoint")
            if session["session_kind"] == "practice" and validation:
                raise ValueError("practice energy traces cannot define a validation split")
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise RuntimeError("frozen curriculum manifest differs from current evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
