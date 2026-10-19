# Deploy and rollback

Status: the workflow in `.github/workflows/infra.yml` is written but has **never run**, because it
needs your Azure subscription. CI (`ci.yml`) already runs `terraform fmt` and `validate` without credentials.

## One-time Azure and GitHub setup (you do this)
1. Finish `docs/azure-setup.md` (account, budget, state storage).
2. Create an app registration with a **federated credential** for this repo, so GitHub can log in
   without a secret:
   ```bash
   az ad app create --display-name gridpulse-github
   az ad app federated-credential create --id <APP_OBJECT_ID> --parameters '{
     "name": "github-main", "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:Parsaka/gridpulse-de:ref:refs/heads/main",
     "audiences": ["api://AzureADTokenExchange"]}'
   ```
   Add a second credential with subject `repo:Parsaka/gridpulse-de:pull_request` for plans on PRs
   and one with `repo:Parsaka/gridpulse-de:environment:azure` for the apply job.
3. Give the app's service principal `Contributor` on the resource group (or subscription for the
   first apply), plus `Storage Blob Data Contributor` on the state storage account.
4. In GitHub, Settings > Secrets and variables > Actions > **Variables** (not secrets, none of these
   is sensitive): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `ALERT_EMAIL`, `BUDGET_START_DATE`.
5. Settings > Environments > create `azure` and add yourself as a required reviewer.

## Flow
- A PR that touches `infra/` runs `terraform plan`; the plan is attached as an artifact.
- To change Azure: Actions > Infrastructure > Run workflow > `apply`. A reviewer must approve the
  `azure` environment before `terraform apply` runs the exact saved plan.

## Rollback
Infrastructure is code, so rollback is a revert:
1. `git revert <merge commit>` and merge the revert (or fix forward).
2. Run the workflow with `apply`; Terraform converges to the previous definition.
3. If a resource must go entirely: `terraform destroy -target=<resource>` locally with reviewer
   oversight. State is versioned by blob versioning on the state container (enable it in the
   portal), which allows restoring an earlier state file.

Data is not rolled back by Terraform: bronze Parquet is rebuilt by re-running the backfill DAG
(idempotent), and gold tables by `dbt build --full-refresh`.
