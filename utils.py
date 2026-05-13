import socket
import ipaddress
from urllib.parse import urljoin, urlparse

MAX_FETCH_BYTES = 1 * 1024 * 1024
MAX_REDIRECTS = 3


def _is_public_ip(ip_addr: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_addr)
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )

def is_safe_url(url: str) -> bool:
    """
    Validates a URL to prevent Server-Side Request Forgery (SSRF).
    It checks if the URL has a valid scheme, extracts the hostname,
    resolves the IP, and ensures it does not point to a private,
    loopback, or unroutable address.
    """
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https"):
            return False
        if parsed_url.port and parsed_url.port not in (80, 443):
            return False

        hostname = parsed_url.hostname
        if not hostname:
            return False

        # Resolve every address, not just the first one. If any address is
        # private/internal, block the URL because DNS answers may rotate.
        addr_infos = socket.getaddrinfo(hostname, None)
        resolved_ips = {info[4][0] for info in addr_infos}
        if not resolved_ips:
            return False

        if any(not _is_public_ip(ip_addr) for ip_addr in resolved_ips):
            return False

        return True

    except (ValueError, socket.gaierror, Exception):
        # If hostname resolution fails or any parsing error occurs, block it
        return False


def _validate_next_url(current_url: str, location: str) -> str:
    next_url = urljoin(current_url, location)
    if not is_safe_url(next_url):
        raise ValueError("Unsafe redirect target blocked")
    return next_url


def safe_fetch_text(url: str, timeout: int = 10, max_bytes: int = MAX_FETCH_BYTES) -> str:
    """Fetch a public http(s) URL with SSRF guards, redirect checks, and a size cap."""
    import requests

    if not is_safe_url(url):
        raise ValueError("Unsafe URL blocked")

    current_url = url
    with requests.Session() as session:
        session.trust_env = False
        for _ in range(MAX_REDIRECTS + 1):
            response = session.get(current_url, timeout=timeout, allow_redirects=False, stream=True)
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("Redirect without Location blocked")
                current_url = _validate_next_url(current_url, location)
                continue

            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError("Response body too large")
            return bytes(content).decode(response.encoding or "utf-8", errors="replace")

    raise ValueError("Too many redirects")


async def safe_fetch_text_async(url: str, timeout: int = 15, max_bytes: int = MAX_FETCH_BYTES) -> str:
    """Async variant of safe_fetch_text for aiohttp callers."""
    import aiohttp

    if not is_safe_url(url):
        raise ValueError("Unsafe URL blocked")

    current_url = url
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=client_timeout, trust_env=False) as session:
        for _ in range(MAX_REDIRECTS + 1):
            async with session.get(current_url, allow_redirects=False) as response:
                if 300 <= response.status < 400:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Redirect without Location blocked")
                    current_url = _validate_next_url(current_url, location)
                    continue

                response.raise_for_status()
                content = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ValueError("Response body too large")
                charset = response.charset or "utf-8"
                return bytes(content).decode(charset, errors="replace")

    raise ValueError("Too many redirects")
