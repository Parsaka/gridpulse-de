"""MLflow tracking + model registry (local SQLite backend by default)."""

import mlflow
import mlflow.lightgbm

from gridpulse.ml.train import ModelResult

EXPERIMENT = "gridpulse-price"
MODEL_NAME = "gridpulse-price-lgbm"


def log_run(
    results: list[ModelResult], tracking_uri: str, data_info: dict, register: str | None = None
) -> str:
    """Log every model as a run; register the best of `register` feature set if given."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    run_ids = {}
    for r in results:
        with mlflow.start_run(run_name=r.name) as run:
            mlflow.log_params({"feature_set": r.feature_set, **data_info})
            if r.feature_set == "with_weather":
                # observed weather stands in for a forecast: optimistic upper bound
                mlflow.set_tag("weather_input", "observed_proxy_for_forecast")
            mlflow.log_metrics({k: v for k, v in r.metrics.items() if isinstance(v, int | float)})
            if r.model is not None:
                mlflow.log_params({"n_features": len(r.features)})
                mlflow.log_dict(
                    dict(sorted(r.importance.items(), key=lambda kv: -kv[1])), "importance.json"
                )
                mlflow.lightgbm.log_model(
                    r.model.booster_,
                    name="model",
                    registered_model_name=MODEL_NAME if r.feature_set == register else None,
                )
            run_ids[r.name] = run.info.run_id
    return ",".join(run_ids.values())
