# Running in the cloud

Two scheduled GitHub Actions workflows run the real pipeline against Azure. Nothing needs a laptop
to be on, and nothing costs money beyond a few cents of storage (details at the end).

```
          GitHub Actions (OIDC, no stored secret)
 09:00 UTC daily                         Sundays 03:00 UTC
 ┌──────────────────────────┐            ┌─────────────────────────────┐
 │ pipeline-daily.yml       │            │ pipeline-retrain.yml        │
 │ ingest SMARD + DWD       │            │ ingest, load FULL history   │
 │ load last 30 days        │            │ dbt build                   │
 │ dbt build + tests        │            │ day-before weather forecasts│
 │ pull model + shadow log  │            │ train (forecast weather)    │
 │ forecast tomorrow        │            │ publish only if skill > 0   │
 │ score earlier forecasts  │            └──────────────┬──────────────┘
 │ push shadow log          │                           │
 └──────────────┬───────────┘                           │
                ▼                                       ▼
   Azure Data Lake Gen2 (stgridpulsedev…)
     bronze/  raw Parquet, one partition per day and series
     state/   model/{model.txt,model_meta.json}, shadow/forecast_log.parquet, shadow/eval_latest.json
```

The Postgres in each job is a throw-away service container. Everything worth keeping lives in the
lake: the raw data (`bronze`) and the small state (`state`: the published model and the shadow
forecast log). So a job can fail, be re-run, or two runs can be repeated without damaging anything
(ingestion is idempotent per day; the shadow log upserts per target hour; runs never overlap
because both workflows share one concurrency group).

## What the daily run does
1. Ingests the last three days of SMARD and DWD data into `bronze` (late revisions are common).
2. Loads the last 30 days into Postgres (bulk `COPY`) and runs `dbt build`, including the tests.
3. Pulls the published model and the shadow log from `state`.
4. Issues tomorrow's hourly forecast from the Open-Meteo forecast and the recent prices, and stores
   it (`ops.forecast_log`).
5. Scores every earlier forecast against the actual price (`shadow-eval`): the honest,
   forward-looking evaluation.
6. Writes the shadow log and `eval_latest.json` back to `state`, and prints the evaluation in the
   run summary.

Why 09:00 UTC: today's day-ahead prices (published the day before) are known, tomorrow's are not,
so "tomorrow" is a real forecast. A forecast is only counted when it was issued before the price
existed.

## What the weekly run does
Rebuilds the warehouse from the full lake, fetches the day-before weather forecasts for the whole
history, trains on them (the live input is a forecast too, so training and use match), and
publishes the model **only if** its test MAE beats the naive baseline (`--min-skill 0`). A worse
model never replaces the published one; the run fails and alerts instead.

## Verified runs (2026-10-21)
| Run | Result | Time |
|---|---|---|
| Weekly retrain, `workflow_dispatch` on `main` | all steps green; model published (skill gate passed) | about 8 min |
| Daily, `workflow_dispatch` on `main` | dbt 37 pass, 1 warning; shadow log restored (24 rows from the previous run), tomorrow's forecast logged, state pushed | about 4 min |

Before that, both flows were rehearsed from a laptop against the same storage account. What is
**not** yet shown: a scheduled (cron) trigger firing on its own, and any scored shadow hours (the
log starts on 2026-10-21; scoring needs the following day's prices).

## Failure handling
* Every step is a plain CLI command; any non-zero exit fails the run. GitHub emails the repository
  owner for failed scheduled runs. If the secret `ALERT_WEBHOOK` (a Slack/Teams/Discord URL) is
  set, the failure is also posted there.
* No model published yet: `state-pull` exits with code 3. Run the weekly workflow once by hand.
* Runs are safe to repeat (`workflow_dispatch`).

## Setup (already done for this repository)
* Terraform (`infra/`) creates the lake, the `state` container, Key Vault, Log Analytics, the budget
  alert, and gives the GitHub identity *Storage Blob Data Contributor* on the lake
  (`pipeline_principal_id`).
* GitHub repository variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
  `ADLS_ACCOUNT_URL`. No secret is stored; the workflows log in with OIDC.
* One-off: `gridpulse sync-bronze` uploads the local history to the lake (16,788 files).

## Turning it off
Disable the two workflows in the Actions tab, or delete the variable `AZURE_CLIENT_ID` (both jobs
are skipped without it). `terraform destroy` removes the Azure side.

## Cost
Azure for Students gives a prepaid credit and asks for no card; nothing is charged unless the
subscription is upgraded by hand. These jobs add no new billable Azure service: they use the
existing storage account (about 100 MB and some tens of thousands of requests per month) and
GitHub Actions minutes (free allowance). A budget alert on the resource group is configured.
Exact figures are on the subscription's Cost Management page; they are not asserted here.
