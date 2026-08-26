from __future__ import annotations

import gzip
import socket
import threading

import httpx
import pytest
from backend.app.runtimes.internetsearch.page_reader import (
    MAX_PAGE_BYTES,
    PublicPageReader,
    SearchCancelledError,
    public_web_url,
)

pytestmark = pytest.mark.search


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://localhost/", "http://127.0.0.1/", "http://10.0.0.1/",
    "http://169.254.169.254/", "http://[::1]/", "http://[fc00::1]/", "http://[fe80::1]/",
    "http://[::ffff:127.0.0.1]/", "https://user:pass@example.com/", "https://example.com:8443/",
    "https://host.local/", "https://example.com\\@localhost/", "https://[2001:db8::1]/",
])
def test_nonpublic_urls_rejected(url):
    with pytest.raises(ValueError):
        public_web_url(url)


def install_http(monkeypatch, handler, addresses=("93.184.216.34",)):
    calls = []
    client_type = httpx.Client
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses])

    def wrapped(request):
        calls.append(request)
        return handler(request)

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert kwargs["timeout"] > 0
        return client_type(transport=httpx.MockTransport(wrapped), **kwargs)

    monkeypatch.setattr("backend.app.runtimes.internetsearch.page_reader.httpx.Client", client)
    return calls


def response(body, *, headers=None, code=200):
    return httpx.Response(code, headers=headers or {"content-type": "text/html"}, stream=httpx.ByteStream(body))


def test_extract_and_pin_origin_identity(monkeypatch):
    calls = install_http(monkeypatch, lambda r: response(b"<nav>navigation</nav><main>Public <b>facts</b><script>evil()</script><div hidden>hidden</div><span style='display:none'>secret</span></main><footer>footer</footer>"))
    page = PublicPageReader().read("https://example.com/path?version=2#part", cancelled=lambda: False)
    assert page.status == "success" and page.text == "Public facts"
    assert page.url == "https://example.com/path?version=2"
    assert calls[0].url.host == "93.184.216.34"
    assert calls[0].headers["host"] == "example.com"
    assert calls[0].extensions["sni_hostname"] == "example.com"
    assert calls[0].url.query == b"version=2"


def test_mixed_public_private_dns_rejected_before_connect(monkeypatch):
    calls = install_http(monkeypatch, lambda r: response(b"bad"), addresses=("93.184.216.34", "127.0.0.1"))
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).status == "blocked"
    assert not calls


def test_redirect_revalidates_dns_and_caps_hops(monkeypatch):
    calls = install_http(monkeypatch, lambda r: response(b"", headers={"location": "https://next.example.com/"}, code=302))
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).status == "blocked"
    assert len(calls) == 4


@pytest.mark.parametrize("location", ["http://127.0.0.1/", "https://[::1]/", "http://example.com/"])
def test_redirect_cannot_escape_public_https(monkeypatch, location):
    calls = install_http(monkeypatch, lambda r: response(b"", headers={"location": location}, code=302))
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).status == "blocked"
    assert len(calls) == 1


def test_dns_rebinding_redirect_is_rejected(monkeypatch):
    calls = install_http(monkeypatch, lambda r: response(b"", headers={"location": "/next"}, code=302))
    answers = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), 443))])
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).status == "blocked"
    assert len(calls) == 1


@pytest.mark.parametrize("compressed", [False, True])
def test_decoded_size_limit(monkeypatch, compressed):
    body = b"x" * (MAX_PAGE_BYTES + 1)
    headers = {"content-type": "text/plain"}
    if compressed:
        body = gzip.compress(body)
        headers["content-encoding"] = "gzip"
    install_http(monkeypatch, lambda r: response(body, headers=headers))
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).status == "blocked"


def test_supported_compression_and_unsupported_media(monkeypatch):
    install_http(monkeypatch, lambda r: response(gzip.compress(b"public text"), headers={"content-type": "text/plain", "content-encoding": "gzip"}))
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).text == "public text"


def test_pdf_is_not_read(monkeypatch):
    install_http(monkeypatch, lambda r: response(b"%PDF", headers={"content-type": "application/pdf"}))
    assert PublicPageReader().read("https://example.com/", cancelled=lambda: False).status == "unsupported"


def test_cancellation_and_dns_timeout(monkeypatch):
    with pytest.raises(SearchCancelledError):
        PublicPageReader().read("https://example.com/", cancelled=lambda: True)
    release = threading.Event()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: release.wait(2))
    try:
        assert PublicPageReader(timeout_s=0.01).read("https://example.com/", cancelled=lambda: False).status == "unavailable"
    finally:
        release.set()
