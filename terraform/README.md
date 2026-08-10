# Terraform: Outlook MCP app registration

Provisions the Azure AD app registration the Outlook MCP server needs:

- Sign-in audience: personal Microsoft accounts + any org directory (`/common`)
- Web redirect URI: `http://localhost:3333/auth/callback`
- Delegated Microsoft Graph permissions: `offline_access`, `User.Read`,
  `Mail.Read`, `Mail.Send`, `Calendars.Read`, `Calendars.ReadWrite`, `Contacts.Read`
- A client secret (180-day lifetime, auto-rotates on apply after expiry)

## Usage

Authenticated via Azure CLI (`az login`) already, so just:

```bash
cd terraform
terraform init
terraform apply
```

Then pull the credentials into the app's `.env`:

```bash
terraform output client_id
terraform output -raw client_secret
```

Put those in `../.env` as `MS_CLIENT_ID` and `MS_CLIENT_SECRET`.

## Notes

- Delegated permissions here still require user consent, which happens the
  first time you run the `authenticate` flow in the browser. No admin consent
  is granted (or needed for a personal mailbox).
- The client secret lives in Terraform state — keep `terraform.tfstate*` out of
  git (already covered by the ignore rule below) and treat it as sensitive.
