# Outlook MCP Python

A Python Microsoft Outlook integration exposed as an MCP server, built on
[FastMCP](https://github.com/PrefectHQ/fastmcp) and the Microsoft Graph API.

## Overview

This project provides an MCP server for Microsoft Outlook using the Microsoft
Graph API. It handles authentication (interactive browser sign-in with silent
token refresh) and mail operations, and is usable from Claude Code and the
Claude desktop/web apps.

## Features

- Microsoft Graph API integration
- Delegated (user) auth via the `azure-identity` interactive browser flow, with
  an encrypted, persistent token cache — sign in once, refresh silently
- Mail operations (list, read, search, send)
- Environment-based configuration and logging

## Project Structure

- `auth/` - Authentication (`graph_auth.py` credential + `tools.py` MCP tools)
- `mail/` - Mail operation modules
- `utils/` - Utility functions
- `terraform/` - Optional IaC to create the Azure AD app registration
- `main.py` - Entry point (`mcp.run()`)
- `server.py` - FastMCP server instance
- `config.py` - Configuration settings

## Prerequisites

- Python 3.10 or higher
- A Microsoft Azure AD app registration (see below)

## Installation

```bash
git clone [repository-url]
cd outlook-mcp-server
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Azure App Registration

The interactive browser flow is a **public-client (PKCE)** flow, so **no client
secret is required**. You need an app registration with a loopback redirect URI
and the Microsoft Graph delegated permissions listed below.

### Option A — Terraform (recommended)

The `terraform/` directory provisions the app registration, its delegated Graph
scopes, and the loopback redirect. It uses your existing `az login`.

```bash
cd terraform
terraform init
terraform apply
```

Then copy the `client_id` output into `MS_CLIENT_ID` (see Configuration). The
generated client secret output is optional and only needed for app-only auth,
not for this server.

### Option B — Azure Portal (manual)

1. Open [Azure Portal](https://portal.azure.com/) → **App registrations** → **New registration**.
2. Name it (e.g. "Outlook MCP Server").
3. Under **Supported account types**, choose *Accounts in any organizational directory and personal Microsoft accounts*.
4. Under **Redirect URI**, select **Public client/native (mobile & desktop)** and enter `http://localhost`.
5. Click **Register**, then copy the **Application (client) ID** into `MS_CLIENT_ID`.
6. Under **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**, add:
   - `offline_access`, `User.Read`, `Mail.Read`, `Mail.Send`, `Calendars.Read`, `Calendars.ReadWrite`, `Contacts.Read`
7. Under **Authentication**, ensure *Allow public client flows* is enabled.

## Configuration

Create a `.env` file (see `.env.example`):

```
MS_CLIENT_ID=your-ms-client-id
# MS_TENANT_ID=common   # optional; default supports personal + work/school
```

For Claude Code / desktop, register the server in your MCP config (see
`claude-config-sample.json`), passing `MS_CLIENT_ID` in its `env`.

## Usage

1. Run the `authenticate` tool — a browser window opens for Microsoft sign-in.
2. After signing in, the account record and tokens are cached (encrypted) under
   your user profile; subsequent sessions refresh silently.
3. Use the mail tools (`list_emails`, `search_emails`, `read_email`, `send_email`).

## Authentication Flow

- `authenticate` opens the system browser (interactive sign-in). Tokens are
  stored in the OS-protected MSAL cache; the signed-in account is recorded at
  `~/.outlook-mcp-auth-record.json`.
- Access tokens are refreshed silently using the cached refresh token. You are
  only prompted to sign in again after long inactivity (refresh token expiry) or
  if access is revoked.
- `check_auth_status` reports whether a valid session exists.

## Troubleshooting

- **Sign-in doesn't complete**: ensure the app registration has `http://localhost`
  registered as a **public client** redirect and public client flows are allowed.
- **API call failures**: check the detailed error message in the tool response.

## Dependencies

- fastmcp (>=3.4,<4)
- azure-identity
- aiohttp
- pydantic / pydantic-settings
- python-dotenv
