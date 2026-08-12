"""
Correspondent aggregation.

Answering "who have I dealt with this year?" by listing messages does not
work: a year of mail is thousands of items, and the useful signal (the set of
distinct addresses) is a few hundred rows. This tool sweeps the folders
server-side and returns only the aggregate, with counts, date ranges and a
people-vs-services split.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)

from config import (
    EMAIL_MINIMAL_FIELDS,
    LIST_PAGE_SIZE,
    MAX_SCAN_MESSAGES,
)
from auth.graph_auth import get_graph_client, has_valid_session
from .folder_utils import resolve_folder_id
from .formatting import fmt_date, message_date
from .date_utils import (
    DateParseError,
    build_date_filter,
    combine_filters,
    date_field_for_folder,
)
from .paging import fetch_messages
from .addresses import looks_like_service, normalise, resolve
from server import mcp


@dataclass
class Correspondent:
    """Accumulated stats for one effective email address."""

    address: str
    display_names: Dict[str, int] = field(default_factory=dict)
    aliases: set = field(default_factory=set)
    received: int = 0
    sent_to: int = 0
    first_seen: Optional[object] = None
    last_seen: Optional[object] = None

    def observe(self, display_name: str, alias: Optional[str], when, inbound: bool):
        if display_name:
            self.display_names[display_name] = self.display_names.get(display_name, 0) + 1
        if alias:
            self.aliases.add(alias)
        if inbound:
            self.received += 1
        else:
            self.sent_to += 1
        if when:
            if self.first_seen is None or when < self.first_seen:
                self.first_seen = when
            if self.last_seen is None or when > self.last_seen:
                self.last_seen = when

    @property
    def best_name(self) -> str:
        if not self.display_names:
            return ""
        return max(self.display_names.items(), key=lambda kv: kv[1])[0]

    @property
    def total(self) -> int:
        return self.received + self.sent_to

    @property
    def two_way(self) -> bool:
        return self.received > 0 and self.sent_to > 0


def _record(
    registry: Dict[str, Correspondent],
    email_address,
    when,
    inbound: bool,
    own_addresses: set,
):
    """Fold one Graph emailAddress object into the registry."""
    if not email_address:
        return
    raw = normalise(getattr(email_address, "address", None))
    if not raw or "@" not in raw:
        return
    if raw in own_addresses:
        return

    effective, alias = resolve(raw)
    if effective in own_addresses:
        return

    entry = registry.get(effective)
    if entry is None:
        entry = Correspondent(address=effective)
        registry[effective] = entry
    entry.observe(getattr(email_address, "name", None) or "", alias, when, inbound)


async def _sweep_folder(
    client,
    folder: str,
    received_after: str,
    received_before: str,
    limit: int,
    registry: Dict[str, Correspondent],
    own_addresses: set,
) -> int:
    """Scan one folder, folding every participant into the registry."""
    folder_id = await resolve_folder_id(client, folder)
    date_field = date_field_for_folder(folder_id)
    date_clauses = build_date_filter(date_field, received_after, received_before)

    query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
        top=min(limit, LIST_PAGE_SIZE),
        orderby=[f"{date_field} desc"],
        select=EMAIL_MINIMAL_FIELDS.split(","),
        filter=combine_filters(date_clauses),
    )

    messages = await fetch_messages(
        client, folder_id, query_params, limit=limit, progress_every=1000
    )

    # In sent-like folders the counterparties are the recipients; elsewhere
    # they're the sender.
    outbound = date_field == "sentDateTime"

    for msg in messages:
        when = message_date(msg)
        if outbound:
            for recipient in (msg.to_recipients or []):
                _record(registry, recipient.email_address, when, False, own_addresses)
            for recipient in (msg.cc_recipients or []):
                _record(registry, recipient.email_address, when, False, own_addresses)
        else:
            if msg.from_:
                _record(registry, msg.from_.email_address, when, True, own_addresses)

    return len(messages)


def _format_row(c: Correspondent, reason: str = "") -> str:
    name = c.best_name
    label = f"{c.address}"
    if name and name.lower() != c.address:
        label += f"  \u2014 {name}"

    parts = [f"in {c.received}", f"out {c.sent_to}"]
    span = ""
    if c.first_seen and c.last_seen:
        span = f"{fmt_date(c.first_seen)[:10]} \u2192 {fmt_date(c.last_seen)[:10]}"

    flags = []
    if c.two_way:
        flags.append("two-way")
    if c.aliases:
        flags.append(f"via alias {sorted(c.aliases)[0]}")
    if reason:
        flags.append(reason)

    return (
        f"  {label}\n"
        f"      {' / '.join(parts)}   {span}"
        + (f"   [{'; '.join(flags)}]" if flags else "")
        + "\n"
    )


@mcp.tool(name="summarise_correspondents", title="Summarise correspondents")
async def handle_summarise_correspondents(
    folders: str = "inbox,sentitems",
    received_after: str = "",
    received_before: str = "",
    max_messages: int = 5000,
    own_addresses: str = "",
    min_messages: int = 1,
) -> str:
    """
    Aggregate every address you have exchanged mail with, split into likely
    people and likely automated services

    Sweeps the given folders over a date range and returns one row per unique
    address with message counts, first/last contact and a people-vs-services
    classification. Intended for tasks like auditing a mailbox before migrating
    to another provider, where listing individual messages would be unusable.

    The people-vs-services split is heuristic. The reliable signal is the
    "two-way" flag: addresses you have both received from and sent to. Treat the
    rest as a starting point to review, not a verdict.

    Forwarding-alias addresses (e.g. passmail.com) are unmasked back to the
    underlying service so counts aggregate against the real sender.

    Args:
        folders: Comma-separated folders to sweep (default: "inbox,sentitems").
            Also accepts "archive", "junk", "deleted", or a display name.
        received_after: Start of the window. Accepts YYYY-MM-DD, an ISO-8601
            timestamp, or relative shorthand like "1y" (default: no lower bound)
        received_before: End of the window, same formats (default: now)
        max_messages: Cap on messages scanned per folder (default: 5000,
            maximum: 25000)
        own_addresses: Comma-separated addresses belonging to you, excluded from
            the results (default: none)
        min_messages: Only report addresses with at least this many messages
            (default: 1)

    Returns:
        A grouped summary of correspondents with counts and date ranges
    """
    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    max_messages = max(1, min(max_messages, MAX_SCAN_MESSAGES))
    folder_list = [f.strip() for f in (folders or "inbox").split(",") if f.strip()]
    own = {normalise(a) for a in (own_addresses or "").split(",") if a.strip()}

    registry: Dict[str, Correspondent] = {}
    scanned: Dict[str, int] = {}

    try:
        client = get_graph_client()
        for folder in folder_list:
            try:
                scanned[folder] = await _sweep_folder(
                    client,
                    folder,
                    received_after,
                    received_before,
                    max_messages,
                    registry,
                    own,
                )
            except DateParseError as e:
                return f"Invalid date range: {e}"
            except Exception as e:  # one bad folder shouldn't sink the sweep
                scanned[folder] = 0
                registry.setdefault(
                    "__errors__", Correspondent(address="__errors__")
                ).display_names[f"{folder}: {e}"] = 1
    except Exception as e:
        return f"Error summarising correspondents: {str(e)}"

    errors = registry.pop("__errors__", None)

    entries = [c for c in registry.values() if c.total >= min_messages]
    if not entries:
        return "No correspondents found in the requested window."

    people: List[tuple] = []
    services: List[tuple] = []
    for c in entries:
        is_service, reason = looks_like_service(c.address, c.best_name)
        # Reciprocity outranks the heuristic: if you wrote to them and they
        # wrote back, treat it as a real correspondent regardless of shape.
        if c.two_way and c.sent_to > 0:
            people.append((c, "" if not is_service else f"looks automated: {reason}"))
        elif is_service:
            services.append((c, reason))
        else:
            people.append((c, reason))

    people.sort(key=lambda t: (-t[0].total, t[0].address))
    services.sort(key=lambda t: (-t[0].total, t[0].address))

    total_scanned = sum(scanned.values())
    window = f"{received_after or 'beginning'} \u2192 {received_before or 'now'}"
    header = (
        f"CORRESPONDENTS \u2014 {', '.join(folder_list)} | {window}\n"
        f"Scanned {total_scanned} messages ("
        + ", ".join(f"{k} {v}" for k, v in scanned.items())
        + f"); {len(entries)} unique addresses\n"
    )
    if any(v >= max_messages for v in scanned.values()):
        header += (
            f"WARNING: at least one folder hit the {max_messages}-message cap; "
            f"raise max_messages for full coverage.\n"
        )
    if errors:
        header += "Folder errors: " + "; ".join(errors.display_names) + "\n"

    out = [header]
    out.append(f"\nLIKELY PEOPLE ({len(people)})\n")
    out.extend(_format_row(c, r) for c, r in people)
    out.append(f"\nLIKELY SERVICES / AUTOMATED ({len(services)})\n")
    out.extend(_format_row(c, r) for c, r in services)

    return "".join(out)
