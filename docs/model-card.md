# Model card: day-ahead price (DE-LU)

**Task:** predict the hourly day-ahead price (EUR/MWh) for the German-Luxembourg bidding zone.
**Data:** SMARD hourly series + DWD weather via Bright Sky, 2024-10-19 to 2026-10-18 (17,520 hours),
gold tables built by dbt. **Split:** chronological, train / 60-day validation (early stopping) /
last 90 days test. The test window was not used for any modelling decision.

## Results (test: 90 days, 2,160 hours)

| Model | MAE (EUR/MWh) | RMSE | MAE vs naive-24h |
|---|---|---|---|
| naive: same hour yesterday | 36.08 [31.6, 40.7] | 53.88 | baseline |
| naive: same hour last week | 46.92 [40.6, 53.5] | 67.23 | -30.0% (95% interval -50.7% to -12.0%) |
| LightGBM, calendar + lags only | 41.45 [36.9, 46.4] | 56.78 | -14.9% (-29.7% to -2.7%): worse, interval excludes zero |
| LightGBM, + observed weather | **32.66** [29.5, 36.0] | **44.52** | **+9.5% (-0.9% to +18.1%)**: interval includes zero |

## Read this before quoting the numbers

- The weather model uses **observed** weather at the target hour as a stand-in for a weather
  forecast. In production the input would be a forecast (e.g. DWD MOSMIX) with forecast error, so
  32.66 is an **optimistic upper bound**, not a deployable accuracy.
- Without weather, the model is **worse** than the naive baseline on this test window.
- The test window has a much higher price level (mean 138.5 vs 93.7 in training). No fuel (gas)
  or CO2 prices are used, which is the main missing driver. Tree models cannot extrapolate levels,
  so the model predicts the change versus yesterday's same hour (chosen on validation data).
- Intervals are 95% day-block bootstrap intervals (4,000 resamples of the 90 test days; whole days
  are resampled because hourly errors within a day are correlated). The weather model beats the
  naive baseline in 96.4% of resamples, but its gain is **not statistically distinguishable from
  zero at 95%**. Only the worse results (calendar-only model, last-week baseline) are significant.
- Single test window of 90 days, so the result is indicative.
- Numbers were refreshed on 2026-10-20 after retraining on the updated warehouse (late SMARD
  revisions); an earlier run on the same split gave 33.12 and +8.2%. That spread is itself a
  reminder not to quote the third digit.
- Hourly aggregation of what is now a 15-minute day-ahead market (since Oct 2025).

## Next steps that would make this credible
1. Collect real MOSMIX forecasts daily from now on and evaluate on genuine forecasts (shadow mode).
2. Add gas/CO2 price features (public sources) and walk-forward cross-validation with intervals.
3. Retrain weekly in Airflow and monitor drift (phase 7).

Reproduce: `gridpulse load-warehouse && (cd dbt && dbt build --full-refresh) && gridpulse train && gridpulse bootstrap-ci`.
Tracking: MLflow (SQLite), model registered as `gridpulse-price-lgbm`.
