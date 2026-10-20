"""Small persistent state that must survive between cloud runs: the trained model and the shadow
forecast log. The warehouse in the cloud job is throw-away (a Postgres service container), so
anything worth keeping is stored here: a local folder, or an Azure Blob container (Entra ID auth,
no keys) when GRIDPULSE_STORAGE_BACKEND=adls.
"""

import contextlib
import io
import json
from pathlib import Path

import pandas as pd
import structlog

from gridpulse.config import Settings, get_settings
from gridpulse.ml.artifacts import META_FILE, MODEL_FILE

log = structlog.get_logger()

MODEL_PREFIX = "model"
SHADOW_LOG = "shadow/forecast_log.parquet"
SHADOW_EVAL = "shadow/eval_latest.json"


class StateStore:
    """put/get of named blobs; names look like 'model/model.txt'."""

    def __init__(self, root: Path | None = None, container=None):
        self.root, self.container = root, container

    def put(self, name: str, data: bytes) -> None:
        if self.container is not None:
            self.container.upload_blob(name, data, overwrite=True)
        else:
            path = Path(self.root) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def get(self, name: str) -> bytes | None:
        if self.container is not None:
            from azure.core.exceptions import ResourceNotFoundError

            try:
                return self.container.download_blob(name).readall()
            except ResourceNotFoundError:
                return None
        path = Path(self.root) / name
        return path.read_bytes() if path.exists() else None


def make_state_store(settings: Settings | None = None) -> StateStore:
    s = settings or get_settings()
    if s.storage_backend in ("adls", "azure"):
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        if s.azure_connection_string:  # emulator
            service = BlobServiceClient.from_connection_string(s.azure_connection_string)
        else:
            from azure.identity import DefaultAzureCredential

            service = BlobServiceClient(s.adls_account_url, credential=DefaultAzureCredential())
        container = service.get_container_client(s.state_container)
        if s.azure_connection_string:
            with contextlib.suppress(ResourceExistsError):
                container.create_container()
        return StateStore(container=container)
    return StateStore(root=s.data_dir / "state")


# ---- model -----------------------------------------------------------------------------------
def push_model(store: StateStore, model_dir: Path) -> None:
    for fname in (MODEL_FILE, META_FILE):
        store.put(f"{MODEL_PREFIX}/{fname}", (Path(model_dir) / fname).read_bytes())
    log.info("state.model_pushed")


def pull_model(store: StateStore, model_dir: Path) -> bool:
    """Download the model; False if none has been published yet."""
    blobs = {f: store.get(f"{MODEL_PREFIX}/{f}") for f in (MODEL_FILE, META_FILE)}
    if any(b is None for b in blobs.values()):
        return False
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    for fname, data in blobs.items():
        (Path(model_dir) / fname).write_bytes(data)
    log.info("state.model_pulled")
    return True


# ---- shadow log --------------------------------------------------------------------------------
def pull_shadow(engine, store: StateStore) -> int:
    """Restore the persisted forecast log into the (fresh) warehouse."""
    from sqlalchemy import text

    from gridpulse.ml import shadow

    shadow.init(engine)
    data = store.get(SHADOW_LOG)
    if data is None:
        return 0
    df = pd.read_parquet(io.BytesIO(data))
    rows = df.to_dict("records")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.forecast_log VALUES "
                "(:issued_at, :ts_utc, :predicted_eur_mwh, :model_name, :model_trained_at) "
                "ON CONFLICT (ts_utc, model_name) DO NOTHING"
            ),
            rows,
        )
    return len(rows)


def push_shadow(engine, store: StateStore) -> int:
    from gridpulse.ml import shadow

    shadow.init(engine)
    df = pd.read_sql("select * from ops.forecast_log order by ts_utc", engine)
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    store.put(SHADOW_LOG, buf.getvalue())
    return len(df)


def push_json(store: StateStore, name: str, obj: dict) -> None:
    store.put(name, json.dumps(obj, indent=2, default=str).encode("utf-8"))
