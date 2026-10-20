variable "subscription_id" {
  type        = string
  description = "Azure subscription ID."
}

variable "location" {
  type        = string
  default     = "swedencentral"
  description = <<-EOT
    Azure region. The Azure for Students subscription only allows belgiumcentral, swedencentral,
    denmarkeast, switzerlandnorth and italynorth (policy "Allowed resource deployment regions");
    germanywestcentral is rejected there. Pay-as-you-go subscriptions can use any region.
  EOT
}

variable "project" {
  type    = string
  default = "gridpulse"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "alert_email" {
  type        = string
  description = "Receives budget alerts."
}

variable "budget_amount_eur" {
  type        = number
  default     = 10
  description = "Monthly budget for the resource group; alerts fire at 50/90/100 percent."
}

variable "budget_start_date" {
  type        = string
  description = "First day of a month, RFC3339, e.g. 2026-11-01T00:00:00Z."
}

variable "admin_principal_id" {
  type        = string
  description = <<-EOT
    Object ID of the human (or group) that administers the Key Vault and writes to the data lake.
    Explicit on purpose: using "whoever runs Terraform" made the role assignments flip between
    your laptop and the CI identity on every plan. Find yours with:
    az ad signed-in-user show --query id -o tsv
  EOT
}

variable "enable_postgres" {
  type        = bool
  default     = false
  description = "Create the PostgreSQL Flexible Server. Can cost money: check the portal's free-offer notice first."
}

variable "postgres_admin_login" {
  type    = string
  default = "gridpulse_admin"
}

variable "postgres_admin_password" {
  type        = string
  sensitive   = true
  default     = null
  description = "Required when enable_postgres = true. Stored in Key Vault, never in Git."
}

variable "postgres_allowed_ip" {
  type        = string
  default     = null
  description = "Your public IPv4, allowed through the Postgres firewall (dev only)."
}
