from types import SimpleNamespace

import numpy as np
import pandas as pd

from poweshift_backend.representation.race_batches import build_complete_race_batches


def _geometry(progress: list[float], supported: list[bool], speed: float) -> SimpleNamespace:
    times = np.arange(len(progress), dtype=np.float64) * 0.25
    return SimpleNamespace(
        time_s=times,
        unwrapped_progress_laps=np.asarray(progress, dtype=np.float64),
        observed_speed_ms=np.full(len(times), speed, dtype=np.float64),
        supported_mask=np.asarray(supported, dtype=np.bool_),
        participation_start_s=0.0,
        participation_end_s=float(times[-1]),
    )


def test_complete_race_batches_keep_all_available_cars_and_discard_skips() -> None:
    geometries = {
        "1": _geometry([0.00, 0.03, 0.06, 0.09, 0.12], [True] * 5, 24.0),
        "2": _geometry([-0.02, 0.01, 0.04, 0.07, 0.10], [True, True, True, False, True], 23.0),
        "3": _geometry([-0.04, -0.01, 0.02, 0.05, 0.08], [True] * 5, 22.0),
    }
    rows = []
    for entry, speed in (("1", 86.4), ("2", 82.8), ("3", 79.2)):
        for index, time_s in enumerate(np.arange(-0.25, 1.26, 0.25)):
            rows.append(
                {
                    "source_row": int(entry) * 100 + index,
                    "DriverNumber": entry,
                    "SessionTime": pd.Timedelta(seconds=float(time_s)),
                    "Speed": speed,
                    "Throttle": 50.0,
                    "Brake": index == 2,
                }
            )

    batches, diagnostics, normalization = build_complete_race_batches(
        geometries,
        pd.DataFrame(rows),
        route_length_m=100.0,
        source_hash="a" * 64,
        window_s=0.5,
    )

    assert len(batches) == 2
    assert diagnostics[0]["entries"] == ["1", "2", "3"]
    assert diagnostics[1]["entries"] == ["1", "3"]
    assert batches[0].observed_speed.shape == (3, 3)
    assert batches[0].progress_pair_mask[:, 0, 1].all()
    assert batches[0].controls[..., 1].max().item() == 0.2
    assert batches[0].road_curvature_m_inv.count_nonzero().item() == 0
    assert normalization["samples"] == 64
