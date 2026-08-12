"""
Address normalisation and correspondent classification.

Two jobs:

1. Unmask forwarding-alias addresses (passmail.com and friends) back to the
   real service behind them, so a mailbox full of aliases still reports which
   companies actually hold your address.
2. Guess whether an address belongs to a human or to an automated sender.

The classification is a heuristic and is reported as such. The one genuinely
strong signal is reciprocity: an address you have both received from *and*
sent to is almost always a real correspondent.
"""

import re
from typing import Optional, Tuple

# Alias providers that encode the original sender in the local part, e.g.
# "no-reply_at_royalmail_com_ajxgxgres@passmail.com".
ALIAS_DOMAINS = {"passmail.com", "passmail.net", "passinbox.com"}

# Multi-label public suffixes that must not be mistaken for a random token.
_COMPOUND_TLDS = {
    ("co", "uk"), ("org", "uk"), ("ac", "uk"), ("gov", "uk"), ("me", "uk"),
    ("ltd", "uk"), ("plc", "uk"), ("net", "uk"), ("sch", "uk"),
    ("com", "au"), ("net", "au"), ("org", "au"), ("co", "nz"), ("co", "za"),
    ("co", "jp"), ("or", "jp"), ("ne", "jp"), ("com", "br"), ("com", "cn"),
    ("co", "in"), ("com", "mx"), ("com", "sg"), ("co", "kr"),
}

_ALIAS_SUFFIX_RE = re.compile(r"^[a-z0-9]{4,16}$")

# Local parts that mean "a machine sent this".
_ROLE_LOCALPARTS = {
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "do_not_reply", "notification", "notifications", "notify", "alerts",
    "alert", "mailer", "mailer-daemon", "bounce", "bounces", "postmaster",
    "info", "hello", "hi", "support", "help", "helpdesk", "helpline",
    "admin", "administrator", "webmaster", "news", "newsletter", "updates",
    "update", "marketing", "offers", "deals", "promotions", "billing",
    "invoice", "invoices", "invoicing", "accounts", "accounting", "payments",
    "service", "services", "customerservice", "customercare", "care",
    "enquiries", "enquiry", "inquiries", "contact", "sales", "orders",
    "order", "shipping", "delivery", "auto-confirm", "autoconfirm",
    "confirm", "confirmation", "security", "verify", "verification",
    "feedback", "survey", "team", "reply", "replies", "messages", "mail",
    "email", "system", "robot", "bot", "daemon", "automated", "auto",
    "subscriptions", "unsubscribe", "members", "membership", "rewards",
    "points", "statements", "receipts", "no-replies", "candidatecare",
    "factor", "pensions", "autoenrolment",
}

# Substrings that flag a role account even inside a longer local part.
_ROLE_SUBSTRINGS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "notification", "mailer", "postmaster", "unsubscribe", "bounce",
    "automated", "auto-confirm", "shipment-tracking", "account-security",
)

# Sending infrastructure and bulk-mail subdomains.
_BULK_DOMAIN_HINTS = (
    "sendgrid.net", "mailchimp.com", "mcsv.net", "mcdlv.net", "rsgsv.net",
    "sparkpostmail.com", "amazonses.com", "mandrillapp.com", "sendinblue.com",
    "hubspotemail.net", "salesforce.com", "exacttarget.com", "mktomail.com",
    "cmail19.com", "createsend.com", "klaviyomail.com", "braze.com",
    "customeriomail.com", "postmarkapp.com", "mailgun.org", "zendesk.com",
    "freshdesk.com", "intercom-mail.com", "notifications.github.com",
)

_BULK_SUBDOMAIN_PREFIXES = (
    "mail.", "email.", "e.", "em.", "eml.", "news.", "newsletter.",
    "updates.", "update.", "info.", "notify.", "notifications.",
    "mailer.", "send.", "smtp.", "bounce.", "reply.", "alerts.",
    "marketing.", "campaign.", "service.", "account.", "accountprotection.",
    "message.", "messages.", "mailings.", "connect.", "engage.",
)

