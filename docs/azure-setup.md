# Azure setup (one-time, done by you)

## No subscription? Free path (verified)
Nothing can be created in Azure without a subscription, and the free account needs a card for
identity verification, which only you can enter. Everything on the storage side still runs for
free against the official **Azurite** emulator, which implements the Azure Blob API:

```bash
docker compose --profile azure-emulator up -d azurite
export GRIDPULSE_STORAGE_BACKEND=azure GRIDPULSE_ADLS_FILESYSTEM=bronze
export GRIDPULSE_AZURE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
gridpulse sample-data --days 5 && gridpulse load-warehouse   # blob -> Postgres
```
The key above is Microsoft's published, public development key for the emulator (not a secret).
CI runs the storage tests against an Azurite service container. The steps below were run for real on
2026-10-20; see "What was applied" at the end for the result and the lessons.


Nothing here is automated on purpose: account creation and payment details must be entered by you.

1. **Account**: create a free Azure account (needs phone and card verification).
2. **Tools** (Windows): `winget install Microsoft.AzureCLI Hashicorp.Terraform`, then reopen the terminal.
3. **Login**: `az login`, then `az account show --query id -o tsv` gives your `subscription_id`.
4. **Check the free offers** in the portal before enabling Postgres (Create > Azure Database for
   PostgreSQL Flexible Server shows what is free for your account). Prices change; trust the portal.
5. **State storage** (once, ~cents/month):
   ```bash
   az group create -n rg-gridpulse-tfstate -l swedencentral   # students: only 5 regions are allowed
   az storage account create -n <unique-name> -g rg-gridpulse-tfstate -l swedencentral \
     --sku Standard_LRS --allow-blob-public-access false
   az storage container create --account-name <unique-name> -n tfstate --auth-mode login
   ```
   You may need the role "Storage Blob Data Contributor" on that account.
6. **Configure**: in `infra/`, copy `backend.hcl.example` to `backend.hcl` and
   `terraform.tfvars.example` to `terraform.tfvars`, then fill in your values (both are git-ignored).
7. **Plan, review, apply**:
   ```bash
   terraform init -backend-config=backend.hcl
   terraform plan -out tfplan
   terraform apply tfplan
   ```
8. **Point the pipeline at the lake**: set `GRIDPULSE_STORAGE_BACKEND=adls` and
   `GRIDPULSE_ADLS_ACCOUNT_URL=https://<storage_account_name>.blob.core.windows.net` (see
   `terraform output storage_account_name`). Your user needs "Storage Blob Data Contributor" on
   the lake account (add as a role assignment or in the portal).
9. **Tear down when not needed**: `terraform destroy` (keeps cost at zero).

## What was applied (2026-10-20, Azure for Students)
Subscription `Azure for Students` (USD 100 credit, no card), region **Sweden Central**.

| Resource | Name | Notes |
|---|---|---|
| Resource group | `rg-gridpulse-dev` | holds everything below |
| Storage account (ADLS Gen2) | `stgridpulsedevyhtd9` | LRS, TLS 1.2, no public blobs, container `bronze` |
| Key Vault | `kv-gridpulse-yhtd9` | RBAC mode, soft delete 7 days |
| Log Analytics | `log-gridpulse-dev` | 0.5 GB/day cap, nothing feeds it yet |
| Budget | `budget-gridpulse-dev` | monthly, alerts at 50/90/100 percent |
| State storage | `stgptfstate751698` (own group `rg-gridpulse-tfstate`) | blob versioning on, for rollback |

PostgreSQL in Azure is **not** created (`enable_postgres = false`). A re-plan reports "No changes".

Verified against the real account: `gridpulse smard|weather|daily` with `GRIDPULSE_STORAGE_BACKEND=azure`
wrote 103 Parquet blobs (about 0.5 MB, 22 datasets); reading them back matched the local copy (price
and solar identical; `load_total` differed by at most 12.7 MWh because SMARD revised it in between).
Authentication is your `az login` through `DefaultAzureCredential`; no key is stored anywhere.

### Lessons from doing it
- **Allowed regions:** the student subscription has the policy "Allowed resource deployment regions"
  (belgiumcentral, swedencentral, denmarkeast, switzerlandnorth, italynorth). `germanywestcentral` is rejected.
  Check with `az policy assignment list`.
- **Sign-in account:** a Gmail-based personal Microsoft account was refused ("account type not supported");
  another personal account worked. The subscription belongs to the account that completed the sign-up, which
  can differ from the notification email in the form.
- **Terraform and truncated output:** piping `terraform apply` into `Select-Object -First N` closed the pipe,
  left the process hanging and the state blob locked. Fix: write output to a file, `terraform force-unlock`
  only after confirming no terraform process runs, then `terraform import` anything created before the
  state was saved (here the Key Vault and the `bronze` filesystem).
- **Role assignments:** use an explicit `admin_principal_id`, not "whoever runs Terraform", or they flip
  between your laptop and CI on every plan.
- **Owner is not a data role:** reading and writing blobs needs `Storage Blob Data Contributor`
  (now in Terraform).
- **GitHub free plan** cannot require reviewers on environments in private repositories; the apply job is
  gated by the manual `workflow_dispatch` input only.

### Stop the spend
`terraform destroy` removes the dev resources; delete `rg-gridpulse-tfstate` last. With the student credit and
no card there is no way to be billed beyond the credit.

