"""Bronze-layer storage: raw-ish data as Parquet, partitioned by source/dataset/date.

Writes are idempotent: re-running a day replaces that day's partition, so backfills and
Airflow retries never create duplicates.
"""

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
