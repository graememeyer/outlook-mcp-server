terraform {
  required_version = ">= 1.5"

  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}

provider "azuread" {
  # Uses your existing Azure CLI login (az account show).
}

# Microsoft Graph, so we can reference its delegated permission (scope) IDs by name.
data "azuread_application_published_app_ids" "well_known" {}

data "azuread_service_principal" "msgraph" {
  client_id = data.azuread_application_published_app_ids.well_known.result["MicrosoftGraph"]
}

locals {
  # Delegated permissions required by the Outlook MCP server (see README / config.py).
  graph_delegated_scopes = [
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Mail.Send",
    "Calendars.Read",
    "Calendars.ReadWrite",
    "Contacts.Read",
  ]
}

resource "azuread_application" "outlook_mcp" {
  display_name = var.app_display_name

  # Personal Microsoft accounts + any org directory (matches the /common OAuth flow).
  sign_in_audience = "AzureADandPersonalMicrosoftAccount"

  # Required to be v2 for the personal-account audience.
  api {
    requested_access_token_version = 2
  }

  web {
    redirect_uris = [var.redirect_uri]
  }

  required_resource_access {
    resource_app_id = data.azuread_service_principal.msgraph.client_id

    dynamic "resource_access" {
      for_each = local.graph_delegated_scopes
      content {
        id   = data.azuread_service_principal.msgraph.oauth2_permission_scope_ids[resource_access.value]
        type = "Scope" # Delegated permission
      }
    }
  }
}

# Rotate the secret if the expiry passes.
resource "time_rotating" "secret" {
  rotation_days = var.secret_expiration_days
}

resource "azuread_application_password" "outlook_mcp" {
  application_id = azuread_application.outlook_mcp.id
  display_name   = "outlook-mcp-terraform"
  end_date       = timeadd(time_rotating.secret.id, "${var.secret_expiration_days * 24}h")

  rotate_when_changed = {
    rotation = time_rotating.secret.id
  }
}
