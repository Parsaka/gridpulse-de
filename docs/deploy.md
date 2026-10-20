# Deploy and rollback

Status (verified 2026-10-20): `.github/workflows/infra.yml` has run for real against the Azure for Students
subscription using OIDC (no stored secret): a `terraform plan` on a pull request, and a manual
`workflow_dispatch` with `action=apply` from `main` (plan job, then apply job in the `azure` environment).
Both reported "No changes" because the infrastructure had already been applied from a laptop. CI (`ci.yml`)
also runs `terraform fmt` and `validate` without credentials.

Not exercised yet: an apply that actually changes something through CI, and approval gating (GitHub's free
plan cannot require reviewers on environments in private repositories).

## One-time Azure and GitHub setup (you do this)
1. Finish `docs/azure-setup.md` (account, budget, state storage).
2. Create an app registration with **federated credentials**, so GitHub can log in without a secret.
   The `subject` must match the claim GitHub actually sends. Newer GitHub accounts and repositories send
   the numeric ids too: `repo:<owner>@<owner-id>/<repo>@<repo-id>:pull_request`. The ids are shown in the
   failed `azure/login` log line `subject claim - ...` (a wrong subject gives `AADSTS700213`), or via
   `gh api repos/<owner>/<repo> --jq '.owner.id, .id'`. Create three credentials (all with issuer
   `https://token.actions.githubusercontent.com` and audience `api://AzureADTokenExchange`) for the subjects
   `...:ref:refs/heads/main`, `...:pull_request` and `...:environment:azure`:
   ```bash
   az ad app create --display-name gridpulse-github
   az ad sp create --id <APP_ID>
   az ad app federated-credential create --id <APP_ID> --parameters @credential.json
   ```
3. Give the app's service principal `Contributor` and `User Access Administrator` on the subscription
   (the latter because the Terraform creates role assignments), plus `Storage Blob Data Contributor` on
   the state storage account. This is broad, acceptable for a single-owner learning subscription; narrow it
   for anything shared.
4. In GitHub, Settings > Secrets and variables > Actions > **Variables** (not secrets, none of these
   is sensitive): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `ALERT_EMAIL`, `BUDGET_START_DATE`,
   `ADMIN_PRINCIPAL_ID` (your user object id: `az ad signed-in-user show --query id -o tsv`).
5. Settings > Environments > create `azure` (the federated credential for the apply job is bound to it).
   Add yourself as a required reviewer **if your plan allows it**: GitHub's free plan does not offer
   required reviewers on environments in private repositories (it works in public repositories). Without
   it, the manual `workflow_dispatch` run with `action=apply` is the only gate.

## Flow
- A PR that touches `infra/` runs `terraform plan`; the plan is attached as an artifact.
- To change Azure: Actions > Infrastructure > Run workflow > `apply`. With a required reviewer set, they must
  approve the `azure` environment before `terraform apply` runs the exact saved plan.

## Rollback
Infrastructure is code, so rollback is a revert:
1. `git revert <merge commit>` and merge the revert (or fix forward).
2. Run the workflow with `apply`; Terraform converges to the previous definition.
3. If a resource must go entirely: `terraform destroy -target=<resource>` locally with reviewer
   oversight. State is versioned by blob versioning on the state container (enable it in the
   portal), which allows restoring an earlier state file.

Data is not rolled back by Terraform: bronze Parquet is rebuilt by re-running the backfill DAG
(idempotent), and gold tables by `dbt build --full-refresh`.
