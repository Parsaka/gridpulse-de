import io
from datetime import date

import pandas as pd
import pytest

from gridpulse.config import Settings, make_store
from gridpulse.storage import AdlsBronzeStore, BronzeStore


class FakeFile:
    def __init__(self, store: dict, path: str):
        self.store, self.path = store, path

    def upload_data(self, data: bytes, overwrite: bool = False):
        assert overwrite is True
        self.store[self.path] = data

    def download_file(self):
        data = self.store[self.path]
        return type("D", (), {"readall": lambda self: data})()


class FakeFS:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def get_file_client(self, path):
        return FakeFile(self.files, path)

    def get_paths(self, path):
        return [type("P", (), {"name": n})() for n in self.files if n.startswith(path)]


def _store_with_fake() -> tuple[AdlsBronzeStore, FakeFS]:
    store = AdlsBronzeStore.__new__(AdlsBronzeStore)  # skip real Azure client construction
    store.fs = FakeFS()
    return store, store.fs


def test_adls_write_is_idempotent_and_partitioned():
    store, fs = _store_with_fake()
    ts = pd.date_range("2025-01-01", periods=48, freq="h", tz="UTC")
    df = pd.DataFrame({"timestamp": ts, "value": range(48)})
    assert store.write(df, "smard", "x") == 48
    assert store.write(df, "smard", "x") == 48
    assert sorted(fs.files) == [
        "smard/x/date=2025-01-01/part.parquet",
        "smard/x/date=2025-01-02/part.parquet",
    ]
    out = store.read("smard", "x")
    assert len(out) == 48 and out["timestamp"].is_unique
    pd.read_parquet(io.BytesIO(fs.files["smard/x/date=2025-01-01/part.parquet"]))


def test_partition_path_matches_local_layout(tmp_path):
    local = BronzeStore(tmp_path).partition_path("a", "b", date(2025, 1, 1))
    assert local.relative_to(tmp_path).as_posix() == AdlsBronzeStore.partition_path(
        "a", "b", date(2025, 1, 1)
    )


def test_make_store_selects_backend(tmp_path):
    assert isinstance(make_store(Settings(data_dir=tmp_path)), BronzeStore)
    with pytest.raises(RuntimeError):
        make_store(Settings(storage_backend="adls"))
    with pytest.raises(ValueError):
        make_store(Settings(storage_backend="nope"))
