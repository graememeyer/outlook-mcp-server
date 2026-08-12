"""
Tests for the nextLink paging loop, using a fake Graph client so no
credentials or network access are needed.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mail import paging  # noqa: E402
from mail.paging import fetch_messages  # noqa: E402


class FakePage:
    def __init__(self, values, next_link=None):
        self.value = values
        self.odata_next_link = next_link


class FakeMessages:
    """Stands in for client.me.mail_folders.by_mail_folder_id(x).messages."""

    def __init__(self, pages, calls):
        self._pages = pages
        self._calls = calls

    async def get(self, request_configuration=None):
        self._calls.append(("first", request_configuration))
        return self._pages[0]


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.request_adapter = object()

        outer = self

        class _ByFolder:
            def by_mail_folder_id(self, folder_id):
                return SimpleNamespace(
                    messages=FakeMessages(outer.pages, outer.calls)
                )

        self.me = SimpleNamespace(mail_folders=_ByFolder())


@pytest.fixture
def patched_page_builder(monkeypatch):
    """Route follow-up page requests to the fake pages by index."""

    def _install(client):
        def fake_builder(_client, next_link):
            index = int(next_link.rsplit("=", 1)[1])
            page = client.pages[index]

            class _B:
                async def get(self):
                    client.calls.append(("next", next_link))
                    return page

            return _B()

        monkeypatch.setattr(paging, "_page_builder", fake_builder)

    return _install


@pytest.mark.asyncio
async def test_follows_next_link_across_pages(patched_page_builder):
    pages = [
        FakePage([f"m{i}" for i in range(500)], "https://graph/next?p=1"),
        FakePage([f"m{i}" for i in range(500, 1000)], "https://graph/next?p=2"),
        FakePage([f"m{i}" for i in range(1000, 1200)], None),
    ]
    client = FakeClient(pages)
    patched_page_builder(client)

    result = await fetch_messages(client, "inbox", object(), limit=5000)

    assert len(result) == 1200, "should have walked all three pages"
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_stops_at_limit_without_extra_requests(patched_page_builder):
    pages = [
        FakePage([f"m{i}" for i in range(500)], "https://graph/next?p=1"),
        FakePage([f"m{i}" for i in range(500, 1000)], "https://graph/next?p=2"),
        FakePage([f"m{i}" for i in range(1000, 1500)], None),
    ]
    client = FakeClient(pages)
    patched_page_builder(client)

    result = await fetch_messages(client, "inbox", object(), limit=600)

    assert len(result) == 600
    assert len(client.calls) == 2, "should not fetch a third page once the limit is met"


@pytest.mark.asyncio
async def test_single_page_without_next_link(patched_page_builder):
    client = FakeClient([FakePage(["a", "b", "c"], None)])
    patched_page_builder(client)

    result = await fetch_messages(client, "inbox", object(), limit=100)

    assert result == ["a", "b", "c"]
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_empty_folder(patched_page_builder):
    client = FakeClient([FakePage([], None)])
    patched_page_builder(client)

    assert await fetch_messages(client, "inbox", object(), limit=100) == []


@pytest.mark.asyncio
async def test_max_pages_guard_stops_runaway(patched_page_builder):
    # Every page advertises another page; the guard must break the loop.
    pages = [FakePage(["m"], "https://graph/next?p=0") for _ in range(10)]
    client = FakeClient(pages)
    patched_page_builder(client)

    result = await fetch_messages(client, "inbox", object(), limit=10000, max_pages=5)

    assert len(client.calls) == 5, "must stop at the max_pages guard"
    assert len(result) == 5
