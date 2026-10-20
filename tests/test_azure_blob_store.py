import io
import os
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from gridpulse.config import Settings, make_store
from gridpulse.storage import AzureBlobBronzeStore, BronzeStore


class FakeContainer:
    """Just enough of azure.storage.blob.ContainerClient for the store."""

    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def upload_blob(self, name, data, overwrite=False):
        assert overwrite is True
        self.blobs[name] = data

    def list_blobs(self, name_starts_with=""):
        return [
            SimpleNamespace(name=n) for n in sorted(self.blobs) if n.startswith(name_starts_with)
        ]

    def download_blob(self, name):
        data = self.blobs[name]
        return SimpleNamespace(readall=lambda: data)


def _fake_store() -> tuple[AzureBlobBronzeStore, FakeContainer]:
    store = AzureBlobBronzeStore.__new__(AzureBlobBronzeStore)  # skip real client construction
    store.container = FakeContainer()
    return store, store.container


def _frame(hours=48):
    ts = pd.date_range("2025-01-01", periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "value": range(hours)})


def test_write_is_idempotent_and_partitioned():
    store, c = _fake_store()
    assert store.write(_frame(), "smard", "x") == 48
    assert store.write(_frame(), "smard", "x") == 48
    assert sorted(c.blobs) == [
        "smard/x/date=2025-01-01/part.parquet",
        "smard/x/date=2025-01-02/part.parquet",
    ]
    out = store.read("smard", "x")
    assert len(out) == 48 and out["timestamp"].is_unique
    pd.read_parquet(io.BytesIO(c.blobs["smard/x/date=2025-01-01/part.parquet"]))


def test_read_since_filters_partitions():
    store, _ = _fake_store()
    store.write(_frame(72), "smard", "x")
    assert len(store.read("smard", "x", since=date(2025, 1, 2))) == 48


def test_partition_path_matches_local_layout(tmp_path):
    local = BronzeStore(tmp_path).partition_path("a", "b", date(2025, 1, 1))
    assert local.relative_to(tmp_path).as_posix() == AzureBlobBronzeStore.partition_path(
        "a", "b", date(2025, 1, 1)
    )


def test_make_store_selects_backend(tmp_path):
    assert isinstance(make_store(Settings(data_dir=tmp_path, storage_backend="local")), BronzeStore)
    with pytest.raises(RuntimeError):
        make_store(
            Settings(storage_backend="azure", adls_account_url="", azure_connection_string="")
        )
    with pytest.raises(ValueError):
        make_store(Settings(storage_backend="nope"))


# --- against the real Azure Storage API implementation (Azurite emulator) -----------------------

CONN = os.environ.get("GRIDPULSE_TEST_AZURITE_CONN")


@pytest.mark.skipif(not CONN, reason="GRIDPULSE_TEST_AZURITE_CONN not set (Azurite emulator)")
def test_roundtrip_against_azurite_emulator():
    pytest.importorskip("azure.storage.blob")
    name = f"t{pd.Timestamp.now().strftime('%H%M%S%f')}"
    store = AzureBlobBronzeStore(name, connection_string=CONN)
    assert store.write(_frame(), "smard", "x") == 48
    assert store.write(_frame(), "smard", "x") == 48  # overwrite, no duplicates
    out = store.read("smard", "x")
    assert len(out) == 48 and out["timestamp"].is_unique
    assert len(store.read("smard", "x", since=date(2025, 1, 2))) == 24
    assert store.read("smard", "other").empty
    store.container.delete_container()
