variable "app_display_name" {
  description = "Display name for the Azure AD app registration."
  type        = string
  default     = "Outlook MCP Server"
}

variable "public_client_redirect_uri" {
  description = "Loopback redirect URI for the azure-identity interactive browser flow. Microsoft allows any localhost port when http://localhost is registered."
  type        = string
  default     = "http://localhost"
}

variable "secret_expiration_days" {
  description = "Lifetime of the generated client secret, in days."
  type        = number
  default     = 180
}
