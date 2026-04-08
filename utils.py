import socket
import ipaddress
from urllib.parse import urlparse

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

        hostname = parsed_url.hostname
        if not hostname:
            return False

        # Resolve the hostname to an IP address
        ip_addr = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip_addr)

        # Check if the IP is a private or otherwise restricted network
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
            return False

        # Additional protection for AWS metadata service (169.254.169.254)
        if ip_addr == "169.254.169.254":
            return False

        return True

    except (ValueError, socket.gaierror, Exception):
        # If hostname resolution fails or any parsing error occurs, block it
        return False
