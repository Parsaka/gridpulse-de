"""Bronze-layer storage: raw-ish data as Parquet, partitioned by source/dataset/date.

Writes are idempotent: re-running a day replaces that day's partition, so backfills and
Airflow retries never create duplicates.
"""

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd


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

    def read(self, source: str, dataset: str) -> pd.DataFrame:
        base = self.root / source / dataset
        files = sorted(base.glob("date=*/part.parquet"))
        if not files:
            return pd.DataFrame()
        return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


class AdlsBronzeStore:
    """Same layout and semantics as BronzeStore, on Azure Data Lake Storage Gen2.

    Auth uses DefaultAzureCredential (az login locally, managed identity / OIDC in the cloud),
    so no keys are stored anywhere. Needs: pip install '.[azure]'.
    """

    def __init__(self, account_url: str, filesystem: str, credential=None):
        from azure.storage.filedatalake import DataLakeServiceClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self.fs = DataLakeServiceClient(account_url, credential=credential).get_file_system_client(
            filesystem
        )

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
            file = self.fs.get_file_client(self.partition_path(source, dataset, day))
            file.upload_data(buf.getvalue(), overwrite=True)  # overwrite = idempotent
            written += len(part)
        return written

    def read(self, source: str, dataset: str) -> pd.DataFrame:
        frames = []
        for item in self.fs.get_paths(path=f"{source}/{dataset}"):
            if item.name.endswith("part.parquet"):
                data = self.fs.get_file_client(item.name).download_file().readall()
                frames.append(pd.read_parquet(io.BytesIO(data)))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
