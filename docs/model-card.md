# Model card: day-ahead price (DE-LU)

**Task:** predict the hourly day-ahead price (EUR/MWh) for the German-Luxembourg bidding zone.
**Data:** SMARD hourly series + DWD weather via Bright Sky, 2024-10-19 to 2026-10-18 (17,520 hours),
gold tables built by dbt. **Split:** chronological, train / 60-day validation (early stopping) /
last 90 days test. The test window was not used for any modelling decision.

## Primary result: walk-forward, 13 months (9,192 hours)

Each month is predicted by models trained only on earlier data (monthly retraining, 60-day
validation block for early stopping). 95% day-block bootstrap intervals, 383 days.

| Model | MAE (EUR/MWh) | vs naive-24h |
|---|---|---|
| naive: same hour yesterday | 30.3 [28.1, 32.3] | baseline |
| naive: same hour last week | 38.6 | -28% (-38% to -18%) |
| LightGBM, calendar + lags only | 28.8 | +4.9% (-0.2% to +9.4%): interval includes zero |
| LightGBM, + observed weather (reference) | 23.5 [22.3, 24.8] | +22% (+18% to +26%) |
| LightGBM, + day-before weather forecast (**headline**) | **23.6** | **+22% (+17% to +26%)** |
| LightGBM, + forecast weather + last month's gas and coal price | 22.6 | +25% (+21% to +29%) |

- 12 of 13 months are better than the baseline in the point estimate (8 with an interval
  excluding zero); December 2025 was slightly worse (not significant).
- The weather input of the headline model is the forecast issued the day before (Open-Meteo
  Previous Runs archive, nine-station mean, CC BY 4.0), not observed weather. Weather noise
  stress test on the observed-weather model: gain 20% at 25% noise, 17% at 50%, 4% at 100%; the
  real forecast is far better than that stress level.
- The 10/90% quantile interval covers 69% of hours instead of 80% as trained; rolling conformal
  calibration (60-day window, no look-ahead) lifts it to 79% at the cost of a wider interval.
- Economic value: no measurable difference in battery revenue versus the naive forecast
  (-460 EUR/MW/year, interval -2,588 to +1,707 for a 1 MW / 2 MWh battery). A free 4-week average
  by hour earns +3,735 EUR/MW/year more than yesterday despite a higher MAE (31.8). See
  [analysis.md](analysis.md).

## Earlier single-window result (last 90 days, 2,160 hours)

Kept for transparency; superseded by the walk-forward result above, which covers a longer period
and therefore gives tighter intervals.

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
2. Add gas/CO2 price features (public sources) and calibrate the quantile intervals (conformal).
3. Retrain weekly in Airflow and monitor drift (phase 7).

Reproduce: `gridpulse load-warehouse && (cd dbt && dbt build --full-refresh) && gridpulse walk-forward --first-test-month 2025-10-01 --n-months 13 && gridpulse analyze` (single window: `gridpulse train && gridpulse bootstrap-ci`).
Tracking: MLflow (SQLite), model registered as `gridpulse-price-lgbm`.
