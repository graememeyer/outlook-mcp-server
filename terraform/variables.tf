variable "app_display_name" {
  description = "Display name for the Azure AD app registration."
  type        = string
  default     = "Outlook MCP Server"
}

variable "redirect_uri" {
  description = "OAuth redirect URI. Must match MS_AUTH_SERVER_URL/auth/callback used by the auth server."
  type        = string
  default     = "http://localhost:3333/auth/callback"
}

variable "secret_expiration_days" {
  description = "Lifetime of the generated client secret, in days."
  type        = number
  default     = 180
}
