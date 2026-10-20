from datetime import datetime
from typing import Annotated

import pandas as pd
import structlog
import typer

from gridpulse import pipeline
from gridpulse.config import get_settings, make_store
from gridpulse.ingestion import brightsky, entsoe, smard

app = typer.Typer(help="GridPulse DE ingestion CLI", no_args_is_help=True)
log = structlog.get_logger()

Start = Annotated[datetime, typer.Option(help="Window start (UTC), e.g. 2025-01-01")]
End = Annotated[datetime, typer.Option(help="Window end, exclusive (UTC)")]


@app.command("smard")
def ingest_smard(
    start: Start,
    end: End,
    dataset: Annotated[list[str] | None, typer.Option(help="Default: all")] = None,
):
    """Backfill / incremental load of SMARD generation, load and price series."""
    for name in dataset or smard.DATASETS:
        pipeline.load_smard_dataset(name, start, end)


@app.command("weather")
def ingest_weather(start: Start, end: End):
    """Hourly DWD weather (via Bright Sky) for the configured regions."""
    for loc in brightsky.LOCATIONS:
        pipeline.load_weather_location(loc, start, end)


@app.command("forecast-weather")
def forecast_weather(start: Start, end: End):
    """Archived day-before weather forecasts (Open-Meteo) for the same regions, national mean to
    gold.weather_forecast_national_hourly. Lets the model be evaluated on a real forecast."""
    import httpx
    from sqlalchemy import create_engine

    from gridpulse.ingestion import openmeteo

    s, e = pipeline.as_utc(start).date(), pipeline.as_utc(end).date()
    frames = []
    with httpx.Client(timeout=60) as client:
        for loc in brightsky.LOCATIONS:
            frames.append(openmeteo.fetch_previous_day_forecast(client, loc, s, e))
            log.info("forecast_weather.fetched", location=loc, rows=len(frames[-1]))
    national = openmeteo.national_mean(frames)
    engine = create_engine(get_settings().warehouse_url)
    national.to_sql(
        "weather_forecast_national_hourly", engine, schema="gold", if_exists="replace", index=False
    )
    log.info("forecast_weather.done", rows=len(national))


@app.command("entsoe-prices")
def ingest_entsoe_prices(start: Start, end: End):
    """Day-ahead prices for DE-LU from ENTSO-E (requires ENTSOE_API_KEY)."""
    settings = get_settings()
    df = entsoe.fetch_day_ahead_prices(
        settings.entsoe_api_key,
        pd.Timestamp(pipeline.as_utc(start)),
        pd.Timestamp(pipeline.as_utc(end)),
    )
    n = make_store(settings).write(df, "entsoe", "price_day_ahead")
    log.info("entsoe.ingested", rows=n)


@app.command("load-warehouse")
def load_warehouse(
    since_days: Annotated[
        int | None, typer.Option(help="Only partitions from the last N days (default: all)")
    ] = None,
):
    """Upsert bronze Parquet into PostgreSQL (schema bronze) for dbt."""
    pipeline.load_warehouse(since_days)


@app.command("bootstrap-ci")
def bootstrap_ci(n_boot: int = 4000):
    """95% day-block bootstrap intervals for the backtest MAE and the gain over naive 24h."""
    import json

    import pandas as pd
    from sqlalchemy import create_engine

    from gridpulse.ml.uncertainty import day_block_bootstrap

    engine = create_engine(get_settings().warehouse_url)
    bt = pd.read_sql("select * from gold.price_forecast_backtest", engine, parse_dates=["ts_utc"])
    preds = [c for c in bt.columns if c.startswith("pred_") and c != "pred_naive_24h"]
    res = day_block_bootstrap(bt, preds, "pred_naive_24h", n_boot=n_boot)
    typer.echo(json.dumps(res, indent=2))


