"""
Offline tests for the pure helpers: date parsing, filter construction, alias
unmasking and correspondent classification.

These deliberately avoid importing anything that touches msgraph/fastmcp, so
they run without credentials or network access.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mail.date_utils import (  # noqa: E402
    DateParseError,
    build_date_filter,
    combine_filters,
    date_field_for_folder,
    parse_datetime,
    to_graph_literal,
)
from mail.addresses import (  # noqa: E402
    looks_like_service,
    resolve,
    split_address,
    unmask_alias,
)


# ---------------------------------------------------------------- date_utils

def test_parse_bare_date_is_midnight_utc():
    dt = parse_datetime("2026-01-01")
    assert dt == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_parse_bare_date_end_of_day():
    dt = parse_datetime("2026-01-01", end_of_day=True)
    assert (dt.hour, dt.minute, dt.second) == (23, 59, 59)


def test_end_of_day_does_not_touch_explicit_timestamps():
    dt = parse_datetime("2026-01-01T09:30:00Z", end_of_day=True)
    assert (dt.hour, dt.minute) == (9, 30)


def test_parse_iso_with_offset_normalises_to_utc():
    dt = parse_datetime("2026-03-01T12:00:00+02:00")
    assert dt == datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("shorthand,approx_days", [("7d", 7), ("2w", 14), ("6m", 180), ("1y", 365)])
def test_relative_shorthand(shorthand, approx_days):
    delta = datetime.now(timezone.utc) - parse_datetime(shorthand)
    assert abs(delta.days - approx_days) <= 1


def test_bad_date_raises():
    with pytest.raises(DateParseError):
        parse_datetime("last Tuesday-ish")


def test_graph_literal_format():
    assert to_graph_literal(parse_datetime("2026-01-01")) == "2026-01-01T00:00:00Z"


def test_date_field_depends_on_folder():
    assert date_field_for_folder("sentitems") == "sentDateTime"
    assert date_field_for_folder("drafts") == "sentDateTime"
    assert date_field_for_folder("inbox") == "receivedDateTime"
    assert date_field_for_folder("archive") == "receivedDateTime"


def test_build_date_filter_both_bounds():
    clauses = build_date_filter("receivedDateTime", "2026-01-01", "2026-08-12")
    assert clauses == [
        "receivedDateTime ge 2026-01-01T00:00:00Z",
        "receivedDateTime le 2026-08-12T23:59:59Z",
    ]


def test_build_date_filter_no_bounds_is_empty():
    assert build_date_filter("receivedDateTime", "", "") == []


def test_combine_filters_flattens_and_ands():
    combined = combine_filters(
        ["receivedDateTime ge 2026-01-01T00:00:00Z"], "isRead eq false", None, []
    )
    assert combined == (
        "receivedDateTime ge 2026-01-01T00:00:00Z and isRead eq false"
    )


def test_combine_filters_returns_none_when_empty():
    assert combine_filters(None, [], "") is None


# ----------------------------------------------------------------- addresses

@pytest.mark.parametrize(
    "alias,expected",
    [
        ("no-reply_at_royalmail_com_ajxgxgres@passmail.com", "no-reply@royalmail.com"),
        ("enquiries_at_patonandco_com_bztwci@passmail.com", "enquiries@patonandco.com"),
        (
            "johnathan_fraser_at_patonandco_com_nplhxqqsxy@passmail.com",
            "johnathan.fraser@patonandco.com",
        ),
        (
            "shipment-tracking_at_amazon_co_uk_ogfhtzf@passmail.com",
            "shipment-tracking@amazon.co.uk",
        ),
        ("hello_at_readwise_io_auxxx@passmail.com", "hello@readwise.io"),
        (
            "therestispolitics_at_goalhanger_com_nhdfrzkej@passmail.com",
            "therestispolitics@goalhanger.com",
        ),
    ],
)
def test_unmask_real_aliases(alias, expected):
    assert unmask_alias(alias) == expected


def test_compound_tld_survives_suffix_stripping():
    # amazon.co.uk must not become amazon.co
    assert unmask_alias(
        "auto-confirm_at_amazon_co_uk_mkihkiykyn@passmail.com"
    ).endswith("@amazon.co.uk")


def test_non_alias_returns_none():
    assert unmask_alias("chris.blacketer@lafosse.com") is None
    assert unmask_alias("someone@passmail.com") is None


def test_resolve_reports_alias_used():
    effective, alias = resolve("hello_at_readwise_io_auxxx@passmail.com")
    assert effective == "hello@readwise.io"
    assert alias == "hello_at_readwise_io_auxxx@passmail.com"


def test_resolve_passthrough_has_no_alias():
    effective, alias = resolve("Chris.Blacketer@Lafosse.com")
    assert effective == "chris.blacketer@lafosse.com"
    assert alias is None


def test_split_address():
    assert split_address("A.B@Example.COM") == ("a.b", "example.com")
    assert split_address("garbage") == ("garbage", "")


@pytest.mark.parametrize(
    "address,name",
    [
        ("no-reply@info.trading212.com", "Trading 212"),
        ("account-security-noreply@accountprotection.microsoft.com", "Microsoft"),
        ("notifications@github.com", "Boliang Zhang"),
        ("johnlewis@eml.johnlewis.com", "My John Lewis"),
        ("donotreply@instantink.hpsmart.com", "HP Instant Ink"),
        ("helpline@nectar.com", "Nectar"),
        ("noreply@e.dyson.co.uk", "Dyson"),
        ("support@on-si.zendesk.com", "Onsi Support"),
    ],
)
def test_services_detected(address, name):
    is_service, _ = looks_like_service(address, name)
    assert is_service, f"{address} should be classified as a service"


@pytest.mark.parametrize(
    "address,name",
    [
        ("chris.blacketer@lafosse.com", "Chris Blacketer"),
        ("mark.handscombe@northernenergy.co.uk", "Mark Handscombe"),
        ("fk@southsidemanagement.com", "Francesca Kane"),
        ("johnathan.fraser@patonandco.com", "Johnathan Fraser"),
    ],
)
def test_people_detected(address, name):
    is_service, _ = looks_like_service(address, name)
    assert not is_service, f"{address} should be classified as a person"


def test_role_account_beats_personal_display_name():
    # A human name on a role address is still a role address.
    is_service, reason = looks_like_service("support@example.com", "Sarah Jones")
    assert is_service and "role address" in reason


def test_opaque_local_part_is_a_service():
    is_service, reason = looks_like_service(
        "no-reply-IYIAapCYLOhnhMpvxFQbIA@mail.anthropic.com", "Anthropic"
    )
    assert is_service