# A display name shaped like a person's name: two or three capitalised words,
# no corporate furniture.
_PERSON_NAME_RE = re.compile(
    r"^[A-Z][a-z'’\-]{1,20}(?:\s+[A-Z][a-z'’\-]{1,20}){1,2}$"
)

_ORG_NAME_WORDS = {
    "ltd", "limited", "llc", "inc", "plc", "gmbh", "team", "support",
    "group", "co", "company", "services", "notifications", "alerts",
    "news", "newsletter", "account", "accounts", "billing", "no-reply",
    "noreply", "info", "help", "helpline", "care", "sales", "rewards",
}


def normalise(address: Optional[str]) -> str:
    """Lowercase and strip an address; return '' for anything falsy."""
    return (address or "").strip().lower()


def split_address(address: str) -> Tuple[str, str]:
    """Split into (local_part, domain); domain is '' if there's no '@'."""
    addr = normalise(address)
    if "@" not in addr:
        return addr, ""
    local, _, domain = addr.rpartition("@")
    return local, domain


def unmask_alias(address: str) -> Optional[str]:
    """Recover the original sender behind a forwarding alias.

    ``no-reply_at_royalmail_com_ajxgxgres@passmail.com`` becomes
    ``no-reply@royalmail.com``. Returns ``None`` when the address isn't a
    recognised alias or doesn't match the expected shape.
    """
    local, domain = split_address(address)
    if domain not in ALIAS_DOMAINS or "_at_" not in local:
        return None

    original_local, _, remainder = local.partition("_at_")
    parts = [p for p in remainder.split("_") if p]
    if len(parts) < 3:
        # Needs at least domain + tld + random suffix to be unambiguous.
        return None

    # The trailing token is the alias's random discriminator, unless dropping
    # it would break a known compound TLD such as .co.uk.
    if tuple(parts[-2:]) in _COMPOUND_TLDS:
        domain_parts = parts
    elif _ALIAS_SUFFIX_RE.match(parts[-1]):
        domain_parts = parts[:-1]
    else:
        domain_parts = parts

    if len(domain_parts) < 2:
        return None

    # Alias encoding flattens dots in the local part to underscores.
    return f"{original_local.replace('_', '.')}@{'.'.join(domain_parts)}"


def resolve(address: str) -> Tuple[str, Optional[str]]:
    """Return (effective_address, alias_used_or_None).

    The effective address is the unmasked original where one can be recovered,
    so counts aggregate against the real service rather than the alias.
    """
    addr = normalise(address)
    original = unmask_alias(addr)
    if original:
        return original, addr
    return addr, None


def looks_like_service(address: str, display_name: str = "") -> Tuple[bool, str]:
    """Heuristically decide whether an address is an automated sender.

    Returns ``(is_service, reason)``. Reasons are surfaced in output so the
    call can be second-guessed rather than trusted blindly.
    """
    local, domain = split_address(address)
    name = (display_name or "").strip()

    if local in _ROLE_LOCALPARTS:
        return True, f"role address ({local}@)"

    for hint in _ROLE_SUBSTRINGS:
        if hint in local:
            return True, f"role keyword '{hint}'"

    for hint in _BULK_DOMAIN_HINTS:
        if domain == hint or domain.endswith("." + hint):
            return True, f"bulk sender ({hint})"

    for prefix in _BULK_SUBDOMAIN_PREFIXES:
        if domain.startswith(prefix):
            return True, f"bulk subdomain ({domain.split('.')[0]}.)"

    # Long random-looking local parts are almost always machine-generated.
    if len(local) > 24 and not any(sep in local for sep in "._-"):
        return True, "opaque local part"

    if _PERSON_NAME_RE.match(name):
        words = {w.lower().strip(".,") for w in name.split()}
        if not words & _ORG_NAME_WORDS:
            return False, "personal display name"

    # firstname.lastname@ / firstname_lastname@ shaped local parts.
    if re.fullmatch(r"[a-z]{2,}[._][a-z]{2,}", local):
        return False, "firstname.lastname pattern"

    return True, "no personal signal"


__all__ = [
    "ALIAS_DOMAINS",
    "looks_like_service",
    "normalise",
    "resolve",
    "split_address",
    "unmask_alias",
]
