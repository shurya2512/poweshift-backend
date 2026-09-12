import pandas as pd
import pytest

from poweshift_backend.data.export import write_manifest, write_table


def test_refuses_to_replace_an_immutable_table_with_different_records(tmp_path) -> None:
    path = tmp_path / "laps.parquet"
    write_table(pd.DataFrame({"Speed": [100.0]}), path)
    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        write_table(pd.DataFrame({"Speed": [101.0]}), path)

    assert path.read_bytes() == original


def test_refuses_to_replace_an_immutable_manifest_with_different_content(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    write_manifest({"coverage": "present"}, path)
    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        write_manifest({"coverage": "missing"}, path)

    assert path.read_bytes() == original
