# ADR 0001: Azure with PostgreSQL as warehouse

**Status:** accepted

**Context:** German job market is Microsoft-heavy; target roles also list PostgreSQL and dbt.
Fabric/Synapse add capacity cost and complexity for a portfolio-sized dataset (millions of rows).

**Decision:** ADLS Gen2 for raw Parquet, Azure Database for PostgreSQL Flexible Server as the
warehouse (dbt-postgres), Container Apps for the API, Key Vault, Azure Monitor. Terraform `azurerm`.
Azure SQL Database may be added later as a second dbt target.

**Consequences:** Near-zero cost on free tier (verify in portal before creating). The same dbt
project runs on local Postgres in CI. Airflow starts local/VPS and may move to an Azure VM later.
