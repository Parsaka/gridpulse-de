variable "subscription_id" {
  type        = string
  description = "Azure subscription ID."
}

variable "location" {
  type        = string
  default     = "germanywestcentral"
  description = "Azure region (Frankfurt)."
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
