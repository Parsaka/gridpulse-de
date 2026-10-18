# ADR 0002: Terraform guardrails for cost and security

**Status:** accepted

**Decisions**
- Infrastructure is code (`infra/`, azurerm ~> 4). Nothing is created by hand except the
  Terraform state storage account.
- PostgreSQL is behind `enable_postgres = false` so a plain `apply` creates only free or
  near-free resources (storage, Key Vault, Log Analytics with a daily cap, budget alerts).
- A monthly budget with alerts at 50/90/100 percent is part of the same state.
- No keys in code: Python uses `DefaultAzureCredential`; secrets live in Key Vault (RBAC mode);
  CI will authenticate to Azure with OIDC (phase 5).
- Dev Postgres uses public access plus a single-IP firewall rule. Acceptable for open data only;
  a private-networking variant is out of scope for the portfolio.

**Consequences:** `terraform validate` and `fmt` run in CI without credentials. `apply` is manual
until phase 5 adds an approval-gated deploy.