@app.command("walk-forward")
def walk_forward_cmd(
    first_test_month: str = "2025-10-01",
    n_months: int = 12,
    out: str = "data/analysis",
    weather: str = "observed",
    fuel: bool = False,
):
    """Monthly-retrained walk-forward backtest (mean + 10/90% quantile models) over a year."""
    from pathlib import Path

    from sqlalchemy import create_engine

    from gridpulse.analysis.walkforward import NOISE_LEVELS, walk_forward
    from gridpulse.ml import data

    engine = create_engine(get_settings().warehouse_url)
    df = data.load_training_frame(engine, weather=weather)
    extra = None
    if fuel:  # last complete month's gas and coal price: known when forecasting
        f = pd.read_csv("data_static/fuel_prices_monthly.csv")
        f["month"] = pd.PeriodIndex(f["month"], freq="M") + 1  # value becomes available a month on
        f = f.set_index("month")
        month = df["ts_utc"].dt.tz_convert("Europe/Berlin").dt.tz_localize(None).dt.to_period("M")
        df["gas_lag1m"] = month.map(f["gas_europe_usd_mmbtu"]).to_numpy()
        df["coal_lag1m"] = month.map(f["coal_australia_usd_t"]).to_numpy()
        extra = ["gas_lag1m", "coal_lag1m"]
    wf, folds = walk_forward(
        df,
        first_test_month,
        n_months,
        noise_levels=() if weather == "forecast" else NOISE_LEVELS,
        extra_features=extra,
        progress=lambda m, n: log.info("walkforward.fold", month=str(m.date()), hours=n),
    )
    suffix = ("_forecast" if weather == "forecast" else "") + ("_fuel" if fuel else "")
    Path(out).mkdir(parents=True, exist_ok=True)
    wf.to_parquet(Path(out) / f"walkforward{suffix}.parquet", index=False)
    wf.to_sql(
        f"walk_forward_backtest{suffix}", engine, schema="gold", if_exists="replace", index=False
    )
    log.info("walkforward.done", hours=len(wf), folds=len(folds))


