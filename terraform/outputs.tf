output "client_id" {
  description = "Application (client) ID -> MS_CLIENT_ID in your .env"
  value       = azuread_application.outlook_mcp.client_id
}

output "client_secret" {
  description = "Client secret value -> MS_CLIENT_SECRET in your .env"
  value       = azuread_application_password.outlook_mcp.value
  sensitive   = true
}

output "tenant_id" {
  description = "Tenant ID the app was created in."
  value       = data.azuread_service_principal.msgraph.application_tenant_id
}
