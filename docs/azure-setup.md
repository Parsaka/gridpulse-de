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
CI runs the storage tests against an Azurite service container. The Terraform and the OIDC deploy
workflow remain validated-only until you have a subscription; the steps below apply then.


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
