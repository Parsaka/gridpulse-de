"""Portable model artifact (LightGBM text model + JSON metadata) so the API needs no MLflow."""

import json
from datetime import UTC, datetime
from pathlib import Path

MODEL_FILE = "model.txt"
META_FILE = "model_meta.json"


def save_model(result, model_dir: Path, anchor: str, data_info: dict) -> Path:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    result.model.booster_.save_model(str(model_dir / MODEL_FILE))
    meta = {
        "name": result.name,
        "feature_set": result.feature_set,
        "features": result.features,
        "anchor": anchor,
        "trained_at": datetime.now(UTC).isoformat(),
        "test_metrics": {k: v for k, v in result.metrics.items() if isinstance(v, int | float)},
        "weather_input_at_training": "observed",
        "data": data_info,
    }
    (model_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return model_dir


def load_model(model_dir: Path):
    import lightgbm as lgb

    model_dir = Path(model_dir)
    meta = json.loads((model_dir / META_FILE).read_text(encoding="utf-8"))
    return lgb.Booster(model_file=str(model_dir / MODEL_FILE)), meta
