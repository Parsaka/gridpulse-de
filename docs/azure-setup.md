# Azure setup (one-time, done by you)

Nothing here is automated on purpose: account creation and payment details must be entered by you.

1. **Account**: create a free Azure account (needs phone and card verification).
2. **Tools** (Windows): `winget install Microsoft.AzureCLI Hashicorp.Terraform`, then reopen the terminal.
3. **Login**: `az login`, then `az account show --query id -o tsv` gives your `subscription_id`.
4. **Check the free offers** in the portal before enabling Postgres (Create > Azure Database for
   PostgreSQL Flexible Server shows what is free for your account). Prices change; trust the portal.
5. **State storage** (once, ~cents/month):
   ```bash
   az group create -n rg-gridpulse-tfstate -l germanywestcentral
   az storage account create -n <unique-name> -g rg-gridpulse-tfstate -l germanywestcentral \
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
   `GRIDPULSE_ADLS_ACCOUNT_URL=https://<storage_account_name>.dfs.core.windows.net` (see
   `terraform output storage_account_name`). Your user needs "Storage Blob Data Contributor" on
   the lake account (add as a role assignment or in the portal).
9. **Tear down when not needed**: `terraform destroy` (keeps cost at zero).
