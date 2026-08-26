from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

MAX_PAGE_BYTES = 1024 * 1024
MAX_PAGE_CHARS = 6000
_DNS_SLOTS = threading.BoundedSemaphore(2)


class SearchCancelledError(Exception):
    pass


def check_cancelled(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise SearchCancelledError


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        address.is_global and not address.is_multicast and not address.is_reserved
        and not address.is_loopback and not address.is_link_local
        and not getattr(address, "ipv4_mapped", None)
        and not getattr(address, "sixtofour", None)
        and not getattr(address, "teredo", None)
    )


def public_web_url(value: str) -> str:
    if len(value) > 4096 or re.search(r"[\x00-\x20\x7f\\]", value):
        raise ValueError("invalid web URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("public HTTP(S) URL required")
    if parsed.port not in {None, 80 if parsed.scheme == "http" else 443}:
        raise ValueError("nonstandard web port")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if "%" in host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home", ".lan")):
        raise ValueError("local destination")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
            raise ValueError("invalid public hostname") from None
    else:
        if not public_address(host):
            raise ValueError("nonpublic destination")
    authority = f"[{host}]" if ":" in host else host
    return urlunsplit((parsed.scheme, authority, parsed.path or "/", parsed.query, ""))


class _ReadableHTML(HTMLParser):
    _EXCLUDED = frozenset({"script", "style", "nav", "header", "footer", "aside", "noscript", "template", "svg", "form"})
    _VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.parts: list[str] = []
        self.main_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
        hidden = (
            tag in self._EXCLUDED or "hidden" in attributes
            or (attributes.get("aria-hidden") or "").lower() == "true"
            or "display:none" in style or "visibility:hidden" in style
            or bool(self.stack and self.stack[-1][1])
        )
        main = tag in {"main", "article"} or bool(self.stack and self.stack[-1][2])
        if tag not in self._VOID:
            self.stack.append((tag, hidden, main))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][1]:
            return
        self.parts.append(data)
        if self.stack and self.stack[-1][2]:
            self.main_parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.main_parts or self.parts).split())


@dataclass(frozen=True, slots=True)
class PageResult:
    url: str
    status: str
    text: str = ""
    reason: str | None = None


class PublicPageReader:
    def __init__(self, timeout_s: float = 8.0) -> None:
        self.timeout_s = timeout_s

    def _resolve(self, host: str, port: int, cancelled: Callable[[], bool]) -> list[str]:
        # OS DNS calls cannot be interrupted. Bound both the caller wait and
        # outstanding resolver workers; abandoned calls retain their slot.
        if not _DNS_SLOTS.acquire(blocking=False):
            raise TimeoutError("DNS resolver busy")
        done = threading.Event()
        addresses: list[str] = []
        errors: list[Exception] = []

        def resolve() -> None:
            try:
                addresses.extend(sorted({str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}))
            except Exception as exc:
                errors.append(exc)
            finally:
                _DNS_SLOTS.release()
                done.set()

        threading.Thread(target=resolve, name="public-page-dns", daemon=True).start()
        deadline = time.monotonic() + self.timeout_s
        while not done.wait(0.05):
            check_cancelled(cancelled)
            if time.monotonic() >= deadline:
                raise TimeoutError("DNS resolution timed out")
        if errors:
            raise errors[0]
        return addresses

    def read(self, url: str, *, cancelled: Callable[[], bool]) -> PageResult:
        current = url
        try:
            for redirect in range(4):
                check_cancelled(cancelled)
                current = public_web_url(current)
                parsed = urlsplit(current)
                host = parsed.hostname or ""
                port = 443 if parsed.scheme == "https" else 80
                addresses = self._resolve(host, port, cancelled)
                if not addresses or not all(public_address(address) for address in addresses):
                    raise ValueError("DNS resolved to a nonpublic destination")
                check_cancelled(cancelled)
                # Pin the connection to the validated IP; Host and SNI retain origin identity.
                target = httpx.URL(current).copy_with(host=addresses[0])
                with (
                    httpx.Client(trust_env=False, follow_redirects=False, timeout=self.timeout_s) as client,
                    client.stream(
                    "GET", target,
                    headers={"Host": host, "Accept": "text/html,text/plain", "Accept-Encoding": "gzip, deflate"},
                    extensions={"sni_hostname": host},
                    ) as response,
                ):
                    check_cancelled(cancelled)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect == 3 or not response.headers.get("location"):
                            raise ValueError("redirect limit or missing destination")
                        destination = urljoin(current, response.headers["location"])
                        if parsed.scheme == "https" and urlsplit(destination).scheme != "https":
                            raise ValueError("insecure redirect")
                        current = destination
                        continue
                    response.raise_for_status()
                    media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if media not in {"text/html", "text/plain"}:
                        return PageResult(current, "unsupported", reason="HTML or plain text required")
                    body = self._read_body(response, cancelled)
                    text = body.decode(response.encoding or "utf-8", errors="replace")
                    if media == "text/html":
                        parser = _ReadableHTML()
                        parser.feed(text)
                        text = parser.text()
                    text = " ".join(text.split())[:MAX_PAGE_CHARS]
                    return PageResult(current, "success" if text else "empty", text)
        except SearchCancelledError:
            raise
        except ValueError as exc:
            return PageResult(url, "blocked", reason=str(exc))
        except Exception as exc:
            return PageResult(url, "unavailable", reason=f"page unavailable ({type(exc).__name__})")
        return PageResult(url, "unavailable", reason="page unavailable")

    @staticmethod
    def _read_body(response: httpx.Response, cancelled: Callable[[], bool]) -> bytes:
        encoding = response.headers.get("content-encoding", "identity").lower()
        if encoding not in {"identity", "gzip", "deflate"}:
            raise ValueError("unsupported content encoding")
        decoder = zlib.decompressobj(31 if encoding == "gzip" else 15) if encoding != "identity" else None
        body = bytearray()
        wire_bytes = 0
        for chunk in response.iter_raw(chunk_size=16384):
            check_cancelled(cancelled)
            wire_bytes += len(chunk)
            if wire_bytes > MAX_PAGE_BYTES:
                raise ValueError("page exceeds size limit")
            decoded = decoder.decompress(chunk, MAX_PAGE_BYTES - len(body) + 1) if decoder else chunk
            body.extend(decoded)
            if len(body) > MAX_PAGE_BYTES or (decoder and decoder.unconsumed_tail):
                raise ValueError("decoded page exceeds size limit")
        if decoder and (not decoder.eof or decoder.unused_data):
            raise ValueError("invalid compressed page")
        return bytes(body)
