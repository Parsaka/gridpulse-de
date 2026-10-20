output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "storage_account_name" {
  value = azurerm_storage_account.lake.name
}

output "bronze_filesystem" {
  value = azurerm_storage_data_lake_gen2_filesystem.bronze.name
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "postgres_fqdn" {
  value = try(azurerm_postgresql_flexible_server.main[0].fqdn, null)
}

output "lake_blob_url" {
  value       = azurerm_storage_account.lake.primary_blob_endpoint
  description = "Set GRIDPULSE_ADLS_ACCOUNT_URL to this value (with GRIDPULSE_STORAGE_BACKEND=azure)."
}

output "state_filesystem" {
  value = azurerm_storage_data_lake_gen2_filesystem.state.name
}
