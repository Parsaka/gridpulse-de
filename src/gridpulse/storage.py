"""Bronze-layer storage: raw-ish data as Parquet, partitioned by source/dataset/date.

Writes are idempotent: re-running a day replaces that day's partition, so backfills and
Airflow retries never create duplicates.
"""

import contextlib
import io
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd


def _partition_date(dirname: str) -> date:
    """'date=2026-01-31' -> date(2026, 1, 31)."""
    return date.fromisoformat(dirname.removeprefix("date="))


class BronzeStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def partition_path(self, source: str, dataset: str, day: date) -> Path:
        return self.root / source / dataset / f"date={day.isoformat()}" / "part.parquet"

    def write(self, df: pd.DataFrame, source: str, dataset: str, ts_col: str = "timestamp") -> int:
        """Split df by UTC calendar day on ts_col and overwrite each day's partition."""
        if df.empty:
            return 0
        df = df.copy()
        df["_ingested_at"] = datetime.now(UTC)
        days = df[ts_col].dt.tz_convert("UTC").dt.date
        written = 0
        for day, part in df.groupby(days):
            path = self.partition_path(source, dataset, day)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            part.to_parquet(tmp, index=False)
            tmp.replace(path)  # atomic swap
            written += len(part)
        return written

    def read(self, source: str, dataset: str, since: date | None = None) -> pd.DataFrame:
        """Read all partitions, or only those with date >= since."""
        base = self.root / source / dataset
        files = sorted(base.glob("date=*/part.parquet"))
        if since is not None:
            files = [f for f in files if _partition_date(f.parent.name) >= since]
        if not files:
            return pd.DataFrame()
        return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


class AzureBlobBronzeStore:
    """Same layout and semantics as BronzeStore, on Azure Blob Storage.

    Works against a real storage account (ADLS Gen2 accounts expose the Blob API too) and against
    the free Azurite emulator, so the Azure code path is testable without a subscription.
    Auth: DefaultAzureCredential for real accounts (az login locally, managed identity or OIDC in
    the cloud, no keys), or a connection string for the emulator. Needs: pip install '.[azure]'.
    """

    def __init__(
        self,
        container: str,
        account_url: str = "",
        connection_string: str = "",
        credential=None,
    ):
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        if connection_string:
            service = BlobServiceClient.from_connection_string(connection_string)
        else:
            if credential is None:
                from azure.identity import DefaultAzureCredential

                credential = DefaultAzureCredential()
            service = BlobServiceClient(account_url, credential=credential)
        self.container = service.get_container_client(container)
        if connection_string:  # emulator: create the container on first use
            with contextlib.suppress(ResourceExistsError):
                self.container.create_container()

    @staticmethod
    def partition_path(source: str, dataset: str, day: date) -> str:
        return f"{source}/{dataset}/date={day.isoformat()}/part.parquet"

    def write(self, df: pd.DataFrame, source: str, dataset: str, ts_col: str = "timestamp") -> int:
        if df.empty:
            return 0
        df = df.copy()
        df["_ingested_at"] = datetime.now(UTC)
        days = df[ts_col].dt.tz_convert("UTC").dt.date
        written = 0
        for day, part in df.groupby(days):
            buf = io.BytesIO()
            part.to_parquet(buf, index=False)
            name = self.partition_path(source, dataset, day)
            self.container.upload_blob(name, buf.getvalue(), overwrite=True)  # idempotent
            written += len(part)
        return written

    def read(self, source: str, dataset: str, since: date | None = None) -> pd.DataFrame:
        frames = []
        for blob in self.container.list_blobs(name_starts_with=f"{source}/{dataset}/"):
            if not blob.name.endswith("part.parquet"):
                continue
            if since is not None and _partition_date(blob.name.split("/")[-2]) < since:
                continue
            data = self.container.download_blob(blob.name).readall()
            frames.append(pd.read_parquet(io.BytesIO(data)))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


AdlsBronzeStore = AzureBlobBronzeStore  # backwards-compatible name