@app.command("analyze")
def analyze(
    data_dir: str = "data/analysis",
    docs_dir: str = "docs",
    n_boot: int = 2000,
    from_parquet: bool = True,
):
    """Run the full analysis: results.json, figures, interactive dashboard and docs/analysis.md."""
    import json
    import shutil
    from pathlib import Path

    import pandas as pd
    from sqlalchemy import create_engine

    from gridpulse.analysis import dashboard, figures, report
    from gridpulse.analysis.compute import compute
    from gridpulse.analysis.data import load_hourly

    engine = create_engine(get_settings().warehouse_url)
    df = load_hourly(engine)
    src = Path(data_dir) / "walkforward.parquet"
    wf = (
        pd.read_parquet(src)
        if from_parquet and src.exists()
        else pd.read_sql("select * from gold.walk_forward_backtest", engine, parse_dates=["ts_utc"])
    )
    wf["ts_utc"] = pd.to_datetime(wf["ts_utc"], utc=True)
    fc_path = Path(data_dir) / "walkforward_forecast.parquet"
    if (
        fc_path.exists()
    ):  # headline model = real day-before weather forecast; observed = upper bound
        fc = pd.read_parquet(fc_path)
        fc["ts_utc"] = pd.to_datetime(fc["ts_utc"], utc=True)
        if not (fc["ts_utc"].to_numpy() == wf["ts_utc"].to_numpy()).all():
            raise ValueError("forecast and observed walk-forward runs cover different hours")
        wf["lgbm_weather_obs"] = wf["lgbm_weather"]
        for col in ("lgbm_weather", "q10", "q90"):
            wf[col] = fc[col].to_numpy()
    fuel_wf = Path(data_dir) / "walkforward_forecast_fuel.parquet"
    if fuel_wf.exists():  # the variant that also sees last month's gas and coal prices
        wf["lgbm_weather_fuel"] = pd.read_parquet(fuel_wf)["lgbm_weather"].to_numpy()
    fuel_path = Path("data_static/fuel_prices_monthly.csv")
    fuel = pd.read_csv(fuel_path) if fuel_path.exists() else None
    res = compute(df, wf, n_boot=n_boot, fuel=fuel)
    out = Path(data_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    figures.make_figures(res, df, wf, out / "figures")
    dash = dashboard.build_dashboard(res, df, wf, out / "dashboard.html")
    docs = Path(docs_dir)
    (docs / "analysis" / "figures").mkdir(parents=True, exist_ok=True)
    for png in (out / "figures").glob("*.png"):
        shutil.copy(png, docs / "analysis" / "figures" / png.name)
    shutil.copy(dash, docs / "analysis" / "dashboard.html")
    shutil.copy(out / "results.json", docs / "analysis" / "results.json")
    report.write_report(res, docs / "analysis.md")
    report.write_business(res, docs / "for-business.md")
    bi_cols = [
        "ts_utc",
        "actual",
        "naive_24h",
        "naive_168h",
        "lgbm_calendar",
        "lgbm_weather",
        "q10",
        "q90",
    ]
    wf[bi_cols].to_sql(
        "walk_forward_backtest", engine, schema="gold", if_exists="replace", index=False
    )
    for name, table in report.bi_tables(res).items():  # feeds the Power BI report
        table.to_sql(name, engine, schema="gold", if_exists="replace", index=False)
    log.info("analyze.done", figures=len(list((out / "figures").glob("*.png"))))


@app.command("export-bi")
def export_bi(
    out: str = "data/bi",
    model: str = "powerbi/GridPulse.SemanticModel/definition/tables",
):
    """Write every table of the Power BI model to CSV (columns taken from the TMDL files), so the
    report can be refreshed without database credentials."""
    import re
    from pathlib import Path

    from sqlalchemy import create_engine

    engine = create_engine(get_settings().warehouse_url)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for tmdl in sorted(Path(model).glob("*.tmdl")):
        cols = re.findall(r"^	column (\w+)", tmdl.read_text(encoding="utf-8"), re.M)
        df = pd.read_sql(f"select {', '.join(cols)} from gold.{tmdl.stem}", engine)
        for c in df.columns:
            if isinstance(df[c].dtype, pd.DatetimeTZDtype):
                df[c] = df[c].dt.tz_convert("UTC").dt.tz_localize(None)
        df.to_csv(out_dir / f"{tmdl.stem}.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
        log.info("export_bi.table", table=tmdl.stem, rows=len(df))


@app.command("state-pull")
def state_pull():
    """Cloud job start: fetch the published model and restore the shadow forecast log."""
    from sqlalchemy import create_engine

    from gridpulse import state

    settings = get_settings()
    store = state.make_state_store(settings)
    found = state.pull_model(store, settings.model_dir)
    restored = state.pull_shadow(create_engine(settings.warehouse_url), store)
    log.info("state.pulled", model=found, shadow_rows=restored)
    if not found:
        raise typer.Exit(code=3)  # no model published yet: run the retrain workflow first


@app.command("state-push")
def state_push(
    model: bool = False,
    shadow: bool = True,
    eval_file: Annotated[str | None, typer.Option(help="Shadow evaluation JSON to publish")] = None,
    min_skill: Annotated[
        float, typer.Option(help="Refuse to publish a model whose test MAE skill is below this")
    ] = 0.0,
):
    """Cloud job end: persist the shadow log (and, after a retrain, the model)."""
    import json
    from pathlib import Path

    from sqlalchemy import create_engine

    from gridpulse import state
    from gridpulse.ml.artifacts import META_FILE

    settings = get_settings()
    store = state.make_state_store(settings)
    if model:
        meta = json.loads((settings.model_dir / META_FILE).read_text(encoding="utf-8"))
        skill = meta["test_metrics"].get("mae_skill_vs_naive_24h", 0.0)
        if skill < min_skill:  # a worse model must never replace the published one
            log.error("state.model_rejected", skill=skill, min_skill=min_skill)
            raise typer.Exit(code=4)
        state.push_model(store, settings.model_dir)
    if eval_file:
        state.push_json(store, state.SHADOW_EVAL, json.loads(Path(eval_file).read_text("utf-8")))
    if shadow:
        n = state.push_shadow(create_engine(settings.warehouse_url), store)
        log.info("state.shadow_pushed", rows=n)


@app.command("sync-bronze")
def sync_bronze(workers: int = 16):
    """Copy the local bronze Parquet to the configured cloud store (idempotent, parallel)."""
    from concurrent.futures import ThreadPoolExecutor

    settings = get_settings()
    if settings.storage_backend not in ("adls", "azure"):
        raise typer.BadParameter("set GRIDPULSE_STORAGE_BACKEND=adls first")
    store = make_store(settings)
    files = [p for p in settings.bronze_dir.rglob("part.parquet")]

    def upload(path):
        name = path.relative_to(settings.bronze_dir).as_posix()
        store.container.upload_blob(name, path.read_bytes(), overwrite=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(upload, files))
    log.info("sync.done", files=len(files))


@app.command("forecast-log")
def forecast_log():
    """Issue the next-day forecast (live weather forecast) and store it for shadow evaluation."""
    from sqlalchemy import create_engine

    from gridpulse.api.service import ForecastService
    from gridpulse.ml import shadow

    settings = get_settings()
    engine = create_engine(settings.warehouse_url)
    forecast = ForecastService(engine, settings.model_dir).forecast_next_day()
    n = shadow.log_forecast(engine, forecast)
    log.info("forecast.logged", rows=n, target_day=forecast["target_day_utc"])


@app.command("shadow-eval")
def shadow_eval(out: Annotated[str | None, typer.Option(help="Also write the JSON here")] = None):
    """Score logged forecasts against actual prices (honest, forward-looking evaluation)."""
    import json
    from pathlib import Path

    from sqlalchemy import create_engine

    from gridpulse.ml import shadow

    text = json.dumps(shadow.evaluate(create_engine(get_settings().warehouse_url)), indent=2)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    typer.echo(text)


@app.command("drift")
def drift(recent_days: int = 14):
    """PSI drift of the model's features: last N days vs the same season a year earlier.

    Exit code 99 means drift was detected (Airflow shows that as a skipped task, i.e. a warning).
    """
    import json

    from sqlalchemy import create_engine

    from gridpulse.ml import artifacts, monitor

    settings = get_settings()
    _, meta = artifacts.load_model(settings.model_dir)
    report = monitor.check_drift(
        create_engine(settings.warehouse_url), meta["features"], recent_days=recent_days
    )
    typer.echo(json.dumps(report, indent=2, default=str))
    if report["drifted"]:
        raise typer.Exit(code=99)


@app.command("sample-data")
def sample_data(start: str = "2026-01-01", days: int = 7):
    """Write deterministic SYNTHETIC bronze data (for CI/offline demos; not real data)."""
    from gridpulse.sample import write_sample_bronze

    write_sample_bronze(make_store(), start, days)
    log.info("sample.written", start=start, days=days)


@app.command("train")
def train(
    test_days: int = 90,
    register: Annotated[str, typer.Option(help="Feature set to register")] = "with_weather",
    no_mlflow: bool = False,
    weather: Annotated[
        str,
        typer.Option(help="Training weather: observed (DWD) or forecast (Open-Meteo day-before)"),
    ] = "observed",
    report_file: Annotated[str | None, typer.Option(help="Also write the JSON report here")] = None,
):
    """Train baselines + LightGBM on gold tables, log to MLflow, write backtest to gold."""
    import json
    from pathlib import Path

    from sqlalchemy import create_engine

    from gridpulse.ml import data, registry
    from gridpulse.ml import train as ml_train

    settings = get_settings()
    engine = create_engine(settings.warehouse_url)
    df = data.load_training_frame(engine, weather=weather)
    results, backtest = ml_train.train_and_evaluate(df, test_days=test_days)
    data.write_backtest(engine, backtest)
    info = {
        "rows": len(df),
        "first_ts": str(df["ts_utc"].min()),
        "last_ts": str(df["ts_utc"].max()),
        "test_days": test_days,
        "weather": weather,
    }
    from gridpulse.ml import artifacts

    chosen = next(r for r in results if r.feature_set == register and r.model is not None)
    artifacts.save_model(chosen, settings.model_dir, ml_train.ANCHOR, info)
    if not no_mlflow:
        registry.log_run(results, settings.mlflow_tracking_uri, info, register=register)
    summary = {r.name: {k: round(v, 4) for k, v in r.metrics.items()} for r in results}
    report = json.dumps({"data": info, "metrics": summary}, indent=2)
    if report_file:
        Path(report_file).write_text(report, encoding="utf-8")
    typer.echo(report)


@app.command("daily")
def daily(days_back: int = 3):
    """Incremental run: re-load the last N days (idempotent)."""
    start, end = pipeline.daily_window(days_back)
    ingest_smard(start, end, None)
    ingest_weather(start, end)


if __name__ == "__main__":
    app()
