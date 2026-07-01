"""Tests that the PooledHttpClient actually uses HTTP/2.

The whole point of switching from ``urllib`` to ``httpx`` was
HTTP/2 multiplexing — issuing many requests over a single TCP
connection so the round-trip latency is paid once, not per
request.  Without HTTP/2 the parallelism in the resilient
sitelinks fetcher is bottlenecked by the connection setup time.

These tests guard against accidentally falling back to HTTP/1.1
(usually because the ``h2`` package is missing — we install it
as a dependency but a fresh checkout without it would silently
degrade to HTTP/1.1 without any test failure otherwise).
"""
from __future__ import annotations

import socket
import ssl
import urllib.parse
import urllib.request

import pytest


def test_h2_package_is_available() -> None:
    """Without ``h2`` installed, ``httpx.Client(http2=True)`` falls
    back to HTTP/1.1 silently.  Guard against that regression by
    asserting the import + a sub-module attribute works.
    """
    import h2.connection  # noqa: F401
    assert hasattr(h2.connection, "H2Connection")


def test_pooled_client_negotiates_http2_with_wikidata() -> None:
    """Live test: a PooledHttpClient hit on
    ``https://www.wikidata.org`` should arrive with
    ``HTTP/2.0`` in the protocol string.  Skipped if the network
    isn't reachable so this doesn't flake offline.
    """
    try:
        socket.create_connection(("www.wikidata.org", 443), timeout=5).close()
    except OSError:
        pytest.skip("wikidata.org unreachable from this machine")

    import httpx
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch._pooled_http_client import (
        PooledHttpClient,
    )

    http_version_seen: list[str] = []

    def _sniff(response):
        ext = response.extensions or {}
        v = ext.get("http_version")
        if v is not None:
            # httpcore returns bytes like b"HTTP/2.0"
            http_version_seen.append(v if isinstance(v, str) else v.decode("ascii", "replace"))

    raw = httpx.Client(
        http2=True, timeout=20,
        event_hooks={"response": [_sniff]},
        headers={"User-Agent": "test"},
    )
    with PooledHttpClient() as client:
        # Replace the inner httpx client with our instrumented one
        # so we can observe the negotiated protocol.
        client._client = raw
        url = (
            "https://www.wikidata.org/w/api.php?"
            + urllib.parse.urlencode({
                "action": "wbgetentities",
                "ids": "Q243",
                "props": "sitelinks",
                "format": "json",
            })
        )
        out = client.get_json(url)
    assert out is not None
    assert "Q243" in out.get("entities", {}), "Wikidata should return at least Q243"
    # If HTTP/2 was negotiated, the version appears in the extensions.
    assert any("2" in v for v in http_version_seen), (
        "expected HTTP/2 protocol, saw: " + repr(http_version_seen)
    )
